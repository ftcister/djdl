import subprocess
import tempfile
from pathlib import Path

from dj_dl.analyzer import analyze_track, is_analyzed


def test_is_analyzed_returns_false_for_untagged_file():
    with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(tmp_path),
        ],
        capture_output=True,
    )

    assert not is_analyzed(tmp_path)
    tmp_path.unlink()


def test_analyze_track_writes_tags():
    import numpy as np
    import soundfile as sf

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    sr = 22050
    duration = 10
    bpm = 120
    beat_interval = 60 / bpm
    t = np.linspace(0, duration, int(sr * duration))
    signal = np.zeros_like(t)
    for beat_time in np.arange(0, duration, beat_interval):
        mask = (t >= beat_time) & (t < beat_time + 0.05)
        signal[mask] = np.sin(2 * np.pi * 1000 * t[mask])

    sf.write(str(tmp_path), signal, sr)

    result = analyze_track(tmp_path)
    assert result.bpm > 0
    assert result.key is not None

    tmp_path.unlink()
