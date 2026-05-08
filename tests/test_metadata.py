import asyncio
import subprocess
import tempfile
from pathlib import Path

from dj_dl.metadata import embed_metadata
from dj_dl.providers.base import Track


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
