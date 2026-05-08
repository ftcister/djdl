from pathlib import Path

from dj_dl.auth import _save_cookies


def test_save_cookies_creates_netscape_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    path = _save_cookies("test_token_value")

    assert Path(path).exists()
    content = Path(path).read_text()
    assert "media-user-token\ttest_token_value" in content
    assert "# Netscape HTTP Cookie File" in content
