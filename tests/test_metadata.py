import asyncio
import io
import subprocess
import tempfile
from pathlib import Path

import pytest
from mutagen.mp4 import MP4, MP4Cover
from PIL import Image

from dj_dl.metadata import embed_metadata
from dj_dl.providers.base import Track


def _make_m4a(path: Path) -> None:
    """Write one second of AAC audio, so mutagen has a real file to tag."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "aac"]
        + [str(path)],
        capture_output=True,
        check=True,
    )


def _serve_cover(monkeypatch: pytest.MonkeyPatch, data: bytes) -> None:
    async def _download_cover(url: str) -> bytes:
        return data

    monkeypatch.setattr("dj_dl.metadata._download_cover", _download_cover)


def test_embed_metadata_m4a():
    with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(tmp_path),
        ],
        capture_output=True,
    )

    track = Track(
        title="Test Track",
        artist="Test Artist",
        album="Test Album",
        track_number=5,
        genre="House",
        year=2024,
    )

    result = asyncio.run(embed_metadata(tmp_path, track))
    assert result.success

    from mutagen.mp4 import MP4

    audio = MP4(str(tmp_path))
    assert audio["\xa9nam"] == ["Test Track"]
    assert audio["\xa9ART"] == ["Test Artist"]
    assert audio["\xa9alb"] == ["Test Album"]
    assert audio["trkn"] == [(5, 0)]

    tmp_path.unlink()


def test_embed_metadata_handles_missing_file():
    result = asyncio.run(embed_metadata(Path("/nonexistent/file.m4a"), Track(title="x")))
    assert not result.success
    assert result.error is not None


@pytest.mark.parametrize("image_format", ["WEBP", "PNG"])
def test_cover_is_embedded_in_the_format_it_declares(tmp_path, monkeypatch, image_format):
    # YouTube answers its .jpg thumbnail URLs with WebP; 336x188 is the largest thumbnail
    # in a flat playlist entry.
    buffer = io.BytesIO()
    Image.new("RGB", (336, 188), "red").save(buffer, format=image_format)
    _serve_cover(monkeypatch, buffer.getvalue())
    audio_path = tmp_path / "song.m4a"
    _make_m4a(audio_path)
    track = Track(title="Song", cover_url="https://i.ytimg.com/vi/x/hqdefault.jpg")

    result = asyncio.run(embed_metadata(audio_path, track))

    assert result.success
    [cover] = MP4(str(audio_path))["covr"]
    # An M4A cover is declared JPEG or PNG, and players decode it as declared.
    assert (cover.imageformat, bytes(cover)[:3]) in {
        (MP4Cover.FORMAT_JPEG, b"\xff\xd8\xff"),
        (MP4Cover.FORMAT_PNG, b"\x89PN"),
    }


def test_unreadable_cover_is_left_out(tmp_path, monkeypatch):
    _serve_cover(monkeypatch, b"<html>not an image</html>")
    audio_path = tmp_path / "song.m4a"
    _make_m4a(audio_path)
    track = Track(title="Song", cover_url="https://example.com/cover.jpg")

    result = asyncio.run(embed_metadata(audio_path, track))

    assert result.success
    audio = MP4(str(audio_path))
    assert "covr" not in audio
    assert audio["\xa9nam"] == ["Song"]
