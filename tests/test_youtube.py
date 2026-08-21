import logging
from unittest.mock import MagicMock, patch

import pytest

from dj_dl.providers.base import Track
from dj_dl.providers.youtube import YouTubeProvider


def _mock_ydl(info: dict | None) -> MagicMock:
    ydl = MagicMock()
    ydl.extract_info.return_value = info
    ctx = MagicMock()
    ctx.__enter__.return_value = ydl
    ctx.__exit__.return_value = False
    return ctx


def _flat_entry(idx: int) -> dict:
    return {
        "url": f"https://www.youtube.com/watch?v=video{idx}",
        "title": f"Artist {idx} - Song {idx}",
        "duration": 200,
    }


@pytest.mark.asyncio
async def test_extract_uses_flat_playlist_extraction():
    info = {"_type": "playlist", "title": "P", "playlist_count": 1, "entries": [_flat_entry(1)]}
    with patch("yt_dlp.YoutubeDL", return_value=_mock_ydl(info)) as ydl_cls:
        await YouTubeProvider().extract("https://youtube.com/playlist?list=x")

    opts = ydl_cls.call_args.args[0]
    assert opts["extract_flat"] == "in_playlist"
    assert opts["ignoreerrors"] is True


@pytest.mark.asyncio
async def test_extract_large_playlist_is_not_capped():
    entries = [_flat_entry(i) for i in range(1, 501)]
    info = {"_type": "playlist", "title": "Big", "playlist_count": 500, "entries": entries}
    with patch("yt_dlp.YoutubeDL", return_value=_mock_ydl(info)):
        result = await YouTubeProvider().extract("https://youtube.com/playlist?list=x")

    assert len(result.tracks) == 500
    assert result.tracks[0].artist == "Artist 1"
    assert result.tracks[499].title == "Song 500"


@pytest.mark.asyncio
async def test_extract_warns_when_playlist_incomplete(caplog):
    entries = [_flat_entry(i) for i in range(1, 101)]
    info = {"_type": "playlist", "title": "Big", "playlist_count": 542, "entries": entries}
    with (
        patch("yt_dlp.YoutubeDL", return_value=_mock_ydl(info)),
        caplog.at_level(logging.WARNING, logger="dj_dl.providers.youtube"),
    ):
        result = await YouTubeProvider().extract("https://youtube.com/playlist?list=x")

    assert len(result.tracks) == 100
    assert "got 100 of 542 tracks" in caplog.text


@pytest.mark.asyncio
async def test_extract_returns_no_tracks_when_extraction_fails(caplog):
    with (
        patch("yt_dlp.YoutubeDL", return_value=_mock_ydl(None)),
        caplog.at_level(logging.WARNING, logger="dj_dl.providers.youtube"),
    ):
        result = await YouTubeProvider().extract("https://www.youtube.com/watch?v=aaaaaaaaaaa")

    assert result.tracks == []
    assert result.source == "youtube"
    assert "No metadata extracted" in caplog.text


def test_entry_to_track_falls_back_to_uploader():
    entry = {"url": "https://youtu.be/x", "title": "No Dash Title", "uploader": "Some Channel"}
    track = YouTubeProvider()._entry_to_track(entry, 1)
    assert track.artist == "Some Channel"
    assert track.title == "No Dash Title"


def test_backfill_track_fills_missing_metadata():
    track = Track(title="Song", artist="Unknown Artist")
    info = {
        "artist": "Real Artist",
        "album": "Real Album",
        "genre": "House",
        "release_year": 2024,
        "isrc": "USRC12345678",
        "duration": 180,
        "thumbnails": [{"url": "https://img/low.jpg"}, {"url": "https://img/high.jpg"}],
    }
    YouTubeProvider()._backfill_track(track, info)
    assert track.artist == "Real Artist"
    assert track.album == "Real Album"
    assert track.genre == "House"
    assert track.year == 2024
    assert track.isrc == "USRC12345678"
    assert track.duration_ms == 180000
    assert track.cover_url == "https://img/high.jpg"


def test_backfill_track_keeps_existing_metadata():
    track = Track(title="Song", artist="Known Artist", album="Known Album", year=2020)
    info = {"artist": "Other", "album": "Other Album", "release_year": 1999}
    YouTubeProvider()._backfill_track(track, info)
    assert track.artist == "Known Artist"
    assert track.album == "Known Album"
    assert track.year == 2020
