"""
Pattern generation engine.

All randomness is driven by an explicit seed so results are reproducible.
Supports locking: locked tracks keep their previous events while unlocked
tracks are regenerated.
"""

from __future__ import annotations

import random
from typing import Optional

from .types import Event, Pattern, SampleType, Settings, TrackState


def _chance(rng: random.Random, p: float) -> bool:
    return rng.random() < max(0.0, min(1.0, p))


def _generate_bar_16(
    rng: random.Random,
    bar_start: int,
    settings: Settings,
    active: set[SampleType],
) -> list[Event]:
    """Generate one 16-step bar for the requested sample types."""
    events: list[Event] = []
    c = settings.complexity
    d = settings.density

    # --- Kick ---
    if SampleType.KICK in active:
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
            if _chance(rng, p):
                events.append(Event(SampleType.KICK, s, rng.uniform(0.78, 1.0)))

    # --- Snare / Clap on 2 & 4 + ghosts ---
    if SampleType.SNARE in active or SampleType.CLAP in active:
        for local in (4, 12):
            s = bar_start + local
            if _chance(rng, 0.94):
                if SampleType.SNARE in active and SampleType.CLAP in active:
                    kind = SampleType.SNARE if _chance(rng, 0.72) else SampleType.CLAP
                elif SampleType.SNARE in active:
                    kind = SampleType.SNARE
                else:
                    kind = SampleType.CLAP
                events.append(Event(kind, s, rng.uniform(0.75, 1.0)))

        if SampleType.SNARE in active:
            ghost_p = 0.03 + 0.20 * c * d
            for local in (3, 7, 11, 15):
                if _chance(rng, ghost_p):
                    events.append(Event(SampleType.SNARE, bar_start + local, rng.uniform(0.18, 0.38)))

    # --- Closed hats ---
    if SampleType.HAT in active:
        for local in range(16):
            if local % 2 == 0:
                p = 0.82 * d
            else:
                p = (0.12 + 0.55 * c) * d
            if _chance(rng, p):
                vel = rng.uniform(0.32, 0.68)
                if local % 4 == 0:
                    vel += 0.12
                events.append(Event(SampleType.HAT, bar_start + local, min(1.0, vel)))

    # --- Open hat ---
    if SampleType.OPEN_HAT in active:
        for local in (7, 15):
            if _chance(rng, 0.04 + 0.15 * c * d):
                events.append(Event(SampleType.OPEN_HAT, bar_start + local, rng.uniform(0.35, 0.65)))

    # --- Perc ---
    if SampleType.PERC in active:
        perc_p = 0.02 + 0.10 * c * d
        for local in range(16):
            if _chance(rng, perc_p):
                events.append(Event(SampleType.PERC, bar_start + local, rng.uniform(0.25, 0.55)))

    return events


def _generate_bar_32(
    rng: random.Random,
    bar_start: int,
    settings: Settings,
    active: set[SampleType],
) -> list[Event]:
    """
    32-step bar: denser subdivision.
    We treat each 'local' as a 32nd-note slot; musical anchors are doubled.
    """
    events: list[Event] = []
    c = settings.complexity
    d = settings.density

    if SampleType.KICK in active:
        for local in range(32):
            s = bar_start + local
            # map 16-step positions onto 32
            if local == 0:
                p = 0.98
            elif local == 16:
                p = 0.72 + 0.18 * c
            elif local in (8, 24):
                p = 0.22 + 0.38 * c
            elif local % 4 == 0:
                p = 0.04 + 0.16 * c
            else:
                p = 0.005 + 0.04 * c
            p *= 0.65 + 0.35 * d
            if _chance(rng, p):
                events.append(Event(SampleType.KICK, s, rng.uniform(0.78, 1.0)))

    if SampleType.SNARE in active or SampleType.CLAP in active:
        for local in (8, 24):
            s = bar_start + local
            if _chance(rng, 0.94):
                if SampleType.SNARE in active and SampleType.CLAP in active:
                    kind = SampleType.SNARE if _chance(rng, 0.72) else SampleType.CLAP
                elif SampleType.SNARE in active:
                    kind = SampleType.SNARE
                else:
                    kind = SampleType.CLAP
                events.append(Event(kind, s, rng.uniform(0.75, 1.0)))

        if SampleType.SNARE in active:
            ghost_p = 0.02 + 0.15 * c * d
            for local in (6, 14, 22, 30):
                if _chance(rng, ghost_p):
                    events.append(Event(SampleType.SNARE, bar_start + local, rng.uniform(0.18, 0.38)))

    if SampleType.HAT in active:
        for local in range(32):
            if local % 4 == 0:
                p = 0.85 * d
            elif local % 2 == 0:
                p = (0.35 + 0.40 * c) * d
            else:
                p = (0.05 + 0.35 * c) * d
            if _chance(rng, p):
                vel = rng.uniform(0.28, 0.65)
                if local % 8 == 0:
                    vel += 0.12
                events.append(Event(SampleType.HAT, bar_start + local, min(1.0, vel)))

    if SampleType.OPEN_HAT in active:
        for local in (14, 30):
            if _chance(rng, 0.04 + 0.15 * c * d):
                events.append(Event(SampleType.OPEN_HAT, bar_start + local, rng.uniform(0.35, 0.65)))

    if SampleType.PERC in active:
        perc_p = 0.015 + 0.08 * c * d
        for local in range(32):
            if _chance(rng, perc_p):
                events.append(Event(SampleType.PERC, bar_start + local, rng.uniform(0.25, 0.55)))

    return events


def generate_pattern(
    settings: Settings,
    track_states: Optional[dict[SampleType, TrackState]] = None,
    previous: Optional[Pattern] = None,
) -> Pattern:
    """
    Generate a full pattern.

    - Locked tracks keep events from *previous*.
    - Unlocked tracks are freshly generated.
    - Seed is applied once for the whole pattern so results are deterministic.
    """
    settings.validate()
    if track_states is None:
        track_states = {k: TrackState() for k in SampleType}

    seed = settings.seed
    if seed is None:
        seed = random.randint(0, 2**31 - 1)

    rng = random.Random(seed)
    events: list[Event] = []

    # Which tracks need generation?
    locked_kinds = {k for k, st in track_states.items() if st.locked}
    active = {k for k in SampleType if not track_states.get(k, TrackState()).locked}

    # Carry over locked events.
    if previous is not None and locked_kinds:
        for e in previous.events:
            if e.kind in locked_kinds:
                events.append(e)

    steps_per_bar = settings.steps_per_bar
    gen_bar = _generate_bar_16 if steps_per_bar == 16 else _generate_bar_32

    for bar_idx in range(settings.bars):
        bar_start = bar_idx * steps_per_bar
        events.extend(gen_bar(rng, bar_start, settings, active))

    # Deduplicate same-kind same-step (keep louder).
    unique: dict[tuple[SampleType, int], Event] = {}
    for e in events:
        key = (e.kind, e.step)
        if key not in unique or e.velocity > unique[key].velocity:
            unique[key] = e

    sorted_events = sorted(unique.values(), key=lambda x: (x.step, x.kind.value))
    return Pattern(events=sorted_events, settings=settings, seed_used=seed)
