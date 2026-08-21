from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from dj_dl.cli import app
from dj_dl.config import Config
from dj_dl.downloader import DownloadReport
from dj_dl.providers.base import ProviderResult, Track

runner = CliRunner()

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@contextmanager
def _stub_download(config, report, tracks=None):
    provider = MagicMock()
    provider.name = "youtube"
    provider.extract = AsyncMock(
        return_value=ProviderResult(
            tracks=[Track(title="Song", artist="Artist")] if tracks is None else tracks,
            source="youtube",
        )
    )
    manager = MagicMock()
    manager.download = AsyncMock(return_value=report)
    with (
        patch("dj_dl.cli.load_config", return_value=config),
        patch("dj_dl.cli.get_provider", return_value=provider),
        patch("dj_dl.cli.DownloadManager", return_value=manager) as manager_cls,
    ):
        yield manager_cls


def test_download_exits_nonzero_when_a_track_fails(tmp_path):
    report = DownloadReport(total=1, failed=1, errors=["HTTP Error 403: Forbidden"])
    with _stub_download(Config(output_dir=tmp_path), report):
        result = runner.invoke(app, ["download", URL])
    assert result.exit_code == 1
    # The report stays visible even though the command now signals failure.
    assert "403" in result.output


def test_download_exits_zero_when_all_tracks_complete(tmp_path):
    with _stub_download(Config(output_dir=tmp_path), DownloadReport(total=1, completed=1)):
        result = runner.invoke(app, ["download", URL])
    assert result.exit_code == 0


def test_download_exits_zero_when_a_track_is_skipped(tmp_path):
    # A track already on disk is not a failure, so the exit status must stay clean.
    with _stub_download(Config(output_dir=tmp_path), DownloadReport(total=1, skipped=1)):
        result = runner.invoke(app, ["download", URL])
    assert result.exit_code == 0


def test_download_exits_nonzero_when_no_tracks_found(tmp_path):
    with _stub_download(Config(output_dir=tmp_path), DownloadReport(), tracks=[]):
        result = runner.invoke(app, ["download", URL])
    assert result.exit_code == 1
    assert "No tracks found" in result.output
