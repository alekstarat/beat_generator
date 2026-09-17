"""
Beat Generator — pure generation engine.

This package has zero hard UI dependencies so the same logic can later
be reimplemented in C++ / JUCE for a VST3 plugin without rewriting
the musical rules.

Heavy optional deps (soundfile, mido) are imported lazily inside
scanner / renderer functions.
"""

from .types import SampleType, Sample, Event, Settings, TrackState, Pattern
from .generator import generate_pattern

__all__ = [
    "SampleType",
    "Sample",
    "Event",
    "Settings",
    "TrackState",
    "Pattern",
    "generate_pattern",
]
