"""Base provider interface and URL detection."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Track:
    """Represents a music track."""

    title: str = ""
    artist: str = ""
    album: str = ""
    source_url: str = ""
    download_url: str = ""
    duration_ms: int = 0
    track_number: int = 0
    cover_url: str = ""
    genre: str = ""
    year: int = 0
    isrc: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderResult:
    """Result from a provider extraction."""

    tracks: list[Track] = field(default_factory=list)
    playlist_name: str = ""
    playlist_description: str = ""
    source: str = ""


class BaseProvider(ABC):
    """Abstract base class for music providers."""

    name: str = ""

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this provider can handle the given URL."""
        ...

    @abstractmethod
    async def extract(self, url: str) -> ProviderResult:
        """Extract track metadata from URL."""
        ...

    @abstractmethod
    async def download(
        self,
        track: Track,
        output_dir: Path,
        progress_callback: Callable | None = None,
    ) -> Path:
        """Download track to output directory."""
        ...


URL_PATTERNS: dict[str, list[re.Pattern]] = {
    "youtube": [
        re.compile(r"youtube\.com/watch\?"),
        re.compile(r"youtu\.be/"),
        re.compile(r"youtube\.com/playlist\?"),
        re.compile(r"music\.youtube\.com/"),
    ],
    "spotify": [
        re.compile(r"open\.spotify\.com/(track|album|playlist)/"),
        re.compile(r"spotify\.com/(track|album|playlist)/"),
    ],
    "apple_music": [
        re.compile(r"music\.apple\.com/[^/]+/(song|album|playlist)/"),
    ],
}


def detect_provider(url: str) -> str:
    """Detect which provider handles the given URL."""
    for provider_name, patterns in URL_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(url):
                return provider_name
    return "unknown"
