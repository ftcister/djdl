#!/bin/bash

set -e

INSTALL_DIR="$HOME/.djdl"
REPO_URL="https://github.com/ftcister/djdl.git"

# Detect shell rc file
if [ -n "$ZSH_VERSION" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -n "$BASH_VERSION" ]; then
    SHELL_RC="$HOME/.bashrc"
else
    SHELL_RC="$HOME/.profile"
fi

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

if ! command -v deno &> /dev/null; then
    echo "🦕 Deno not found. Installing for best YouTube audio quality..."
    if command -v brew &> /dev/null; then
        brew install deno
    else
        curl -fsSL https://deno.land/install.sh | sh
    fi
    echo "✅ Deno installed."
fi

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "⚠️  Warning: ~/.local/bin is not in your PATH."
    echo "   Add this to your $SHELL_RC: export PATH=\"\$HOME/.local/bin:\$PATH\""
    if ! grep -q "export PATH=\"\$HOME/.local/bin:\$PATH\"" "$SHELL_RC"; then
        echo -e "\n# djdl\nexport PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$SHELL_RC"
        echo "✅ Added ~/.local/bin to PATH in $SHELL_RC"
    fi
fi

if [[ -d "$INSTALL_DIR/.git" ]]; then
    echo "🔄 Updating existing installation..."
    (cd "$INSTALL_DIR" && git pull --quiet)
else
    echo "📥 Cloning repository..."
    git clone --quiet "$REPO_URL" "$INSTALL_DIR"
fi

echo "🐍 Installing Python package..."
(cd "$INSTALL_DIR" && uv tool install -e "." --quiet)

echo ""
echo "🚀 Done!"
echo ""
echo "Usage:"
echo "  djdl <url>              # Download from YouTube/Spotify/Apple Music"
echo "  djdl set-folder <path>  # Set output directory"
echo "  djdl auth               # Authenticate Apple Music"
echo "  djdl analyze            # Analyze BPM/key"
echo ""
echo "Restart your terminal or run: source $SHELL_RC"