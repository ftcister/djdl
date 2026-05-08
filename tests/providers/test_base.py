from dj_dl.providers.base import BaseProvider, ProviderResult, Track, detect_provider


class DummyProvider(BaseProvider):
    name = "dummy"

    def can_handle(self, url: str) -> bool:
        return "dummy.com" in url

    async def extract(self, url: str) -> ProviderResult:
        return ProviderResult(
            tracks=[Track(title="Test", artist="Artist", source_url=url)],
            playlist_name="Test Playlist",
        )

    async def download(self, track, output_dir, progress_callback=None):
        pass


def test_can_handle():
    p = DummyProvider()
    assert p.can_handle("https://dummy.com/track/1")
    assert not p.can_handle("https://spotify.com/track/1")


def test_detect_provider():
    assert detect_provider("https://www.youtube.com/watch?v=xxx") == "youtube"
    assert detect_provider("https://open.spotify.com/track/xxx") == "spotify"
    assert detect_provider("https://music.apple.com/us/album/xxx") == "apple_music"
    assert detect_provider("https://example.com") == "unknown"
