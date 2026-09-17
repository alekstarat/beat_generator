"""
Preset save / load (JSON).

Stores settings, seed, track lock/mute/solo, forced sample paths,
and the absolute sample-pack root so a preset can be reloaded.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .types import Pattern, SampleType, Settings, TrackState


def _settings_to_dict(s: Settings) -> dict[str, Any]:
    return {
        "bpm": s.bpm,
        "complexity": s.complexity,
        "density": s.density,
        "swing": s.swing,
        "humanize": s.humanize,
        "bars": s.bars,
        "steps_per_bar": s.steps_per_bar,
        "seed": s.seed,
    }


def _settings_from_dict(d: dict[str, Any]) -> Settings:
    return Settings(
        bpm=float(d.get("bpm", 140)),
        complexity=float(d.get("complexity", 0.6)),
        density=float(d.get("density", 0.7)),
        swing=float(d.get("swing", 0.0)),
        humanize=float(d.get("humanize", 0.25)),
        bars=int(d.get("bars", 2)),
        steps_per_bar=int(d.get("steps_per_bar", 16)),
        seed=d.get("seed"),
    )


def _tracks_to_dict(tracks: dict[SampleType, TrackState]) -> dict[str, Any]:
    out = {}
    for k, st in tracks.items():
        out[k.value] = {
            "locked": st.locked,
            "muted": st.muted,
            "solo": st.solo,
            "forced_sample": str(st.forced_sample) if st.forced_sample else None,
        }
    return out


def _tracks_from_dict(d: dict[str, Any]) -> dict[SampleType, TrackState]:
    result: dict[SampleType, TrackState] = {k: TrackState() for k in SampleType}
    for key, val in d.items():
        try:
            kind = SampleType(key)
        except ValueError:
            continue
        result[kind] = TrackState(
            locked=bool(val.get("locked", False)),
            muted=bool(val.get("muted", False)),
            solo=bool(val.get("solo", False)),
            forced_sample=Path(val["forced_sample"]) if val.get("forced_sample") else None,
        )
    return result


def save_preset(
    path: Path,
    settings: Settings,
    track_states: dict[SampleType, TrackState],
    sample_pack_root: Optional[Path] = None,
    pattern: Optional[Pattern] = None,
    name: str = "",
) -> None:
    data = {
        "version": 1,
        "name": name,
        "sample_pack_root": str(sample_pack_root) if sample_pack_root else None,
        "settings": _settings_to_dict(settings),
        "tracks": _tracks_to_dict(track_states),
        "seed_used": pattern.seed_used if pattern else settings.seed,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_preset(path: Path) -> dict[str, Any]:
    """
    Returns a dict with keys:
      name, sample_pack_root (Path|None), settings (Settings),
      track_states (dict), seed_used (int|None)
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    root = data.get("sample_pack_root")
    return {
        "name": data.get("name", path.stem),
        "sample_pack_root": Path(root) if root else None,
        "settings": _settings_from_dict(data.get("settings", {})),
        "track_states": _tracks_from_dict(data.get("tracks", {})),
        "seed_used": data.get("seed_used"),
    }
