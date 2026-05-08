"""BPM and key analyzer with librosa."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4


@dataclass
class AnalysisResult:
    path: Path
    bpm: float
    key: str
    confidence: float


CAMELOT_MAP = {
    "C major": "8B",
    "G major": "9B",
    "D major": "10B",
    "A major": "11B",
    "E major": "12B",
    "B major": "1B",
    "F# major": "2B",
    "C# major": "3B",
    "Ab major": "4B",
    "Eb major": "5B",
    "Bb major": "6B",
    "F major": "7B",
    "A minor": "8A",
    "E minor": "9A",
    "B minor": "10A",
    "F# minor": "11A",
    "C# minor": "12A",
    "G# minor": "1A",
    "D# minor": "2A",
    "Bb minor": "3A",
    "F minor": "4A",
    "C minor": "5A",
    "G minor": "6A",
    "D minor": "7A",
}

MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def is_analyzed(filepath: Path) -> bool:
    suffix = filepath.suffix.lower()
    try:
        if suffix == ".m4a":
            audio = MP4(str(filepath))
            tags = audio.tags
            if tags is None:
                return False
            return "tmpo" in tags and "----:com.apple.iTunes:TKEY" in tags
        elif suffix == ".mp3":
            audio = MP3(str(filepath))
            if audio.tags:
                return "TBPM" in audio.tags and "TKEY" in audio.tags
        elif suffix == ".flac":
            audio = FLAC(str(filepath))
            return "BPM" in audio and "INITIALKEY" in audio
    except Exception:
        pass
    return False


def analyze_track(filepath: Path) -> AnalysisResult:
    y, sr = librosa.load(str(filepath), sr=22050, duration=120)

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.squeeze(tempo))

    key, confidence = _detect_key(y, int(sr))

    _write_analysis_tags(filepath, bpm, key)

    return AnalysisResult(path=filepath, bpm=bpm, key=key, confidence=confidence)


def _detect_key(y: np.ndarray, sr: int) -> tuple[str, float]:
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_avg = np.mean(chroma, axis=1)

    major_corrs = []
    minor_corrs = []

    for i in range(12):
        rolled_major = np.roll(MAJOR_PROFILE, i)
        rolled_minor = np.roll(MINOR_PROFILE, i)
        major_corrs.append(np.corrcoef(chroma_avg, rolled_major)[0, 1])
        minor_corrs.append(np.corrcoef(chroma_avg, rolled_minor)[0, 1])

    major_corrs = np.array(major_corrs)
    minor_corrs = np.array(minor_corrs)

    best_major_idx = int(np.argmax(major_corrs))
    best_minor_idx = int(np.argmax(minor_corrs))

    if major_corrs[best_major_idx] > minor_corrs[best_minor_idx]:
        key_name = f"{KEYS[best_major_idx]} major"
        confidence = float(major_corrs[best_major_idx])
    else:
        key_name = f"{KEYS[best_minor_idx]} minor"
        confidence = float(minor_corrs[best_minor_idx])

    camelot = CAMELOT_MAP.get(key_name, "8A")
    return camelot, confidence


def _write_analysis_tags(filepath: Path, bpm: float, key: str) -> None:
    suffix = filepath.suffix.lower()

    if suffix == ".m4a":
        audio = MP4(str(filepath))
        audio["tmpo"] = [int(bpm)]
        tags = audio.tags
        if tags is None:
            audio.add_tags()
            tags = audio.tags
        if tags is not None:
            tags["----:com.apple.iTunes:TKEY"] = key.encode("utf-8")
        audio.save()
    elif suffix == ".mp3":
        from mutagen.id3 import TBPM, TKEY

        audio = MP3(str(filepath))
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
        if tags is not None:
            tags["TBPM"] = TBPM(encoding=3, text=str(int(bpm)))
            tags["TKEY"] = TKEY(encoding=3, text=key)
        audio.save()
    elif suffix == ".flac":
        audio = FLAC(str(filepath))
        audio["BPM"] = str(int(bpm))
        audio["INITIALKEY"] = key
        audio.save()
    else:
        pass
