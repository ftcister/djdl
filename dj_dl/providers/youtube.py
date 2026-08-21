"""YouTube provider using yt-dlp Python API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yt_dlp

from dj_dl.providers.base import BaseProvider, ProviderResult, Track, sanitize_filename

logger = logging.getLogger(__name__)

logging.getLogger("yt_dlp").setLevel(logging.ERROR)


class YouTubeProvider(BaseProvider):
    name = "youtube"

    def can_handle(self, url: str) -> bool:
        return any(
            pattern in url
            for pattern in (
                "youtube.com/watch",
                "youtu.be/",
                "youtube.com/playlist",
                "music.youtube.com",
            )
        )

    async def extract(self, url: str) -> ProviderResult:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            # Flat extraction walks the playlist's continuation pages in one pass
            # instead of fully resolving every video; full extraction of large
            # playlists is slow and gets silently truncated at 100 entries when
            # a continuation request fails.
            "extract_flat": "in_playlist",
            "extractor_retries": 3,
            "ignoreerrors": True,
            "skip_download": True,
        }

        def _extract() -> dict[str, Any] | None:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = await asyncio.to_thread(_extract)

        # ignoreerrors reports a URL that cannot be extracted at all — deleted, private or
        # region-blocked — by returning None rather than by raising.
        if info is None:
            logger.warning("No metadata extracted for %s", url)
            return ProviderResult(tracks=[], source="youtube")

        if info.get("_type") == "playlist":
            tracks = []
            for idx, entry in enumerate(info.get("entries", []), 1):
                if entry:
                    tracks.append(self._entry_to_track(entry, idx))
            expected = info.get("playlist_count") or 0
            if expected and len(tracks) < expected:
                logger.warning(
                    "Playlist extraction incomplete: got %d of %d tracks for %s",
                    len(tracks),
                    expected,
                    url,
                )
            return ProviderResult(
                tracks=tracks,
                playlist_name=info.get("title", "Unknown Playlist"),
                source="youtube",
            )

        return ProviderResult(
            tracks=[self._entry_to_track(info, 1)],
            source="youtube",
        )

    def _entry_to_track(self, entry: dict[str, Any], index: int) -> Track:
        title = entry.get("title", "")
        artist = entry.get("artist", "")

        if not artist and " - " in title:
            parts = title.split(" - ", 1)
            artist = parts[0].strip()
            title = parts[1].strip()

        cover_url = entry.get("thumbnail", "")
        thumbnails = entry.get("thumbnails", [])
        if thumbnails and isinstance(thumbnails, list):
            cover_url = thumbnails[-1].get("url", cover_url)

        return Track(
            title=title,
            artist=artist or entry.get("uploader") or entry.get("channel") or "Unknown Artist",
            album=entry.get("album", ""),
            source_url=entry.get("webpage_url", entry.get("url", "")),
            download_url=entry.get("webpage_url", entry.get("url", "")),
            duration_ms=(entry.get("duration") or 0) * 1000,
            track_number=index,
            cover_url=cover_url,
            genre=entry.get("genre", ""),
            year=entry.get("release_year") or 0,
            isrc=entry.get("isrc", ""),
        )

    def _backfill_track(self, track: Track, info: dict[str, Any]) -> None:
        """Fill metadata that flat playlist entries lack, using the full video info."""
        if info.get("artist") and track.artist in ("", "Unknown Artist"):
            track.artist = info["artist"]
        if not track.album:
            track.album = info.get("album", "")
        if not track.genre:
            track.genre = info.get("genre", "")
        if not track.year:
            track.year = info.get("release_year") or 0
        if not track.isrc:
            track.isrc = info.get("isrc", "")
        if not track.duration_ms:
            track.duration_ms = (info.get("duration") or 0) * 1000
        if not track.cover_url:
            thumbnails = info.get("thumbnails")
            if thumbnails and isinstance(thumbnails, list):
                track.cover_url = thumbnails[-1].get("url", "")
            else:
                track.cover_url = info.get("thumbnail", "")

    async def download(
        self,
        track: Track,
        output_dir: Path,
        progress_callback: Callable | None = None,
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_title = sanitize_filename(track.title)
        safe_artist = sanitize_filename(track.artist)
        base_name = f"{safe_title} - {safe_artist}"

        output_template = str(output_dir / f"{base_name}.%(ext)s")

        ydl_opts: dict[str, Any] = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "256",
                }
            ],
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
        }

        loop = asyncio.get_running_loop()

        if progress_callback:

            def _hook(info_dict: dict[str, Any]) -> None:
                if info_dict.get("status") == "downloading":
                    total = info_dict.get("total_bytes") or info_dict.get("total_bytes_estimate", 0)
                    downloaded = info_dict.get("downloaded_bytes", 0)
                    if total > 0:
                        pct = downloaded / total
                        asyncio.run_coroutine_threadsafe(
                            progress_callback(track, pct),
                            loop,
                        )
                elif info_dict.get("status") == "finished":
                    asyncio.run_coroutine_threadsafe(
                        progress_callback(track, 1.0),
                        loop,
                    )

            ydl_opts["progress_hooks"] = [_hook]

        def _download() -> dict[str, Any] | None:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(track.download_url, download=True)

        info = await asyncio.to_thread(_download)
        if info:
            self._backfill_track(track, info)

        expected_path = output_dir / f"{base_name}.m4a"
        if expected_path.exists():
            return expected_path

        for f in output_dir.glob("*.m4a"):
            if base_name in f.name:
                return f

        logger.error("Downloaded file not found in %s for track: %s", output_dir, track.title)
        raise FileNotFoundError(f"Downloaded file not found in {output_dir}")
