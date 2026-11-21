import asyncio
from collections.abc import Callable
from pathlib import Path

import pytest

from dj_dl.config import Config
from dj_dl.downloader import DownloadJob, DownloadManager, JobStatus
from dj_dl.providers.base import BaseProvider, ProviderResult, Track


class _RecordingProvider(BaseProvider):
    """Saves an empty `<title> - <artist>.m4a` per download and records each requested URL."""

    name = "recording"

    def __init__(self) -> None:
        self.downloaded: list[str] = []

    def can_handle(self, url: str) -> bool:
        return True

    async def extract(self, url: str) -> ProviderResult:
        return ProviderResult()

    async def download(
        self,
        track: Track,
        output_dir: Path,
        progress_callback: Callable | None = None,
    ) -> Path:
        self.downloaded.append(track.download_url)
        # A real download yields to the event loop long before its file exists.
        await asyncio.sleep(0)
        path = output_dir / f"{track.title} - {track.artist}.m4a"
        path.touch()
        return path


def test_download_job_creation():
    track = Track(title="Test", artist="Artist")
    job = DownloadJob(track=track, output_dir=Path("/tmp/test"))
    assert job.status == JobStatus.pending


def test_file_already_exists_matches_sanitized_filename(tmp_path):
    config = Config(output_dir=tmp_path)
    manager = DownloadManager(config)
    # files are saved with unsafe characters stripped, so the skip check must
    # compare sanitized names too
    (tmp_path / "What Is Love - JaxJon.m4a").touch()
    track = Track(title="What Is Love?", artist="Jax/Jon")
    job = DownloadJob(track=track, output_dir=tmp_path)
    assert manager._file_already_exists(job) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "second_url",
    [
        pytest.param("https://www.youtube.com/watch?v=aaaaaaaaaaa", id="same-video-listed-twice"),
        pytest.param("https://www.youtube.com/watch?v=bbbbbbbbbbb", id="other-video-same-name"),
    ],
)
async def test_tracks_saved_under_the_same_name_are_downloaded_once(tmp_path, second_url):
    first_url = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    tracks = [
        Track(title="Example Song", artist="Example Artist", download_url=first_url),
        Track(title="Example Song", artist="Example Artist", download_url=second_url),
    ]
    provider = _RecordingProvider()
    # Two download slots let both tracks start before either file exists.
    config = Config(output_dir=tmp_path, concurrent_downloads=2, auto_analyze=False)
    manager = DownloadManager(config)

    report = await manager.download(ProviderResult(tracks=tracks, source="youtube"), provider)

    assert provider.downloaded == [first_url]
    assert report.completed == 1
    assert report.skipped == 1


def test_organize_path_flat():
    config = Config(output_dir=Path("/tmp/music"))
    manager = DownloadManager(config)
    track = Track(title="Song", artist="Artist Name", album="Album Name")
    result = ProviderResult(tracks=[track], source="spotify")
    path = manager._organize_path(track, result)
    assert path == Path("/tmp/music")
