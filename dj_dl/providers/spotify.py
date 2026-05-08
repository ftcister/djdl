"""Spotify provider: metadata via API/embed fallback, then YouTube Music matching."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yt_dlp
from rapidfuzz import fuzz
from ytmusicapi import YTMusic

from dj_dl.providers.base import BaseProvider, ProviderResult, Track
from dj_dl.providers.youtube import YouTubeProvider

logger = logging.getLogger(__name__)

_FORBIDDEN_WORDS = {
    "cover",
    "remix",
    "live",
    "karaoke",
    "reaction",
    "tutorial",
    "instrumental",
    "acoustic",
    "piano",
    "guitar",
}
_MIN_MATCH_SCORE = 70.0


def _normalize(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[\[(].*?[])]", "", t)
    return t.strip()


def _contains_forbidden(title: str) -> bool:
    words = set(_normalize(title).split())
    return bool(words & _FORBIDDEN_WORDS)


def _calc_duration_match(spotify_ms: int, youtube_s: int) -> float:
    if youtube_s <= 0:
        return 0.0
    diff = abs((spotify_ms / 1000) - youtube_s)
    return math.exp(-0.1 * diff) * 100


def _best_artist_match(spotify_artist: str, yt_artists: list[dict[str, str]]) -> float:
    if not yt_artists:
        return 0.0
    best = 0.0
    normalized_spotify = _normalize(spotify_artist)
    for artist in yt_artists:
        name = artist.get("name", "")
        score = fuzz.ratio(normalized_spotify, _normalize(name))
        if score > best:
            best = score
    return best


def _score_result(track: Track, result: dict[str, Any]) -> float:
    result_title = result.get("title", "")
    result_artists = result.get("artists", [])
    result_duration = result.get("duration_seconds", 0) or result.get("lengthSeconds", 0)

    album_data = result.get("album")
    result_album = album_data.get("name", "") if isinstance(album_data, dict) else ""

    name_score = fuzz.ratio(_normalize(track.title), _normalize(result_title))
    artist_score = _best_artist_match(track.artist, result_artists)
    duration_score = _calc_duration_match(track.duration_ms, result_duration)
    album_score = fuzz.ratio(_normalize(track.album), _normalize(result_album))

    if _contains_forbidden(result_title) and not _contains_forbidden(track.title):
        name_score *= 0.3

    return (
        (name_score * 0.25) + (artist_score * 0.25) + (duration_score * 0.25) + (album_score * 0.25)
    )


class SpotifyProvider(BaseProvider):
    name = "spotify"

    def __init__(self, client_id: str | None = None, client_secret: str | None = None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._sp = None
        self._youtube = YouTubeProvider()
        self._ytmusic = YTMusic()

        if client_id and client_secret:
            try:
                import spotipy
                from spotipy.oauth2 import SpotifyClientCredentials

                auth = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
                self._sp = spotipy.Spotify(auth_manager=auth)
            except Exception as e:
                logger.debug("Failed to initialize Spotify API client: %s", e)
                self._sp = None

    def can_handle(self, url: str) -> bool:
        return "open.spotify.com" in url or "spotify.com" in url

    def _parse_url(self, url: str) -> tuple[str, str]:
        parsed = urlparse(url)
        match = re.search(r"/(track|album|playlist)/([^/?]+)", parsed.path)
        if match:
            return match.group(1), match.group(2)
        return "", ""

    async def extract(self, url: str) -> ProviderResult:
        item_type, item_id = self._parse_url(url)
        if not item_type or not item_id:
            return ProviderResult(tracks=[], source="spotify")

        if self._sp:
            try:
                result = await self._extract_with_api(item_type, item_id)
                if result.tracks:
                    return result
            except Exception as e:
                logger.debug("Spotify API extraction failed: %s", e)

        try:
            result = await self._extract_from_embed(item_type, item_id)
            if result.tracks:
                return result
        except Exception as e:
            logger.debug("Spotify embed extraction failed: %s", e)

        return ProviderResult(tracks=[], source="spotify")

    async def _extract_with_api(self, item_type: str, item_id: str) -> ProviderResult:
        sp = self._sp
        if sp is None:
            return ProviderResult(tracks=[], source="spotify")

        def _fetch() -> dict[str, Any]:
            if item_type == "track":
                return sp.track(item_id)
            elif item_type == "album":
                return sp.album(item_id)
            elif item_type == "playlist":
                return sp.playlist(item_id)
            return {}

        data = await asyncio.to_thread(_fetch)

        if item_type == "track":
            return ProviderResult(
                tracks=[self._api_track_to_track(data)],
                source="spotify",
            )

        if item_type == "album":
            tracks = []
            for idx, t in enumerate(data.get("tracks", {}).get("items", []), 1):
                tracks.append(self._api_track_to_track(t, idx))
            return ProviderResult(
                tracks=tracks,
                playlist_name=data.get("name", ""),
                source="spotify",
            )

        if item_type == "playlist":
            tracks = []
            for idx, item in enumerate(data.get("tracks", {}).get("items", []), 1):
                t = item.get("track")
                if t:
                    tracks.append(self._api_track_to_track(t, idx))
            return ProviderResult(
                tracks=tracks,
                playlist_name=data.get("name", ""),
                source="spotify",
            )

        return ProviderResult(tracks=[], source="spotify")

    def _api_track_to_track(self, data: dict[str, Any], index: int = 1) -> Track:
        artists = data.get("artists", [])
        artist = artists[0].get("name", "") if artists else ""
        album = data.get("album", {})
        return Track(
            title=data.get("name", ""),
            artist=artist,
            album=album.get("name", "") if isinstance(album, dict) else "",
            source_url=data.get("external_urls", {}).get("spotify", ""),
            duration_ms=data.get("duration_ms", 0),
            track_number=index,
            cover_url=(
                album.get("images", [{}])[0].get("url", "") if isinstance(album, dict) else ""
            ),
            isrc=data.get("external_ids", {}).get("isrc", ""),
        )

    async def _extract_from_embed(self, item_type: str, item_id: str) -> ProviderResult:
        embed_url = f"https://open.spotify.com/embed/{item_type}/{item_id}"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(embed_url)
            response.raise_for_status()
            html = response.text

        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
        )
        if not match:
            match = re.search(r'<script id="resource" type="application/json">(.*?)</script>', html)

        if not match:
            return ProviderResult(tracks=[], source="spotify")

        data = json.loads(match.group(1))

        props = data.get("props", {}).get("pageProps", {})
        state = props.get("state", {})
        data_obj = state.get("data", {})
        entity = data_obj.get("entity", {})

        if item_type == "track":
            return ProviderResult(
                tracks=[self._embed_track_to_track(entity)],
                source="spotify",
            )

        if item_type in ("album", "playlist"):
            tracks = []
            track_list = entity.get("trackList", entity.get("tracks", []))
            for idx, t in enumerate(track_list, 1):
                tracks.append(self._embed_track_to_track(t, idx))
            return ProviderResult(
                tracks=tracks,
                playlist_name=entity.get("name", entity.get("title", "")),
                source="spotify",
            )

        return ProviderResult(tracks=[], source="spotify")

    def _embed_track_to_track(self, data: dict[str, Any], index: int = 1) -> Track:
        artists = data.get("artists", [])
        if artists and isinstance(artists[0], dict):
            artist = artists[0].get("name", "")
        elif artists and isinstance(artists[0], str):
            artist = artists[0]
        else:
            artist = data.get("artistName", "") or data.get("subtitle", "")

        album = data.get("album")
        album_name = album.get("name", "") if isinstance(album, dict) else ""
        isrc = data.get("isrc", "") or ""

        cover_url = ""
        visual_identity = data.get("visualIdentity", {})
        if isinstance(visual_identity, dict):
            images = visual_identity.get("image", [])
            if images and isinstance(images, list):
                cover_url = images[0].get("url", "")

        return Track(
            title=data.get("name", data.get("title", "")),
            artist=artist,
            album=album_name,
            source_url=data.get("uri", ""),
            duration_ms=data.get("duration", 0) or 0,
            track_number=index,
            cover_url=cover_url,
            isrc=isrc,
        )

    async def _match_on_youtube(self, tracks: list[Track]) -> list[Track]:
        for track in tracks:
            if not track.title or not track.artist:
                continue

            matched_url, matched_thumb = await self._match_on_youtube_music(track)
            if not matched_url:
                matched_url, matched_thumb = await self._match_on_youtube_search(track)

            if matched_url:
                track.download_url = matched_url
            if matched_thumb and not track.cover_url:
                track.cover_url = matched_thumb

        return tracks

    async def _match_on_youtube_music(self, track: Track) -> tuple[str | None, str | None]:
        queries = self._build_queries(track)
        all_results: list[dict[str, Any]] = []

        for query in queries:
            try:
                results = await asyncio.to_thread(
                    self._ytmusic.search,
                    query,
                    filter="songs",
                    limit=10,
                    ignore_spelling=True,
                )
                if results:
                    all_results.extend(results)
            except Exception as e:
                logger.debug("YouTube Music search failed for %s: %s", query, e)

        if not all_results:
            return None, None

        best_score = 0.0
        best_result = None

        for result in all_results:
            score = _score_result(track, result)
            if score > best_score:
                best_score = score
                best_result = result

        if best_result and best_score >= _MIN_MATCH_SCORE:
            video_id = best_result.get("videoId")
            if video_id:
                logger.debug("YT Music matched %s (score=%.1f)", track.title, best_score)
                thumb = ""
                thumbs = best_result.get("thumbnails", [])
                if thumbs and isinstance(thumbs, list):
                    thumb = thumbs[-1].get("url", "")
                return f"https://music.youtube.com/watch?v={video_id}", thumb
        return None, None

    async def _match_on_youtube_search(self, track: Track) -> tuple[str | None, str | None]:
        query = f"{track.title} - {track.artist}"
        if track.isrc:
            query = f"{track.isrc} {query}"
        search_url = f"ytsearch1:{query}"

        def _search() -> dict[str, Any]:
            with yt_dlp.YoutubeDL(
                {
                    "quiet": True,
                    "no_warnings": True,
                    "extract_flat": False,
                    "skip_download": True,
                }
            ) as ydl:
                return ydl.extract_info(search_url, download=False)

        try:
            result = await asyncio.to_thread(_search)
            entries = result.get("entries", [])
            if entries and entries[0]:
                entry = entries[0]
                url = entry.get("webpage_url", entry.get("url", ""))
                thumb = ""
                thumbnails = entry.get("thumbnails", [])
                if thumbnails and isinstance(thumbnails, list):
                    thumb = thumbnails[-1].get("url", "")
                if not thumb:
                    thumb = entry.get("thumbnail", "")
                logger.debug("YT Search fallback matched %s", track.title)
                return url, thumb
        except Exception as e:
            logger.debug("YouTube search fallback failed for %s: %s", track.title, e)
        return None, None

        try:
            result = await asyncio.to_thread(_search)
            entries = result.get("entries", [])
            if entries and entries[0]:
                url = entries[0].get("webpage_url", entries[0].get("url", ""))
                logger.debug("YT Search fallback matched %s", track.title)
                return url
        except Exception as e:
            logger.debug("YouTube search fallback failed for %s: %s", track.title, e)
        return None

    def _build_queries(self, track: Track) -> list[str]:
        if track.isrc:
            return [
                f"{track.isrc} {track.title} - {track.artist}",
                f"{track.isrc} {track.artist} - {track.title}",
            ]
        return [
            f"{track.title} - {track.artist}",
            f"{track.artist} - {track.title}",
        ]

    async def download(
        self,
        track: Track,
        output_dir: Path,
        progress_callback: Callable | None = None,
    ) -> Path:
        if not track.download_url:
            matched = await self._match_on_youtube([track])
            if matched and matched[0].download_url:
                track = matched[0]
            else:
                raise ValueError(f"No YouTube Music match found for {track.title}")

        return await self._youtube.download(track, output_dir, progress_callback)
