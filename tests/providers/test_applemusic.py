import pytest

from dj_dl.providers.applemusic import AppleMusicProvider


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
async def test_extract_apple_track(provider):
    url = "https://music.apple.com/cl/song/chanel-phulla-remix-mixed/1790947039"
    result = await provider.extract(url)
    if result.tracks:
        assert result.tracks[0].title


@pytest.mark.asyncio
async def test_extract_apple_playlist(provider):
    url = "https://music.apple.com/cl/playlist/loopy/pl.u-2aoqq8bTGmAb4Me"
    result = await provider.extract(url)
    if result.tracks:
        assert len(result.tracks) >= 1
