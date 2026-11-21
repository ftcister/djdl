import subprocess
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from dj_dl.cli import app
from dj_dl.config import Config
from dj_dl.downloader import DownloadReport
from dj_dl.providers.base import ProviderError, ProviderResult, Track

runner = CliRunner()

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@contextmanager
def _stub_download(config, report, tracks=None, *, extract_error: ProviderError | None = None):
    provider = MagicMock()
    provider.name = "youtube"
    provider.extract = AsyncMock(
        return_value=ProviderResult(
            tracks=[Track(title="Song", artist="Artist")] if tracks is None else tracks,
            source="youtube",
        ),
        side_effect=extract_error,
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


def test_download_shows_the_provider_error_and_exits_nonzero(tmp_path):
    error = ProviderError("Apple Music rejected the saved token (HTTP 403). Run: djdl auth")
    with _stub_download(Config(output_dir=tmp_path), DownloadReport(), extract_error=error):
        result = runner.invoke(app, ["download", URL])
    assert result.exit_code == 1
    assert "Apple Music rejected the saved token (HTTP 403). Run: djdl auth" in result.output


def test_download_exits_nonzero_when_no_tracks_found(tmp_path):
    with _stub_download(Config(output_dir=tmp_path), DownloadReport(), tracks=[]):
        result = runner.invoke(app, ["download", URL])
    assert result.exit_code == 1
    assert "No tracks found" in result.output


def test_output_dir_option_overrides_the_configured_folder(tmp_path):
    configured = tmp_path / "configured"
    requested = tmp_path / "requested"
    config = Config(output_dir=configured)
    with _stub_download(config, DownloadReport(total=1, completed=1)) as manager_cls:
        result = runner.invoke(app, ["download", URL, "--output-dir", str(requested)])

    assert result.exit_code == 0
    # The manager is built from the overridden config, so audio and XML both land here.
    assert manager_cls.call_args.args[0].output_dir == requested.resolve()
    assert requested.is_dir()


def test_output_dir_option_is_not_written_back_to_config(tmp_path):
    config = Config(output_dir=tmp_path / "configured")
    with (
        _stub_download(config, DownloadReport(total=1, completed=1)),
        patch.object(Config, "save") as save,
    ):
        result = runner.invoke(app, ["download", URL, "--output-dir", str(tmp_path / "requested")])

    assert result.exit_code == 0
    save.assert_not_called()


def test_update_upgrades_yt_dlp_and_gamdl_when_reinstalling(tmp_path):
    (tmp_path / ".djdl" / ".git").mkdir(parents=True)
    ok = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with (
        patch.object(Path, "home", return_value=tmp_path),
        patch("dj_dl.cli.subprocess.run", return_value=ok) as run,
    ):
        result = runner.invoke(app, ["update"])

    assert result.exit_code == 0
    # The last call reinstalls djdl from the pulled clone.
    reinstall = run.call_args_list[-1].args[0]
    assert reinstall[:3] == ["uv", "tool", "install"]
    upgraded = [reinstall[i + 1] for i, arg in enumerate(reinstall) if arg == "--upgrade-package"]
    assert sorted(upgraded) == ["gamdl", "yt-dlp"]
