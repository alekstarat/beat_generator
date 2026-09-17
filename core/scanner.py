"""
Sample-pack scanner and classifier.

Pure functions — no UI, no global state.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np

from .types import KEYWORDS, Sample, SampleType


def classify(path: Path) -> Optional[SampleType]:
    """Classify a WAV path by parent folder name + stem keywords."""
    text = f"{path.parent.name} {path.stem}".lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)

    # More specific categories first so "open_hat" wins over "hat".
    order = [
        SampleType.OPEN_HAT,
        SampleType.KICK,
        SampleType.SNARE,
        SampleType.CLAP,
        SampleType.PERC,
        SampleType.HAT,
    ]
    for kind in order:
        if any(k in text for k in KEYWORDS[kind]):
            return kind
    return None


def load_audio(path: Path) -> tuple[np.ndarray, int]:
    """Load mono float32 audio, peak-normalized to 1.0."""
    import soundfile as sf  # lazy — keeps core importable without soundfile for tests
    audio, sr = sf.read(str(path), always_2d=True, dtype="float32")
    audio = audio.mean(axis=1)
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak > 1e-8:
        audio = audio / peak
    return audio.astype(np.float32), int(sr)


def scan_samples(
    root: Path,
    progress_callback=None,
) -> dict[SampleType, list[Sample]]:
    """
    Recursively scan *root* for WAV files and classify them.

    progress_callback(current: int, total: int, path: Path) is optional.
    """
    result: dict[SampleType, list[Sample]] = {k: [] for k in SampleType}

    paths = sorted(
        list(root.rglob("*.wav")) + list(root.rglob("*.WAV")),
        key=lambda p: str(p).lower(),
    )
    if not paths:
        raise RuntimeError(f"No WAV files found in: {root}")

    total = len(paths)
    for i, path in enumerate(paths):
        if progress_callback:
            progress_callback(i + 1, total, path)

        kind = classify(path)
        if kind is None:
            continue
        try:
            audio, sr = load_audio(path)
            if len(audio) == 0:
                continue
            result[kind].append(Sample(path=path, kind=kind, audio=audio, sample_rate=sr))
        except Exception:
            # Skip unreadable files silently; UI can show a log later.
            continue

    return result


def sample_summary(samples: dict[SampleType, list[Sample]]) -> dict[str, int]:
    return {k.value: len(v) for k, v in samples.items()}
