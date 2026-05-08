from pathlib import Path

from dj_dl.config import Config
from dj_dl.downloader import DownloadJob, DownloadManager, JobStatus
from dj_dl.providers.base import ProviderResult, Track


def test_download_job_creation():
    track = Track(title="Test", artist="Artist")
    job = DownloadJob(track=track, output_dir=Path("/tmp/test"))
    assert job.status == JobStatus.pending


def test_organize_path_flat():
    config = Config(output_dir=Path("/tmp/music"))
    manager = DownloadManager(config)
    track = Track(title="Song", artist="Artist Name", album="Album Name")
    result = ProviderResult(tracks=[track], source="spotify")
    path = manager._organize_path(track, result)
    assert path == Path("/tmp/music")


def test_sanitize_folder_name():
    manager = DownloadManager(Config())
    assert manager._sanitize('Artist: "Name"') == "Artist Name"
    assert manager._sanitize("file/name") == "filename"
    assert manager._sanitize("") == "Unknown"
