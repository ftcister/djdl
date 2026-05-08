import csv
from pathlib import Path

import pytest

from dj_dl.config import Config
from dj_dl.downloader import DownloadManager
from dj_dl.providers.applemusic import AppleMusicProvider
from dj_dl.providers.base import detect_provider
from dj_dl.providers.spotify import SpotifyProvider
from dj_dl.providers.youtube import YouTubeProvider


def load_fixtures():
    fixtures_path = Path(__file__).parent / "fixtures" / "urls.csv"
    with open(fixtures_path) as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("fixture", load_fixtures())
def test_provider_detection(fixture):
    assert detect_provider(fixture["url"]) == fixture["service"]


@pytest.mark.parametrize("fixture", [f for f in load_fixtures() if f["type"] == "track"])
@pytest.mark.asyncio
async def test_extract_track(fixture):
    service = fixture["service"]
    url = fixture["url"]

    if service == "youtube":
        provider = YouTubeProvider()
    elif service == "spotify":
        provider = SpotifyProvider()
    elif service == "apple_music":
        from dj_dl.config import load_config

        config = load_config()
        provider = AppleMusicProvider(cookies_path=config.apple_music.cookies_path)
    else:
        pytest.skip(f"Unknown service: {service}")

    result = await provider.extract(url)
    if service == "apple_music" and not result.tracks:
        pytest.skip("Apple Music requires authentication")
    assert len(result.tracks) >= 1
    assert result.tracks[0].title


@pytest.mark.parametrize("fixture", [f for f in load_fixtures() if f["type"] == "playlist"])
@pytest.mark.asyncio
async def test_extract_playlist(fixture):
    service = fixture["service"]
    url = fixture["url"]

    if service == "youtube":
        provider = YouTubeProvider()
    elif service == "spotify":
        provider = SpotifyProvider()
    elif service == "apple_music":
        from dj_dl.config import load_config

        config = load_config()
        provider = AppleMusicProvider(cookies_path=config.apple_music.cookies_path)
    else:
        pytest.skip(f"Unknown service: {service}")

    result = await provider.extract(url)
    if service == "apple_music" and not result.tracks:
        pytest.skip("Apple Music requires authentication")
    assert len(result.tracks) >= 1


@pytest.mark.parametrize("fixture", load_fixtures())
@pytest.mark.asyncio
async def test_download_track(fixture):
    service = fixture["service"]
    url = fixture["url"]

    if service == "youtube":
        provider = YouTubeProvider()
    elif service == "spotify":
        provider = SpotifyProvider()
    elif service == "apple_music":
        from dj_dl.config import load_config

        config = load_config()
        provider = AppleMusicProvider(cookies_path=config.apple_music.cookies_path)
    else:
        pytest.skip(f"Unknown service: {service}")

    result = await provider.extract(url)
    if not result.tracks:
        pytest.skip("No tracks found")

    config = Config(output_dir=Path(__file__).parent / "results", organize_by="none")
    manager = DownloadManager(config)

    report = await manager.download(result, provider)
    assert report.completed > 0 or report.skipped > 0
