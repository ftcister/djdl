"""YouTube provider using yt-dlp Python API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yt_dlp

from dj_dl.providers.base import BaseProvider, ProviderResult, Track

logger = logging.getLogger(__name__)


class YouTubeProvider(BaseProvider):
    """Downloads audio from YouTube using yt-dlp."""

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
            "extract_flat": False,
            "skip_download": True,
        }

        def _extract() -> dict[str, Any]:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = await asyncio.to_thread(_extract)

        if info.get("_type") == "playlist":
            tracks = []
            for idx, entry in enumerate(info.get("entries", []), 1):
                if entry:
                    tracks.append(self._entry_to_track(entry, idx))
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

        return Track(
            title=title,
            artist=artist or "Unknown Artist",
            album=entry.get("album", ""),
            source_url=entry.get("webpage_url", entry.get("url", "")),
            download_url=entry.get("webpage_url", entry.get("url", "")),
            duration_ms=(entry.get("duration") or 0) * 1000,
            track_number=index,
            cover_url=entry.get("thumbnail", ""),
            genre=entry.get("genre", ""),
            year=entry.get("release_year") or 0,
            isrc=entry.get("isrc", ""),
        )

    async def download(
        self,
        track: Track,
        output_dir: Path,
        progress_callback: Callable | None = None,
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(output_dir / "%(title)s.%(ext)s")

        ydl_opts = {
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
        }

        before = set(output_dir.glob("*.m4a"))

        def _download() -> None:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([track.download_url])

        await asyncio.to_thread(_download)

        after = set(output_dir.glob("*.m4a"))
        new_files = after - before

        if new_files:
            return new_files.pop()

        expected_path = output_dir / f"{track.title}.m4a"
        if expected_path.exists():
            return expected_path

        for f in output_dir.glob("*.m4a"):
            if track.title.lower() in f.name.lower() or track.source_url in f.name:
                return f

        logger.error("Downloaded file not found in %s for track: %s", output_dir, track.title)
        raise FileNotFoundError(f"Downloaded file not found in {output_dir}")
