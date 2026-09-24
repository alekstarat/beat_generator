"""
Melody generation and MIDI/audio helpers for the piano-roll tab.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass(order=True)
class MelodyNote:
    start: int
    pitch: int
    length: int = 1
    velocity: float = 0.8


@dataclass
class MelodyPattern:
    notes: list[MelodyNote] = field(default_factory=list)
    bpm: float = 120.0
    steps: int = 32
    steps_per_bar: int = 16
    root: int = 60
    scale: str = "Minor"
    seed: Optional[int] = None


SCALES = {
    "Major": [0, 2, 4, 5, 7, 9, 11],
    "Minor": [0, 2, 3, 5, 7, 8, 10],
    "Dorian": [0, 2, 3, 5, 7, 9, 10],
    "Pentatonic": [0, 2, 4, 7, 9],
}


def scale_pitches(root: int, scale: str, low: int = 48, high: int = 84) -> list[int]:
    intervals = SCALES.get(scale, SCALES["Minor"])
    result = []
    for octave in range(-2, 5):
        base = root + octave * 12
        for interval in intervals:
            p = base + interval
            if low <= p <= high:
                result.append(p)
    return sorted(set(result))


def generate_melody(
    bpm: float = 120,
    steps: int = 32,
    root: int = 60,
    scale: str = "Minor",
    density: float = 0.62,
    seed: Optional[int] = None,
    steps_per_bar: int = 16,
    variation: float = 0.45,
    note_length: int = 1,
    velocity: float = 0.78,
    register: int = 4,
) -> MelodyPattern:
    """Generate a playable monophonic phrase on the selected scale."""
    rng = random.Random(seed)
    pitches = scale_pitches(root, scale)
    if not pitches:
        return MelodyPattern([], bpm, steps, steps_per_bar, root, scale, seed)

    # The register knob moves the melodic center through the available octaves.
    center = max(48, min(84, (register * 12) + 12))
    notes: list[MelodyNote] = []
    prev = min(pitches, key=lambda p: abs(p - center))
    variation = max(0.0, min(1.0, variation))
    note_length = max(1, min(4, int(note_length)))
    velocity = max(0.2, min(1.0, velocity))

    for step in range(steps):
        if step % 4 == 0:
            probability = min(0.95, density + 0.18)
        else:
            probability = density * (0.82 if step % 2 else 1.0)

        if rng.random() > probability:
            continue

        # Occasionally leave space for a more musical phrase.
        if step > 2 and rng.random() < 0.10 * (1.0 - density):
            continue

        candidates = [p for p in pitches if abs(p - prev) <= 12]
        if not candidates:
            candidates = pitches
        # Variation controls how strongly the generator prefers stepwise motion.
        scored = []
        for p in candidates:
            distance = abs(p - prev)
            register_distance = abs(p - center)
            score = (1.0 / (1.0 + distance * (1.8 - variation * 1.2)))
            score *= 1.0 / (1.0 + register_distance / 9.0)
            score *= rng.uniform(0.75, 1.25)
            scored.append((p, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        top_count = max(1, min(len(scored), 2 + int(variation * 7)))
        p = scored[0][0] if rng.random() > variation * 0.8 else rng.choice([x[0] for x in scored[:top_count]])

        length = note_length
        if variation > 0.5 and rng.random() < (variation - 0.5) * 0.45 and step + 1 < steps:
            length = min(4, length + 1)
        if variation > 0.75 and rng.random() < 0.12 and step + 3 < steps:
            length = 4

        vel = max(0.2, min(1.0, velocity * rng.uniform(0.82, 1.12)))
        notes.append(MelodyNote(step, p, min(length, steps - step), vel))
        prev = p

    return MelodyPattern(notes, bpm, steps, steps_per_bar, root, scale, seed)


def synthesize(pattern: MelodyPattern, sample_rate: int = 44100) -> np.ndarray:
    """Small dependency-free polyphonic sine/triangle-ish piano preview."""
    step_seconds = 60.0 / pattern.bpm / (pattern.steps_per_bar / 4.0)
    duration = pattern.steps * step_seconds + 0.6
    audio = np.zeros(int(duration * sample_rate), dtype=np.float32)

    for note in pattern.notes:
        start = int(note.start * step_seconds * sample_rate)
        length = max(1, int(note.length * step_seconds * sample_rate))
        end = min(len(audio), start + length + int(0.18 * sample_rate))
        if end <= start:
            continue

        n = end - start
        t = np.arange(n, dtype=np.float32) / sample_rate
        freq = 440.0 * (2.0 ** ((note.pitch - 69) / 12.0))

        # A few harmonics makes the preview less like a pure test tone.
        wave = (
            np.sin(2 * np.pi * freq * t)
            + 0.22 * np.sin(2 * np.pi * 2 * freq * t)
            + 0.08 * np.sin(2 * np.pi * 3 * freq * t)
        ).astype(np.float32)

        attack = min(int(0.012 * sample_rate), n)
        release = min(int(0.16 * sample_rate), n)
        env = np.ones(n, dtype=np.float32)
        if attack:
            env[:attack] = np.linspace(0, 1, attack, endpoint=False)
        if release:
            env[-release:] *= np.linspace(1, 0, release, endpoint=True)

        # Gate at note length, then release tail.
        gate = min(length, n)
        if gate < n:
            tail = n - gate
            env[gate:] *= np.linspace(1, 0, tail, endpoint=True)

        audio[start:end] += wave * env * note.velocity * 0.24

    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0.95:
        audio *= 0.95 / peak
    return audio


def write_midi(pattern: MelodyPattern, path: Path) -> None:
    import mido

    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Generated Melody"))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(pattern.bpm)))

    ticks_per_step = midi.ticks_per_beat // (pattern.steps_per_bar // 4)
    events = []
    for note in pattern.notes:
        start = note.start * ticks_per_step
        end = (note.start + note.length) * ticks_per_step
        velocity = max(1, min(127, int(note.velocity * 127)))
        events.append((start, 1, note.pitch, velocity))
        events.append((end, 0, note.pitch, 0))

    # Note-offs before note-ons at the same tick.
    events.sort(key=lambda e: (e[0], e[1]))
    last_tick = 0
    for tick, kind, pitch, velocity in events:
        delta = max(0, tick - last_tick)
        if kind == 1:
            track.append(mido.Message("note_on", note=pitch, velocity=velocity, time=delta))
        else:
            track.append(mido.Message("note_off", note=pitch, velocity=0, time=delta))
        last_tick = tick

    track.append(mido.MetaMessage("end_of_track", time=0))
    path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(str(path))
