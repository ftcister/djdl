from pathlib import Path

import pytest

from dj_dl.config import Config
from dj_dl.downloader import DownloadManager
from dj_dl.providers.youtube import YouTubeProvider


@pytest.mark.asyncio
async def test_download_generates_rekordbox_xml():
    output_dir = Path(__file__).parent / "results"
    output_dir.mkdir(exist_ok=True)
    config = Config(output_dir=output_dir, organize_by="none")
    manager = DownloadManager(config)
    provider = YouTubeProvider()

    url = "https://www.youtube.com/watch?v=UiPfIjGE0XE"
    result = await provider.extract(url)
    assert result.tracks, "No tracks found"

    track = result.tracks[0]
    for existing in output_dir.glob("*.m4a"):
        if track.title in existing.name or (track.artist and track.artist in existing.name):
            existing.unlink()

    report = await manager.download(result, provider)
    assert report.completed > 0, "Download did not complete"

    xml_path = output_dir / "results.xml"

    assert xml_path.exists(), f"{xml_path.name} was not generated in output directory"
    content = xml_path.read_text()
    assert "<DJ_PLAYLISTS" in content
    assert "<TRACK TrackID=" in content
    assert report.files[0].stem in content or result.tracks[0].title in content
