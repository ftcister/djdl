"""Spotify provider: metadata via API/embed fallback, then YouTube matching."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yt_dlp

from dj_dl.providers.base import BaseProvider, ProviderResult, Track
from dj_dl.providers.youtube import YouTubeProvider


class SpotifyProvider(BaseProvider):
    """Extracts Spotify metadata and finds audio on YouTube."""

    name = "spotify"

    def __init__(self, client_id: str | None = None, client_secret: str | None = None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._sp = None
        self._youtube = YouTubeProvider()

        if client_id and client_secret:
            try:
                import spotipy
                from spotipy.oauth2 import SpotifyClientCredentials

                auth = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
                self._sp = spotipy.Spotify(auth_manager=auth)
            except Exception:
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
            except Exception:
                pass

        try:
            result = await self._extract_from_embed(item_type, item_id)
            if result.tracks:
                return result
        except Exception:
            pass

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
            artist = data.get("artistName", "")

        return Track(
            title=data.get("name", data.get("title", "")),
            artist=artist,
            album=data.get("album", {}).get("name", ""),
            source_url=data.get("uri", ""),
            duration_ms=data.get("duration", 0),
            track_number=index,
            cover_url="",
            isrc=data.get("isrc", ""),
        )

    async def _match_on_youtube(self, tracks: list[Track]) -> list[Track]:
        for track in tracks:
            query = f"{track.title} - {track.artist}"
            if track.isrc:
                query = f"{track.isrc} {query}"

            search_url = f"ytsearch1:{query}"

            def _search(url: str, opts: dict) -> dict[str, Any]:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)

            try:
                result = await asyncio.to_thread(
                    _search,
                    search_url,
                    {"quiet": True, "extract_flat": False, "skip_download": True},
                )
                entries = result.get("entries", [])
                if entries and entries[0]:
                    track.download_url = entries[0].get("webpage_url", entries[0].get("url", ""))
            except Exception:
                pass

        return tracks

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
                raise ValueError(f"No YouTube match found for {track.title}")

        return await self._youtube.download(track, output_dir, progress_callback)
