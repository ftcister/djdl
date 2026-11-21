from pathlib import Path

from dj_dl.auth import _save_cookies


def test_save_cookies_creates_netscape_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    path = _save_cookies("test_token_value")

    assert Path(path).exists()
    content = Path(path).read_text()
    assert "media-user-token\ttest_token_value" in content
    assert "# Netscape HTTP Cookie File" in content


def test_save_cookies_makes_the_token_readable_only_by_its_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # A file left world-readable by an earlier save must be tightened too.
    existing = tmp_path / ".config" / "dj-dl" / "apple_music_cookies.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("old")
    existing.chmod(0o644)

    path = _save_cookies("test_token_value")

    assert Path(path).stat().st_mode & 0o777 == 0o600
