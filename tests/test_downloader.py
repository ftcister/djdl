import asyncio
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree

import pytest
from yt_dlp.utils import DownloadError

from dj_dl.config import Config
from dj_dl.downloader import DownloadJob, DownloadManager, JobStatus
from dj_dl.providers.base import BaseProvider, ProviderResult, Track

HTTP_403 = "ERROR: unable to download video data: HTTP Error 403: Forbidden"


class _RecordingProvider(BaseProvider):
    """Saves an empty `<title> - <artist>.m4a` per download and records each attempted URL.

    A URL in `failures` fails that many attempts with YouTube's 403 before it downloads.
    """

    name = "recording"

    def __init__(self, *, failures: dict[str, int] | None = None) -> None:
        self.attempts: list[str] = []
        self._failures_left = dict(failures or {})

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
        self.attempts.append(track.download_url)
        # A real download yields to the event loop long before its file exists.
        await asyncio.sleep(0)
        if self._failures_left.get(track.download_url, 0) > 0:
            self._failures_left[track.download_url] -= 1
            raise DownloadError(HTTP_403)
        path = output_dir / f"{track.title} - {track.artist}.m4a"
        path.touch()
        return path


def _xml_playlist_paths(xml_path: Path) -> list[Path]:
    """Files of the playlist in a Rekordbox XML, in playlist order."""
    root = ElementTree.parse(xml_path).getroot()
    paths_by_id = {
        track.attrib["TrackID"]: Path(track.attrib["Location"].removeprefix("file://localhost"))
        for track in root.iterfind("COLLECTION/TRACK")
    }
    return [
        paths_by_id[track.attrib["Key"]] for track in root.iterfind("PLAYLISTS/NODE/NODE/TRACK")
    ]


def test_download_job_creation():
    track = Track(title="Test", artist="Artist")
    job = DownloadJob(track=track, output_dir=Path("/tmp/test"))
    assert job.status == JobStatus.pending


def test_existing_file_matches_sanitized_filename(tmp_path):
    config = Config(output_dir=tmp_path)
    manager = DownloadManager(config)
    # files are saved with unsafe characters stripped, so the skip check must
    # compare sanitized names too
    existing = tmp_path / "What Is Love - JaxJon.m4a"
    existing.touch()
    track = Track(title="What Is Love?", artist="Jax/Jon")
    job = DownloadJob(track=track, output_dir=tmp_path)
    assert manager._existing_file(job) == existing


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

    assert provider.attempts == [first_url]
    assert report.completed == 1
    assert report.skipped == 1


@pytest.mark.asyncio
async def test_error_names_the_track_that_failed(tmp_path):
    url = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    tracks = [Track(title="Example Song", artist="Example Artist", download_url=url)]
    provider = _RecordingProvider(failures={url: 2})
    manager = DownloadManager(Config(output_dir=tmp_path, auto_analyze=False))

    report = await manager.download(ProviderResult(tracks=tracks, source="youtube"), provider)

    assert report.failed == 1
    [error] = report.errors
    assert "Example Song - Example Artist" in error
    assert "HTTP Error 403: Forbidden" in error


@pytest.mark.asyncio
async def test_failed_download_gets_one_more_attempt_after_the_batch(tmp_path):
    first_url = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    second_url = "https://www.youtube.com/watch?v=bbbbbbbbbbb"
    tracks = [
        Track(title="First Song", artist="Example Artist", download_url=first_url),
        Track(title="Second Song", artist="Example Artist", download_url=second_url),
    ]
    provider = _RecordingProvider(failures={first_url: 1})
    # One download slot makes the attempt order deterministic.
    config = Config(output_dir=tmp_path, concurrent_downloads=1, auto_analyze=False)

    report = await DownloadManager(config).download(
        ProviderResult(tracks=tracks, source="youtube"), provider
    )

    assert provider.attempts == [first_url, second_url, first_url]
    assert (report.completed, report.failed, report.errors) == (2, 0, [])


@pytest.mark.asyncio
async def test_download_failing_both_attempts_is_reported_once(tmp_path):
    url = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
    tracks = [Track(title="Example Song", artist="Example Artist", download_url=url)]
    provider = _RecordingProvider(failures={url: 2})
    manager = DownloadManager(Config(output_dir=tmp_path, auto_analyze=False))

    report = await manager.download(ProviderResult(tracks=tracks, source="youtube"), provider)

    assert provider.attempts == [url, url]
    assert (report.completed, report.failed, len(report.errors)) == (0, 1, 1)


@pytest.mark.asyncio
async def test_rekordbox_xml_lists_tracks_already_on_disk(tmp_path):
    # A rerun that fetches only the tracks that failed must still export the whole playlist.
    existing = tmp_path / "Old Song - Example Artist.m4a"
    existing.touch()
    tracks = [
        Track(title="Old Song", artist="Example Artist", download_url="https://youtu.be/a"),
        Track(title="New Song", artist="Example Artist", download_url="https://youtu.be/b"),
    ]
    manager = DownloadManager(Config(output_dir=tmp_path, auto_analyze=False))

    await manager.download(
        ProviderResult(tracks=tracks, playlist_name="Example", source="youtube"),
        _RecordingProvider(),
    )

    assert _xml_playlist_paths(tmp_path / f"{tmp_path.name}.xml") == [
        existing.resolve(),
        (tmp_path / "New Song - Example Artist.m4a").resolve(),
    ]


def test_organize_path_flat():
    config = Config(output_dir=Path("/tmp/music"))
    manager = DownloadManager(config)
    track = Track(title="Song", artist="Artist Name", album="Album Name")
    result = ProviderResult(tracks=[track], source="spotify")
    path = manager._organize_path(track, result)
    assert path == Path("/tmp/music")
