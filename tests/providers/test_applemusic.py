import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
import structlog
from gamdl.api import AppleMusicApi, GamdlApiResponseError

from dj_dl.config import Config
from dj_dl.downloader import DownloadJob, DownloadManager
from dj_dl.providers.applemusic import AppleMusicProvider
from dj_dl.providers.base import ProviderError, Track

SONG_URL = "https://music.apple.com/cl/song/chanel-phulla-remix-mixed/1790947039"


class _FakeSession:
    """Stands in for gamdl's AppleMusicApi: the account flag and the HTTP client it holds."""

    def __init__(self, *, active_subscription: bool) -> None:
        self.active_subscription = active_subscription
        self.client = SimpleNamespace(aclose=self._aclose)
        self.closed = False

    async def _aclose(self) -> None:
        self.closed = True


@pytest.fixture
def provider():
    return AppleMusicProvider()


def test_can_handle_apple_urls(provider):
    assert provider.can_handle("https://music.apple.com/us/album/xxx/1624945511")
    assert provider.can_handle("https://music.apple.com/us/playlist/pl.xxx")
    assert provider.can_handle("https://music.apple.com/us/song/xxx/1624945520")
    assert not provider.can_handle("https://open.spotify.com/track/xxx")


def test_parse_apple_url(provider):
    info = provider._parse_url("https://music.apple.com/us/album/name/1624945511")
    assert info["type"] == "album"
    assert info["id"] == "1624945511"
    assert info["storefront"] == "us"


@pytest.mark.asyncio
async def test_extract_without_a_saved_token_says_to_run_auth(provider):
    with pytest.raises(ProviderError, match="djdl auth"):
        await provider.extract(SONG_URL)


@pytest.mark.asyncio
async def test_extract_reports_a_token_apple_rejects(monkeypatch):
    async def rejected(**kwargs: str) -> None:
        raise GamdlApiResponseError("Error fetching account info", status_code=403)

    monkeypatch.setattr(AppleMusicApi, "create_from_netscape_cookies", rejected)

    with pytest.raises(ProviderError, match="rejected the saved token.*djdl auth"):
        await AppleMusicProvider(cookies_path="cookies.txt").extract(SONG_URL)


@pytest.mark.asyncio
async def test_extract_reports_an_account_without_a_subscription(monkeypatch):
    async def no_subscription(**kwargs: str) -> _FakeSession:
        return _FakeSession(active_subscription=False)

    monkeypatch.setattr(AppleMusicApi, "create_from_netscape_cookies", no_subscription)

    with pytest.raises(ProviderError, match="no active subscription"):
        await AppleMusicProvider(cookies_path="cookies.txt").extract(SONG_URL)


@pytest.mark.asyncio
async def test_extract_closes_the_apple_music_session_when_it_fails(monkeypatch):
    session = _FakeSession(active_subscription=False)

    async def create(**kwargs: str) -> _FakeSession:
        return session

    monkeypatch.setattr(AppleMusicApi, "create_from_netscape_cookies", create)

    with pytest.raises(ProviderError):
        await AppleMusicProvider(cookies_path="cookies.txt").extract(SONG_URL)

    assert session.closed


def test_downloaded_file_is_skipped_on_the_next_run(tmp_path):
    # gamdl names its own file; the skip check of the next run looks for the track's name.
    downloaded = tmp_path / "01 Example Song.m4a"
    downloaded.touch()
    output_dir = tmp_path / "music"
    output_dir.mkdir()
    track = Track(title="Example Song", artist="Example Artist")

    saved = AppleMusicProvider()._move_to_output(downloaded, output_dir, track)

    job = DownloadJob(track=track, output_dir=output_dir)
    assert DownloadManager(Config(output_dir=output_dir))._existing_file(job) == saved


@pytest.mark.asyncio
async def test_concurrent_downloads_keep_their_own_files(tmp_path, monkeypatch):
    async def fake_gamdl(self, *, track: Track, temp_dir: Path, cookies_path: str) -> None:
        # A real download yields to the event loop long before its file exists.
        await asyncio.sleep(0)
        album_dir = temp_dir / "Example Artist" / "Example Album"
        album_dir.mkdir(parents=True, exist_ok=True)
        (album_dir / f"{track.title}.m4a").write_text(track.title)
        await asyncio.sleep(0)

    monkeypatch.setattr(AppleMusicProvider, "_download_with_gamdl", fake_gamdl)
    provider = AppleMusicProvider(cookies_path="cookies.txt")
    tracks = [Track(title=f"Song {n}", artist="Example Artist") for n in (1, 2)]

    saved = await asyncio.gather(*(provider.download(t, tmp_path) for t in tracks))

    # Each fake file holds its track's title in place of audio.
    assert [path.read_text() for path in saved] == ["Song 1", "Song 2"]


def test_gamdl_debug_logs_stay_out_of_the_console(capsys):
    # gamdl logs the Apple Music account details at debug level.
    log = structlog.get_logger("gamdl.api.apple_music")

    log.debug("success", account_info={"subscription": "active"})
    log.warning("storefront mismatch")

    out = capsys.readouterr().out
    assert "account_info" not in out
    assert "storefront mismatch" in out
