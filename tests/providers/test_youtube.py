import pytest

from dj_dl.providers.youtube import YouTubeProvider


@pytest.fixture
def provider():
    return YouTubeProvider()


def test_can_handle_youtube_urls(provider):
    assert provider.can_handle("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert provider.can_handle("https://youtu.be/dQw4w9WgXcQ")
    assert provider.can_handle("https://www.youtube.com/playlist?list=PLxxx")
    assert provider.can_handle("https://music.youtube.com/watch?v=xxx")
    assert not provider.can_handle("https://open.spotify.com/track/xxx")


@pytest.mark.asyncio
async def test_extract_single_track(provider):
    result = await provider.extract("https://www.youtube.com/watch?v=UiPfIjGE0XE")
    assert len(result.tracks) == 1
    track = result.tracks[0]
    assert track.title
    assert track.download_url


@pytest.mark.asyncio
async def test_extract_playlist(provider):
    url = "https://youtube.com/playlist?list=PLK02ND1lAn-mcklLYEzO11gbdoBKTmtwi"
    result = await provider.extract(url)
    assert len(result.tracks) > 1
    assert result.playlist_name
