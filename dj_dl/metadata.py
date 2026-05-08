"""Metadata embedder with mutagen for M4A, MP3, and FLAC."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import httpx
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, TALB, TCON, TDRC, TIT2, TPE1, TRCK
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover

from dj_dl.providers.base import Track


@dataclass
class MetadataResult:
    success: bool
    path: Path
    error: str | None = None


async def embed_metadata(filepath: Path, track: Track) -> MetadataResult:
    try:
        suffix = filepath.suffix.lower()
        if suffix == ".m4a":
            await asyncio.to_thread(_tag_m4a, filepath, track)
        elif suffix == ".mp3":
            await asyncio.to_thread(_tag_mp3, filepath, track)
        elif suffix == ".flac":
            await asyncio.to_thread(_tag_flac, filepath, track)
        else:
            return MetadataResult(
                success=False, path=filepath, error=f"Unsupported format: {suffix}"
            )
        return MetadataResult(success=True, path=filepath)
    except Exception as e:
        return MetadataResult(success=False, path=filepath, error=str(e))


def _tag_m4a(filepath: Path, track: Track) -> None:
    audio = MP4(str(filepath))

    if track.title:
        audio["\xa9nam"] = [track.title]
    if track.artist:
        audio["\xa9ART"] = [track.artist]
        audio["aART"] = [track.artist]
    if track.album:
        audio["\xa9alb"] = [track.album]
    if track.track_number:
        audio["trkn"] = [(track.track_number, 0)]
    if track.genre:
        audio["\xa9gen"] = [track.genre]
    if track.year:
        audio["\xa9day"] = [str(track.year)]

    if track.cover_url:
        cover_data = asyncio.run(_download_cover(track.cover_url))
        if cover_data:
            audio["covr"] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]

    audio.save()


def _tag_mp3(filepath: Path, track: Track) -> None:
    audio = MP3(str(filepath))
    if audio.tags is None:
        audio.add_tags()

    tags = audio.tags
    if tags is None:
        return
    if track.title:
        tags["TIT2"] = TIT2(encoding=3, text=track.title)
    if track.artist:
        tags["TPE1"] = TPE1(encoding=3, text=track.artist)
    if track.album:
        tags["TALB"] = TALB(encoding=3, text=track.album)
    if track.track_number:
        tags["TRCK"] = TRCK(encoding=3, text=str(track.track_number))
    if track.year:
        tags["TDRC"] = TDRC(encoding=3, text=str(track.year))
    if track.genre:
        tags["TCON"] = TCON(encoding=3, text=track.genre)

    if track.cover_url:
        cover_data = asyncio.run(_download_cover(track.cover_url))
        if cover_data:
            tags["APIC"] = APIC(
                encoding=3,
                mime="image/jpeg",
                type=3,
                desc="Cover",
                data=cover_data,
            )

    audio.save()


def _tag_flac(filepath: Path, track: Track) -> None:
    audio = FLAC(str(filepath))

    if track.title:
        audio["TITLE"] = track.title
    if track.artist:
        audio["ARTIST"] = track.artist
    if track.album:
        audio["ALBUM"] = track.album
    if track.track_number:
        audio["TRACKNUMBER"] = str(track.track_number)
    if track.year:
        audio["DATE"] = str(track.year)
    if track.genre:
        audio["GENRE"] = track.genre

    if track.cover_url:
        cover_data = asyncio.run(_download_cover(track.cover_url))
        if cover_data:
            pic = Picture()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.desc = "Cover"
            pic.data = cover_data
            audio.add_picture(pic)

    audio.save()


async def _download_cover(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
            if response.status_code == 200:
                return response.content
    except Exception:
        pass
    return None
