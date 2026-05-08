# djdl

Multi-platform DJ music downloader for YouTube, Spotify, and Apple Music. Downloads tracks and playlists at maximum Rekordbox-compatible quality (AAC M4A) with full metadata, BPM/key analysis, and automatic Rekordbox XML export.

## Features

- **YouTube** — Download single tracks or playlists
- **Spotify** — Extract metadata via API or embed fallback, match audio on YouTube
- **Apple Music** — Direct AAC 256kbps download with subscription auth
- **Flat output** — All files land directly in your configured folder
- **Metadata embedding** — Title, artist, album, artwork, genre via mutagen
- **BPM & Key analysis** — Automatic analysis with librosa, writes TBPM/TKEY tags
- **Rekordbox XML export** — Auto-generates XML for direct Rekordbox import

## Installation

### Prerequisites

You need three things installed **before** running the installer:

**1. Python 3.12+**

```bash
# macOS (usually pre-installed, or install via Homebrew)
brew install python

# Check version
python3 --version
```

**2. uv (Python package manager)**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**3. ffmpeg (audio conversion)**

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg
```

### Install djdl

```bash
curl -sL https://raw.githubusercontent.com/ftcister/ytdl/main/install.sh | bash
```

**What it installs:**
- Clones repo to `~/.ytdl/`
- Installs `djdl` via `uv tool install` (isolated environment, no global pollution)
- Ensures `~/.local/bin` is on your PATH

Then restart your terminal or run `source ~/.zshrc`.

## Usage

### 1. Install (one time)

```bash
curl -sL https://raw.githubusercontent.com/ftcister/ytdl/main/install.sh | bash
```

Restart your terminal or run `source ~/.zshrc`.

### 2. First time setup

```bash
# Tell djdl where to save your music
djdl set-folder ~/Music/DJ

# Authenticate Apple Music (only if you want Apple Music downloads)
djdl auth
```

**Apple Music auth** shows step-by-step instructions to copy your `media-user-token` cookie from the browser. Paste it and done. Never needed again unless you change accounts.

### 3. Download music (daily usage)

Paste any URL:

```bash
# YouTube
djdl https://www.youtube.com/watch?v=xxx

# Spotify (finds audio on YouTube, embeds Spotify metadata)
djdl https://open.spotify.com/track/xxx

# Apple Music (requires subscription + auth)
djdl https://music.apple.com/cl/song/xxx

# YouTube playlist
djdl https://youtube.com/playlist?list=xxx
```

**What happens:**
- Downloads AAC M4A at best available quality
- Embeds metadata (title, artist, album, artwork, genre)
- Analyzes BPM and key automatically
- Generates `DJ.xml` in your download folder for Rekordbox import
- All files land **flat** in your configured folder (no subfolders)

### 4. After downloading

```bash
open ~/Music/DJ
```

You will see:
```
Bass Rider - Sidney Charles.m4a
Knock2 - dashstar＊ (VIP).m4a
DJ.xml                      ← import this into Rekordbox
```

### 5. Update

```bash
djdl update                 # Pull latest changes and upgrade
```

### 6. Other commands

```bash
djdl analyze                # Analyze BPM/key for all tracks in folder
djdl --help                 # Show all available commands
```

### Authentication

| Platform | Required | Command |
|----------|----------|---------|
| YouTube | No | — |
| Spotify | No | Optional API keys for better metadata |
| Apple Music | Yes | `djdl auth` |

### Apple Music Auth

```bash
$ djdl auth
============================================================
  Apple Music Authentication
============================================================

To download from Apple Music, you need to provide your
media-user-token cookie.

Steps:
  1. Open Chrome and go to: https://music.apple.com
  2. Make sure you are logged in to your Apple Music account
  3. Press F12 (or right-click → Inspect)
  4. Go to: Application → Cookies → https://music.apple.com
  5. Find the row named: media-user-token
  6. Right-click on the value → Copy value

============================================================

Paste your media-user-token here: [paste-token]
```

### Command Reference

```
djdl <url>              # Download track/playlist (auto-detect platform)
djdl set-folder [path]  # Set output directory
djdl analyze [folder]   # Analyze BPM/key for all tracks
djdl auth               # Authenticate Apple Music
djdl update             # Update djdl to latest version
djdl --help             # Show help
```

## Development

All development tasks are run through the Makefile:

```bash
cd ~/.ytdl

# Install the tool locally
make install

# Run tests
make test

# Lint
make lint

# Auto-fix lint issues
make lint-fix

# Format
make format

# Type check
make typecheck

# Run all quality checks (lint + format-check + typecheck)
make check

# Full validation (lint-fix + format + typecheck + test)
make validate

# Clean test artifacts
make clean
```

### Makefile targets

```
make install        # Install djdl via uv tool install
make uninstall      # Remove djdl tool
make test           # Run all tests
make test-q         # Run tests quietly
make lint           # Run ruff linter
make lint-fix       # Auto-fix ruff issues
make format         # Run ruff formatter
make format-check   # Check formatting without modifying
make typecheck      # Run type checker
make check          # lint + format-check + typecheck
make validate       # lint-fix + format + typecheck + test
make clean          # Remove test artifacts and pycache
make test-auth      # Run auth tests only
make test-integration   # Run integration tests only
make test-rekordbox     # Run rekordbox tests only
```

## Architecture

```
dj_dl/
  cli.py              # Typer CLI entry point
  config.py           # YAML configuration
  downloader.py       # Download manager with concurrency
  metadata.py         # Mutagen metadata embedder
  analyzer.py         # BPM/key detection with librosa
  rekordbox_xml.py    # Rekordbox XML export
  auth.py             # Apple Music authentication
  providers/
    base.py           # BaseProvider ABC
    youtube.py        # YouTube provider (yt-dlp)
    spotify.py        # Spotify provider (metadata → YouTube)
    applemusic.py     # Apple Music provider (gamdl)
```

## Update

```bash
djdl update
```

## Uninstall

```bash
cd ~/.ytdl
make uninstall
```

To fully remove everything including the repo:
```bash
make uninstall
rm -rf ~/.ytdl
# Remove the export PATH line from ~/.zshrc if added
```

## License

MIT
