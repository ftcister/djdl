# AGENTS.md

## Project Overview

djdl is a multi-platform DJ music downloader CLI tool. Users interact with it via the `djdl` terminal command. It downloads tracks and playlists from YouTube, Spotify, and Apple Music, outputting AAC M4A files with full metadata, BPM/key analysis, and Rekordbox XML export.

**User-facing command:** `djdl` (installed via `uv tool install`)
**Installation:** `curl -sL .../install.sh | bash`

## Architecture

### Tech Stack
- Python 3.12+
- uv (package manager)
- typer (CLI framework)
- rich (terminal UI)
- yt-dlp (YouTube downloading)
- gamdl (Apple Music downloading)
- mutagen (metadata embedding)
- librosa (BPM/key analysis)
- httpx (HTTP client)

### Project Structure
```
dj_dl/
  __init__.py         # Version info
  cli.py              # Typer CLI commands
  config.py           # YAML config with dataclasses
  downloader.py       # DownloadManager with asyncio concurrency
  metadata.py         # M4A/MP3/FLAC metadata embedder
  analyzer.py         # BPM and key detection
  rekordbox_xml.py    # Rekordbox XML export
  auth.py             # Apple Music browser auth
  providers/
    __init__.py
    base.py           # BaseProvider ABC, Track/ProviderResult
    youtube.py        # YouTubeProvider (yt-dlp API)
    spotify.py        # SpotifyProvider (API/embed → YouTube)
    applemusic.py     # AppleMusicProvider (gamdl)
tests/
  fixtures/
    urls.csv          # Test URLs for all platforms
```

### Key Patterns

**Provider Pattern**: All providers extend `BaseProvider` with:
- `can_handle(url: str) -> bool` — URL detection
- `extract(url: str) -> ProviderResult` — Metadata extraction
- `download(track, output_dir) -> Path` — Audio download

**Config**: YAML at `~/.config/dj-dl/config.yaml` with dataclasses:
```python
@dataclass
class Config:
    output_dir: Path = ~/Music/DJ
    organize_by: str = "none"  # Always flat output
    apple_music: AppleMusicConfig
```

**Flat Output**: All downloads go directly to `config.output_dir`, no subfolders.

## Development Workflow

All development tasks are run through the Makefile.

### Running Tests
```bash
make test
```

### Lint/Format
```bash
make lint
make lint-fix
make format
```

### Type Check
```bash
make typecheck
```

### Full Quality Check
```bash
make check      # lint + format-check + typecheck
make validate   # lint-fix + format + typecheck + test
```

### Adding Dependencies
```bash
uv add <package>
```

## Testing

- 44 tests, all passing
- Integration tests use real URLs (YouTube/Spotify public, Apple Music with auth)
- Apple Music tests skip if no auth configured
- Test fixtures in `tests/fixtures/urls.csv`

## Auth System

**YouTube/Spotify**: No auth required. Spotify uses public embed pages as fallback.

**Apple Music**: Requires `media-user-token` cookie from browser.
- User runs `djdl auth`
- Interactive prompt guides cookie extraction
- Cookie saved to `~/.config/dj-dl/apple_music_cookies.txt`
- Token checked before overwriting existing auth

## Known Limitations

1. **Apple Music**: Requires active subscription + cookie export
2. **Spotify**: Audio sourced from YouTube (not native Spotify streams)
3. **BPM/Key**: Uses librosa which may fallback to audioread for M4A
4. **Type Checker**: gamdl types may show errors in ty (external library)

## Extension Points

**Adding a new provider**:
1. Create `dj_dl/providers/<name>.py`
2. Extend `BaseProvider`
3. Implement `can_handle`, `extract`, `download`
4. Add tests in `tests/providers/test_<name>.py`
5. Register in `dj_dl/cli.py:get_provider()`

**Adding a new CLI command**:
1. Add `@app.command()` in `dj_dl/cli.py`
2. Add to `KNOWN_COMMANDS` set (this is required for URL auto-detection to work correctly)
3. Add tests if needed

## Dependencies with Versions

All runtime dependencies use `~=` (compatible release) in `pyproject.toml`:
- yt-dlp ~= 2026.3.17
- gamdl ~= 3.5
- mutagen ~= 1.47.0
- httpx ~= 0.28.1
- typer ~= 0.25.1
- rich ~= 15.0.0
- pyyaml ~= 6.0.3
- spotipy ~= 2.26.0
- ytmusicapi ~= 1.12.0
- librosa ~= 0.11.0
- browser-cookie3 ~= 0.20.1
- playwright ~= 1.59.0

## Installation & Distribution

**Primary install method (for users):**
```bash
curl -sL https://raw.githubusercontent.com/ftcister/ytdl/main/install.sh | bash
```

This installs `djdl` via `uv tool install` (isolated environment). The binary is placed in `~/.local/bin` and `~/.local/bin` is added to PATH if missing.

**Files involved:**
- `install.sh` — One-liner installer script