#!/bin/bash

set -e

INSTALL_DIR="$HOME/.ytdl"
ZSHRC="$HOME/.zshrc"
REPO_URL="https://github.com/ftcister/ytdl.git"

echo "📦 Installing djdl..."

echo "🔍 Checking dependencies..."

if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed."
    exit 1
fi

if ! command -v uv &> /dev/null; then
    echo "❌ Error: uv is not installed."
    echo "   Install it: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  Warning: ffmpeg is not installed. Audio conversion may fail."
    echo "   Install it: brew install ffmpeg"
fi

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "⚠️  Warning: ~/.local/bin is not in your PATH."
    echo "   Add this to your ~/.zshrc: export PATH=\"\$HOME/.local/bin:\$PATH\""
    if ! grep -q "export PATH=\"\$HOME/.local/bin:\$PATH\"" "$ZSHRC"; then
        echo -e "\n# djdl\nexport PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$ZSHRC"
        echo "✅ Added ~/.local/bin to PATH in $ZSHRC"
    fi
fi

if [[ -d "$INSTALL_DIR/.git" ]]; then
    echo "🔄 Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull --quiet
else
    echo "📥 Cloning repository..."
    git clone --quiet "$REPO_URL" "$INSTALL_DIR"
fi

echo "🐍 Installing Python package..."
cd "$INSTALL_DIR"
uv tool install -e "." --quiet

echo ""
echo "🚀 Done!"
echo ""
echo "Usage:"
echo "  djdl <url>              # Download from YouTube/Spotify/Apple Music"
echo "  djdl set-folder <path>  # Set output directory"
echo "  djdl auth               # Authenticate Apple Music"
echo "  djdl analyze            # Analyze BPM/key"
echo ""
echo "Restart your terminal or run: source ~/.zshrc"