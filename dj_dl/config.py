"""Configuration system for dj-dl."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "dj-dl" / "config.yaml"


@dataclass
class SpotifyConfig:
    """Spotify API credentials."""

    client_id: str | None = None
    client_secret: str | None = None


@dataclass
class AppleMusicConfig:
    """Apple Music configuration."""

    cookies_path: str | None = None


@dataclass
class Config:
    """Main configuration for dj-dl."""

    output_dir: Path = field(default_factory=lambda: Path.home() / "Music" / "DJ")
    audio_format: str = "m4a"
    audio_quality: int = 0
    organize_by: str = "none"
    concurrent_downloads: int = 3
    auto_analyze: bool = True
    spotify: SpotifyConfig = field(default_factory=SpotifyConfig)
    apple_music: AppleMusicConfig = field(default_factory=AppleMusicConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Create Config from dictionary."""
        data = data.copy()
        spotify_data = data.pop("spotify", {})
        apple_music_data = data.pop("apple_music", {})

        if "output_dir" in data:
            data["output_dir"] = Path(data["output_dir"]).expanduser()

        return cls(
            **data,
            spotify=SpotifyConfig(**spotify_data),
            apple_music=AppleMusicConfig(**apple_music_data),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert Config to dictionary."""
        return {
            "output_dir": str(self.output_dir),
            "audio_format": self.audio_format,
            "audio_quality": self.audio_quality,
            "organize_by": self.organize_by,
            "concurrent_downloads": self.concurrent_downloads,
            "auto_analyze": self.auto_analyze,
            "spotify": {
                "client_id": self.spotify.client_id,
                "client_secret": self.spotify.client_secret,
            },
            "apple_music": {
                "cookies_path": self.apple_music.cookies_path,
            },
        }

    def save(self, path: Path | None = None) -> None:
        """Save config to YAML file."""
        save_path = path or DEFAULT_CONFIG_PATH
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False)


def load_config(path: str | Path | None = None) -> Config:
    """Load configuration from YAML file."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH

    if not config_path.exists():
        config = Config()
        config.save(config_path)
        return config

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    return Config.from_dict(data)
