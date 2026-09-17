#!/usr/bin/env python3
"""
Beat Randomizer — first prototype.

Scans a sample-pack directory, classifies WAV files by filename/folder,
generates a simple 4/4 drum pattern, renders it to WAV and writes MIDI.
"""

from __future__ import annotations

import argparse
import math
import random
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
import mido


SAMPLE_RATE = 44100
STEPS_PER_BAR = 16


class SampleType:
    KICK = "kick"
    SNARE = "snare"
    HAT = "hat"
    OPEN_HAT = "open_hat"
    CLAP = "clap"
    PERC = "perc"


KEYWORDS = {
    SampleType.KICK: ["kick", "bd", "bassdrum", "bass_drum"],
    SampleType.SNARE: ["snare", "snr", "sd"],
    SampleType.OPEN_HAT: ["openhat", "open_hat", "ohat", "oh"],
    SampleType.HAT: ["hihat", "hi_hat", "hat", "hh", "closedhat", "closed_hat"],
    SampleType.CLAP: ["clap"],
    SampleType.PERC: ["perc", "shaker", "rim", "tom", "conga", "bongo"],
}


@dataclass
class Sample:
    path: Path
    kind: str
    audio: np.ndarray
    sample_rate: int


@dataclass
class Event:
    kind: str
    step: int
    velocity: float
    pan: float = 0.0
    pitch: float = 0.0


@dataclass
class Settings:
    bpm: float = 140.0
    complexity: float = 0.6
    density: float = 0.7
    swing: float = 0.0
    humanize: float = 0.25
    bars: int = 4
    seed: int | None = None


def classify(path: Path) -> str | None:
    text = f"{path.parent.name} {path.stem}".lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)

    # More specific categories first.
    for kind in [SampleType.OPEN_HAT, SampleType.KICK, SampleType.SNARE,
                 SampleType.CLAP, SampleType.PERC, SampleType.HAT]:
        if any(k in text for k in KEYWORDS[kind]):
            return kind
    return None


def load_audio(path: Path) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(path, always_2d=True, dtype="float32")
    audio = audio.mean(axis=1)
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak > 1e-8:
        audio = audio / peak
    return audio, sr


def scan_samples(root: Path) -> dict[str, list[Sample]]:
    result = {k: [] for k in KEYWORDS}

    paths = list(root.rglob("*.wav")) + list(root.rglob("*.WAV"))
    if not paths:
        raise RuntimeError(f"No WAV files found in: {root}")

    print(f"Found {len(paths)} WAV files")

    for path in paths:
        kind = classify(path)
        if kind is None:
            continue
        try:
            audio, sr = load_audio(path)
            if len(audio) == 0:
                continue
            result[kind].append(Sample(path, kind, audio, sr))
        except Exception as exc:
            print(f"Skipping {path}: {exc}")

    for kind, samples in result.items():
        print(f"  {kind:9s}: {len(samples)}")

    return result


def chance(rng: random.Random, p: float) -> bool:
    return rng.random() < max(0.0, min(1.0, p))


def generate_pattern(settings: Settings) -> list[Event]:
    rng = random.Random(settings.seed)
    events: list[Event] = []
    steps = settings.bars * STEPS_PER_BAR
    c = settings.complexity
    d = settings.density

    for bar_start in range(0, steps, STEPS_PER_BAR):
        # Kick: strong downbeat + optional syncopation.
        for local in range(16):
            s = bar_start + local
            if local == 0:
                p = 0.98
            elif local == 8:
                p = 0.72 + 0.18 * c
            elif local in (4, 12):
                p = 0.22 + 0.38 * c
            elif local % 2 == 0:
                p = 0.04 + 0.16 * c
            else:
                p = 0.01 + 0.08 * c

            p *= 0.65 + 0.35 * d
            if chance(rng, p):
                velocity = rng.uniform(0.78, 1.0)
                events.append(Event(SampleType.KICK, s, velocity))

        # Snare/clap: 2 and 4, with optional ghost notes.
        for local in (4, 12):
            s = bar_start + local
            if chance(rng, 0.94):
                events.append(Event(
                    SampleType.SNARE if chance(rng, 0.72) else SampleType.CLAP,
                    s,
                    rng.uniform(0.75, 1.0)
                ))

        ghost_probability = 0.03 + 0.20 * c * d
        for local in (3, 7, 11, 15):
            if chance(rng, ghost_probability):
                events.append(Event(
                    SampleType.SNARE,
                    bar_start + local,
                    rng.uniform(0.18, 0.38)
                ))

        # Closed hats: base 8ths; complexity adds 16ths.
        for local in range(16):
            if local % 2 == 0:
                p = 0.82 * d
            else:
                p = (0.12 + 0.55 * c) * d

            if chance(rng, p):
                vel = rng.uniform(0.32, 0.68)
                if local % 4 == 0:
                    vel += 0.12
                events.append(Event(SampleType.HAT, bar_start + local, min(1, vel)))

        # Occasional open hat, usually before a strong beat.
        for local in (7, 15):
            if chance(rng, 0.04 + 0.15 * c * d):
                events.append(Event(SampleType.OPEN_HAT, bar_start + local, rng.uniform(0.35, 0.65)))

        # Percussion becomes more likely with complexity.
        perc_probability = 0.02 + 0.10 * c * d
        for local in range(16):
            if chance(rng, perc_probability):
                events.append(Event(SampleType.PERC, bar_start + local, rng.uniform(0.25, 0.55)))

    # Avoid pathological duplicate same-kind events at the same step.
    unique: dict[tuple[str, int], Event] = {}
    for e in events:
        key = (e.kind, e.step)
        if key not in unique or e.velocity > unique[key].velocity:
            unique[key] = e

    return sorted(unique.values(), key=lambda x: (x.step, x.kind))


def resample(audio: np.ndarray, source_sr: int, target_sr: int) -> np.ndarray:
    if source_sr == target_sr:
        return audio
    new_len = max(1, int(round(len(audio) * target_sr / source_sr)))
    old_x = np.linspace(0, 1, len(audio), endpoint=False)
    new_x = np.linspace(0, 1, new_len, endpoint=False)
    return np.interp(new_x, old_x, audio).astype(np.float32)


def change_speed(audio: np.ndarray, semitones: float) -> np.ndarray:
    """Simple pitch/speed change. Good enough for prototype drum variation."""
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

    # Constant-power stereo panning.
    pan = max(-1.0, min(1.0, pan))
    left = math.cos((pan + 1.0) * math.pi / 4.0)
    right = math.sin((pan + 1.0) * math.pi / 4.0)

    out[start:end, 0] += audio[:n] * gain * left
    out[start:end, 1] += audio[:n] * gain * right


def render(
    events: list[Event],
    samples: dict[str, list[Sample]],
    settings: Settings,
) -> np.ndarray:
    rng = random.Random(settings.seed)
    beat_seconds = 60.0 / settings.bpm
    step_seconds = beat_seconds / 4.0

    total_seconds = settings.bars * 4 * beat_seconds + 2.0
    out = np.zeros((int(total_seconds * SAMPLE_RATE), 2), dtype=np.float32)

    last_sample: dict[str, Path] = {}

    for event in events:
        choices = samples.get(event.kind, [])
        if not choices:
            continue

        # Discourage immediate sample repetition.
        candidates = [s for s in choices if s.path != last_sample.get(event.kind)]
        sample = rng.choice(candidates or choices)
        last_sample[event.kind] = sample.path

        audio = resample(sample.audio, sample.sample_rate, SAMPLE_RATE)

        # Subtle pitch variation. Hats get slightly more variation.
        pitch_range = 1.5 if event.kind in (SampleType.HAT, SampleType.OPEN_HAT) else 0.7
        semitones = rng.uniform(-pitch_range, pitch_range) * settings.complexity
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

        # Swing shifts every other 16th.
        if event.step % 2 == 1:
            timing += step_seconds * 0.5 * settings.swing

        start = int(max(0.0, event.step * step_seconds + timing) * SAMPLE_RATE)

        pan = 0.0
        if event.kind in (SampleType.HAT, SampleType.PERC, SampleType.OPEN_HAT):
            pan = rng.uniform(-0.22, 0.22) * settings.humanize

        mix_event(out, audio, start, event.velocity, pan)

    # Gentle master normalization.
    peak = float(np.max(np.abs(out)))
    if peak > 0.98:
        out *= 0.98 / peak

    return out


def write_midi(events: list[Event], path: Path, settings: Settings) -> None:
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)

    track.append(mido.MetaMessage("track_name", name="Beat Randomizer"))

    notes = {
        SampleType.KICK: 36,
        SampleType.SNARE: 38,
        SampleType.CLAP: 39,
        SampleType.HAT: 42,
        SampleType.OPEN_HAT: 46,
        SampleType.PERC: 43,
    }

    events_sorted = sorted(events, key=lambda e: e.step)
    last_tick = 0

    for e in events_sorted:
        if e.kind not in notes:
            continue

        tick = e.step * (midi.ticks_per_beat // 4)
        delta = max(0, tick - last_tick)
        velocity = max(1, min(127, int(e.velocity * 127)))

        track.append(mido.Message("note_on", note=notes[e.kind], velocity=velocity, time=delta))
        track.append(mido.Message("note_off", note=notes[e.kind], velocity=0, time=midi.ticks_per_beat // 8))
        last_tick = tick + midi.ticks_per_beat // 8

    track.append(mido.MetaMessage("end_of_track", time=0))
    midi.save(path)


def print_pattern(events: list[Event], bars: int) -> None:
    steps = bars * 16
    symbols = {
        SampleType.KICK: "K",
        SampleType.SNARE: "S",
        SampleType.CLAP: "C",
        SampleType.HAT: "H",
        SampleType.OPEN_HAT: "O",
        SampleType.PERC: "P",
    }

    by_kind = {}
    for e in events:
        by_kind.setdefault(e.kind, set()).add(e.step)

    print("\nPattern:")
    for kind in [SampleType.KICK, SampleType.SNARE, SampleType.CLAP,
                 SampleType.HAT, SampleType.OPEN_HAT, SampleType.PERC]:
        if kind not in by_kind:
            continue
        line = "".join(symbols[kind] if i in by_kind[kind] else "." for i in range(steps))
        grouped = " ".join(line[i:i+16] for i in range(0, steps, 16))
        print(f"{kind:9s} {grouped}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Generate simple beats from a sample pack.")
    parser.add_argument("samples", type=Path)
    parser.add_argument("--bpm", type=float, default=140)
    parser.add_argument("--complexity", type=float, default=0.6)
    parser.add_argument("--density", type=float, default=0.7)
    parser.add_argument("--swing", type=float, default=0.0)
    parser.add_argument("--humanize", type=float, default=0.25)
    parser.add_argument("--bars", type=int, default=4)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output", type=Path, default=Path("output"))
    args = parser.parse_args()

    for name, value in [
        ("complexity", args.complexity),
        ("density", args.density),
        ("swing", args.swing),
        ("humanize", args.humanize),
    ]:
        if not 0 <= value <= 1:
            parser.error(f"--{name} must be between 0 and 1")

    settings = Settings(
        bpm=args.bpm,
        complexity=args.complexity,
        density=args.density,
        swing=args.swing,
        humanize=args.humanize,
        bars=args.bars,
        seed=args.seed,
    )

    samples = scan_samples(args.samples)
    events = generate_pattern(settings)
    print_pattern(events, settings.bars)

    missing = [
        kind for kind in [SampleType.KICK, SampleType.SNARE, SampleType.HAT]
        if not samples[kind]
    ]
    if missing:
        print("WARNING: missing:", ", ".join(missing))

    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    wav = render(events, samples, settings)
    wav_path = output / "beat.wav"
    midi_path = output / "beat.mid"

    sf.write(wav_path, wav, SAMPLE_RATE, subtype="PCM_24")
    write_midi(events, midi_path, settings)

    print(f"Written: {wav_path}")
    print(f"Written: {midi_path}")


if __name__ == "__main__":
    main()
