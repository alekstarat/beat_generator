"""
Audio and MIDI rendering.

Pure functions. No UI, no global mutable state.
"""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Optional

import numpy as np

from .types import Event, Pattern, Sample, SampleType, Settings, TrackState

SAMPLE_RATE = 44100


def resample(audio: np.ndarray, source_sr: int, target_sr: int) -> np.ndarray:
    if source_sr == target_sr:
        return audio
    new_len = max(1, int(round(len(audio) * target_sr / source_sr)))
    old_x = np.linspace(0, 1, len(audio), endpoint=False)
    new_x = np.linspace(0, 1, new_len, endpoint=False)
    return np.interp(new_x, old_x, audio).astype(np.float32)


def change_speed(audio: np.ndarray, semitones: float) -> np.ndarray:
    """Simple pitch/speed change (good enough for drums)."""
    if abs(semitones) < 1e-4:
        return audio
    factor = 2.0 ** (semitones / 12.0)
    new_len = max(1, int(len(audio) / factor))
    old_x = np.linspace(0, 1, len(audio), endpoint=False)
    new_x = np.linspace(0, 1, new_len, endpoint=False)
    return np.interp(new_x, old_x, audio).astype(np.float32)


def mix_event(
    out: np.ndarray,
    audio: np.ndarray,
    start: int,
    gain: float,
    pan: float,
) -> None:
    if start >= len(out):
        return
    end = min(len(out), start + len(audio))
    n = end - start
    if n <= 0:
        return

    pan = max(-1.0, min(1.0, pan))
    left = math.cos((pan + 1.0) * math.pi / 4.0)
    right = math.sin((pan + 1.0) * math.pi / 4.0)

    out[start:end, 0] += audio[:n] * gain * left
    out[start:end, 1] += audio[:n] * gain * right


def _pick_sample(
    choices: list[Sample],
    forced: Optional[Path],
    last: Optional[Path],
    rng: random.Random,
) -> Optional[Sample]:
    if forced is not None:
        for s in choices:
            if s.path == forced:
                return s
        # Forced path not found — fall through.
    if not choices:
        return None
    candidates = [s for s in choices if s.path != last]
    return rng.choice(candidates or choices)


def render(
    pattern: Pattern,
    samples: dict[SampleType, list[Sample]],
    track_states: Optional[dict[SampleType, TrackState]] = None,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """
    Render pattern to stereo float32 numpy array.
    Applies mute/solo, forced samples, swing, humanize, pitch variation.
    """
    settings = pattern.settings
    if track_states is None:
        track_states = {k: TrackState() for k in SampleType}

    # Solo logic: if any track is soloed, only solos play.
    any_solo = any(st.solo for st in track_states.values())

    rng = random.Random(pattern.seed_used)
    steps_per_bar = settings.steps_per_bar
    beat_seconds = 60.0 / settings.bpm
    # one step = one subdivision of a quarter note
    step_seconds = beat_seconds / (steps_per_bar / 4.0)

    total_seconds = settings.bars * 4 * beat_seconds + 1.5
    out = np.zeros((int(total_seconds * sample_rate), 2), dtype=np.float32)

    last_sample: dict[SampleType, Path] = {}

    for event in pattern.events:
        st = track_states.get(event.kind, TrackState())
        if st.muted:
            continue
        if any_solo and not st.solo:
            continue

        choices = samples.get(event.kind, [])
        sample = _pick_sample(choices, st.forced_sample, last_sample.get(event.kind), rng)
        if sample is None:
            continue
        last_sample[event.kind] = sample.path

        audio = resample(sample.audio, sample.sample_rate, sample_rate)

        pitch_range = 1.5 if event.kind in (SampleType.HAT, SampleType.OPEN_HAT) else 0.7
        semitones = rng.uniform(-pitch_range, pitch_range) * settings.complexity
        if event.pitch:
            semitones += event.pitch
        audio = change_speed(audio, semitones)

        timing = 0.0
        if settings.humanize > 0:
            max_ms = {
                SampleType.KICK: 3,
                SampleType.SNARE: 8,
                SampleType.CLAP: 8,
                SampleType.HAT: 12,
                SampleType.OPEN_HAT: 12,
                SampleType.PERC: 20,
            }.get(event.kind, 8)
            timing = rng.uniform(-max_ms, max_ms) * settings.humanize / 1000.0

        # Swing: delay odd steps (every other 16th or 32nd depending on grid).
        if event.step % 2 == 1:
            timing += step_seconds * 0.5 * settings.swing

        start = int(max(0.0, event.step * step_seconds + timing) * sample_rate)

        pan = event.pan
        if abs(pan) < 1e-6 and event.kind in (SampleType.HAT, SampleType.PERC, SampleType.OPEN_HAT):
            pan = rng.uniform(-0.22, 0.22) * settings.humanize

        mix_event(out, audio, start, event.velocity, pan)

    peak = float(np.max(np.abs(out)))
    if peak > 0.98:
        out *= 0.98 / peak

    return out


def write_wav(audio: np.ndarray, path: Path, sample_rate: int = SAMPLE_RATE) -> None:
    import soundfile as sf
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio, sample_rate, subtype="PCM_24")


def write_midi(pattern: Pattern, path: Path) -> None:
    import mido
    settings = pattern.settings
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Beat Generator"))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(settings.bpm)))

    notes = {
        SampleType.KICK: 36,
        SampleType.SNARE: 38,
        SampleType.CLAP: 39,
        SampleType.HAT: 42,
        SampleType.OPEN_HAT: 46,
        SampleType.PERC: 43,
    }

    # ticks per step
    ticks_per_step = midi.ticks_per_beat // (settings.steps_per_bar // 4)
    note_len = max(1, ticks_per_step // 2)

    events_sorted = sorted(pattern.events, key=lambda e: e.step)
    last_tick = 0

    for e in events_sorted:
        if e.kind not in notes:
            continue
        tick = e.step * ticks_per_step
        delta = max(0, tick - last_tick)
        velocity = max(1, min(127, int(e.velocity * 127)))

        track.append(mido.Message("note_on", note=notes[e.kind], velocity=velocity, time=delta))
        track.append(mido.Message("note_off", note=notes[e.kind], velocity=0, time=note_len))
        last_tick = tick + note_len

    track.append(mido.MetaMessage("end_of_track", time=0))
    path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(str(path))
