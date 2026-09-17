"""
Shared data types for the generation engine.

Designed to map cleanly to C++ structs / JUCE ValueTrees later:
- SampleType  → enum class
- Sample      → struct with path + AudioBuffer
- Event       → struct { SampleType, step, velocity, pan, pitch }
- Settings    → struct of generation parameters
- TrackState  → per-track lock + forced sample path
- Pattern     → list of Events + metadata
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np


class SampleType(str, Enum):
    KICK = "kick"
    SNARE = "snare"
    HAT = "hat"
    OPEN_HAT = "open_hat"
    CLAP = "clap"
    PERC = "perc"

    @classmethod
    def all(cls) -> list["SampleType"]:
        return list(cls)


# Keywords used by the filename/folder classifier.
# Order of specificity is handled in scanner.classify().
KEYWORDS: dict[SampleType, list[str]] = {
    SampleType.KICK: ["kick", "bd", "bassdrum", "bass_drum"],
    SampleType.SNARE: ["snare", "snr", "sd"],
    SampleType.OPEN_HAT: ["openhat", "open_hat", "ohat", "oh"],
    SampleType.HAT: ["hihat", "hi_hat", "hat", "hh", "closedhat", "closed_hat", "ch"],
    SampleType.CLAP: ["clap"],
    SampleType.PERC: ["perc", "shaker", "rim", "tom", "conga", "bongo", "cowbell"],
}


@dataclass
class Sample:
    path: Path
    kind: SampleType
    audio: np.ndarray          # mono float32, peak-normalized
    sample_rate: int


@dataclass
class Event:
    kind: SampleType
    step: int                  # absolute step index (0-based)
    velocity: float            # 0..1
    pan: float = 0.0           # -1..1
    pitch: float = 0.0         # semitones


@dataclass
class Settings:
    bpm: float = 140.0
    complexity: float = 0.6    # 0..1
    density: float = 0.7       # 0..1
    swing: float = 0.0         # 0..1
    humanize: float = 0.25     # 0..1
    bars: int = 2
    steps_per_bar: int = 16    # 16 or 32
    seed: Optional[int] = None

    def total_steps(self) -> int:
        return self.bars * self.steps_per_bar

    def validate(self) -> None:
        for name in ("complexity", "density", "swing", "humanize"):
            v = getattr(self, name)
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {v}")
        if self.steps_per_bar not in (16, 32):
            raise ValueError("steps_per_bar must be 16 or 32")
        if self.bars < 1:
            raise ValueError("bars must be >= 1")
        if self.bpm < 40 or self.bpm > 300:
            raise ValueError("bpm must be in [40, 300]")


@dataclass
class TrackState:
    """Per-track UI/engine state that survives regenerate."""
    locked: bool = False
    forced_sample: Optional[Path] = None   # if set, always use this sample
    muted: bool = False
    solo: bool = False


@dataclass
class Pattern:
    """Generated pattern + the settings/seed that produced it."""
    events: list[Event] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)
    seed_used: Optional[int] = None

    def events_for(self, kind: SampleType) -> list[Event]:
        return [e for e in self.events if e.kind == kind]

    def steps_for(self, kind: SampleType) -> set[int]:
        return {e.step for e in self.events if e.kind == kind}
