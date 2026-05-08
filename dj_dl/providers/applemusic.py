from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dj_dl.providers.base import BaseProvider, ProviderResult, Track
from dj_dl.providers.youtube import YouTubeProvider

logger = logging.getLogger(__name__)


class AppleMusicProvider(BaseProvider):
    name = "apple_music"

    def __init__(self, cookies_path: str | None = None) -> None:
        self.cookies_path = cookies_path
        self._api = None
        self._youtube = YouTubeProvider()

    def can_handle(self, url: str) -> bool:
        return "music.apple.com" in url

    def _parse_url(self, url: str) -> dict[str, str]:
        pattern = r"music\.apple\.com/([^/]+)/(?:([^/]+)/)?([^/]+)/(?:[^/]+/)?(\d+)"
        match = re.search(pattern, url)
        if match:
            groups = match.groups()
            return {
                "storefront": groups[0] or "us",
                "type": groups[1] or "song",
                "id": groups[-1],
            }
        alt = r"music\.apple\.com/([^/]+)/playlist/[^/]+/(pl\.[^/?]+)"
        m2 = re.search(alt, url)
        if m2:
            return {"storefront": m2.group(1), "type": "playlist", "id": m2.group(2)}
        return {"storefront": "us", "type": "", "id": ""}

    async def extract(self, url: str) -> ProviderResult:
        if not self.cookies_path:
            return ProviderResult(tracks=[], source="apple_music")

        info = self._parse_url(url)
        item_type = info.get("type", "")
        item_id = info.get("id", "")
        storefront = info.get("storefront", "us")

        if not item_id or not item_type:
            return ProviderResult(tracks=[], source="apple_music")

        try:
            from gamdl.api import AppleMusicApi

            api = await AppleMusicApi.create_from_netscape_cookies(
                cookies_path=self.cookies_path,
                storefront=storefront,
            )

            if not api.active_subscription:
                return ProviderResult(tracks=[], source="apple_music")

            if item_type == "song":
                data = await api.get_song(item_id)
                tracks = [self._am_song_to_track(data["data"][0], 1)]
                return ProviderResult(tracks=tracks, source="apple_music")

            if item_type == "album":
                data = await api.get_album(item_id)
                album_data = data["data"][0]
                track_list = album_data.get("relationships", {}).get("tracks", {}).get("data", [])
                tracks = []
                for idx, track_data in enumerate(track_list, 1):
                    tracks.append(self._am_song_to_track(track_data, idx))
                return ProviderResult(
                    tracks=tracks,
                    playlist_name=album_data.get("attributes", {}).get("name", ""),
                    source="apple_music",
                )

            if item_type == "playlist":
                data = await api.get_playlist(item_id)
                playlist_data = data["data"][0]
                track_list = (
                    playlist_data.get("relationships", {}).get("tracks", {}).get("data", [])
                )
                tracks = []
                for idx, track_data in enumerate(track_list, 1):
                    tracks.append(self._am_song_to_track(track_data, idx))
                return ProviderResult(
                    tracks=tracks,
                    playlist_name=playlist_data.get("attributes", {}).get("name", ""),
                    source="apple_music",
                )

        except Exception as e:
            logger.debug("Apple Music extraction failed: %s", e)

        return ProviderResult(tracks=[], source="apple_music")

    def _am_song_to_track(self, song: dict[str, Any], index: int) -> Track:
        attrs = song.get("attributes", {})
        artwork = attrs.get("artwork", {})
        return Track(
            title=attrs.get("name", ""),
            artist=attrs.get("artistName", ""),
            album=attrs.get("albumName", ""),
            source_url=attrs.get("url", ""),
            duration_ms=attrs.get("durationInMillis", 0),
            track_number=index,
            cover_url=self._build_artwork_url(artwork),
            genre=", ".join(attrs.get("genreNames", [])),
            year=0,
            isrc=attrs.get("isrc", ""),
        )

    def _build_artwork_url(self, artwork: dict[str, Any], size: int = 1200) -> str:
        url = artwork.get("url", "")
        if url:
            return url.replace("{w}", str(size)).replace("{h}", str(size))
        return ""

    async def download(
        self,
        track: Track,
        output_dir: Path,
        progress_callback: Callable | None = None,
    ) -> Path:
        if not self.cookies_path:
            raise RuntimeError("Apple Music authentication required. Run: djdl auth")

        try:
            from gamdl.api import AppleMusicApi
            from gamdl.downloader import (
                AppleMusicBaseDownloader,
                AppleMusicDownloader,
                AppleMusicMusicVideoDownloader,
                AppleMusicSongDownloader,
                AppleMusicUploadedVideoDownloader,
            )
            from gamdl.interface import (
                AppleMusicBaseInterface,
                AppleMusicInterface,
                AppleMusicMusicVideoInterface,
                AppleMusicSongInterface,
                AppleMusicUploadedVideoInterface,
            )

            api = await AppleMusicApi.create_from_netscape_cookies(
                cookies_path=self.cookies_path,
            )

            base_interface = await AppleMusicBaseInterface.create(
                apple_music_api=api,
            )

            song_interface = AppleMusicSongInterface(base=base_interface)
            mv_interface = AppleMusicMusicVideoInterface(base=base_interface)
            uv_interface = AppleMusicUploadedVideoInterface(base=base_interface)

            interface = AppleMusicInterface(
                song=song_interface,
                music_video=mv_interface,
                uploaded_video=uv_interface,
            )

            temp_dir = output_dir / ".gamdl_temp"
            temp_dir.mkdir(parents=True, exist_ok=True)

            base_downloader = AppleMusicBaseDownloader(
                interface=interface,
                output_path=str(temp_dir),
            )

            song_downloader = AppleMusicSongDownloader(base=base_downloader)
            mv_downloader = AppleMusicMusicVideoDownloader(base=base_downloader)
            uv_downloader = AppleMusicUploadedVideoDownloader(base=base_downloader)

            downloader = AppleMusicDownloader(
                song=song_downloader,
                music_video=mv_downloader,
                uploaded_video=uv_downloader,
            )

            async for item in downloader.get_download_item_from_url(track.source_url):
                await downloader.download(item)

            m4a_files = list(temp_dir.rglob("*.m4a"))
            if not m4a_files:
                raise FileNotFoundError("No .m4a file found after download")

            source_file = m4a_files[0]
            safe_name = re.sub(r'[<>:"/\\|?*]', "", f"{track.artist} - {track.title}")
            dest_file = output_dir / f"{safe_name}.m4a"

            counter = 1
            while dest_file.exists():
                dest_file = output_dir / f"{safe_name} ({counter}).m4a"
                counter += 1

            source_file.rename(dest_file)

            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

            return dest_file

        except Exception as e:
            raise RuntimeError(f"Apple Music download failed: {e}") from e
