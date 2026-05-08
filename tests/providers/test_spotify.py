import pytest

from dj_dl.providers.spotify import SpotifyProvider


@pytest.fixture
def provider():
    return SpotifyProvider()


def test_can_handle_spotify_urls(provider):
    assert provider.can_handle("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
    assert provider.can_handle("https://open.spotify.com/album/xxx")
    assert provider.can_handle("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
    assert not provider.can_handle("https://www.youtube.com/watch?v=xxx")


def test_parse_spotify_url(provider):
    result = provider._parse_url("https://open.spotify.com/track/abc123")
    assert result == ("track", "abc123")
    result = provider._parse_url("https://open.spotify.com/playlist/xyz?si=foo")
    assert result == ("playlist", "xyz")


@pytest.mark.asyncio
async def test_extract_spotify_track(provider):
    url = "https://open.spotify.com/track/1LV5G400jD3Ytvyv6Dlkym"
    result = await provider.extract(url)
    assert len(result.tracks) >= 1
    assert result.tracks[0].title


@pytest.mark.asyncio
async def test_extract_spotify_playlist(provider):
    url = "https://open.spotify.com/playlist/6GroeYfHlwE58jF8qMASdy"
    result = await provider.extract(url)
    assert len(result.tracks) >= 1
    assert result.playlist_name
