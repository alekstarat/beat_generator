"""
Main application window.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSpinBox, QDoubleSpinBox, QComboBox, QFileDialog, QMessageBox,
    QGroupBox, QFormLayout, QProgressBar, QStatusBar, QFrame, QLineEdit,
    QSizePolicy, QApplication,
)

from core.types import SampleType, Settings, TrackState, Pattern, Event, Sample
from core.scanner import scan_samples, sample_summary
from core.generator import generate_pattern
from core.renderer import render, write_wav, write_midi, SAMPLE_RATE
from core.preset import save_preset, load_preset

from .sequencer import SequencerWidget
from .audio_player import AudioPlayer


class ScanWorker(QThread):
    progress = Signal(int, int, str)
    finished_ok = Signal(object)   # samples dict
    failed = Signal(str)

    def __init__(self, root: Path):
        super().__init__()
        self.root = root

    def run(self):
        try:
            def cb(cur, total, path):
                self.progress.emit(cur, total, str(path.name))
            samples = scan_samples(self.root, progress_callback=cb)
            self.finished_ok.emit(samples)
        except Exception as e:
            self.failed.emit(str(e))


class RenderWorker(QThread):
    finished_ok = Signal(object)  # np.ndarray
    failed = Signal(str)

    def __init__(self, pattern, samples, track_states):
        super().__init__()
        self.pattern = pattern
        self.samples = samples
        self.track_states = track_states

    def run(self):
        try:
            audio = render(self.pattern, self.samples, self.track_states)
            self.finished_ok.emit(audio)
        except Exception as e:
            self.failed.emit(str(e))


class DropZone(QFrame):
    folder_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(70)
        self.setStyleSheet("""
            DropZone {
                border: 2px dashed #546e7a;
                border-radius: 8px;
                background: #1e2a32;
            }
            DropZone:hover {
                border-color: #26a69a;
                background: #24343e;
            }
        """)
        layout = QVBoxLayout(self)
        self.label = QLabel("Drop sample-pack folder here\nor click Browse…")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: #90a4ae; border: none; background: transparent;")
        layout.addWidget(self.label)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        p = Path(path)
        if p.is_file():
            p = p.parent
        if p.is_dir():
            self.folder_dropped.emit(str(p))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Beat Generator")
        self.resize(1100, 720)
        self.setStyleSheet(APP_STYLE)

        # --- engine state ---
        self.sample_pack_root: Optional[Path] = None
        self.samples: dict[SampleType, list[Sample]] = {k: [] for k in SampleType}
        self.track_states: dict[SampleType, TrackState] = {k: TrackState() for k in SampleType}
        self.pattern: Optional[Pattern] = None
        self.audio: Optional[np.ndarray] = None
        self.settings = Settings()

        self.player = AudioPlayer(self)
        self.player.finished.connect(self._on_play_finished)

        self._scan_worker: Optional[ScanWorker] = None
        self._render_worker: Optional[RenderWorker] = None

        self._build_ui()
        self._connect()
        self.statusBar().showMessage("Drop a sample pack to begin")

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(10)
        root.setContentsMargins(12, 12, 12, 8)

        # Top: drop + path
        top = QHBoxLayout()
        self.drop_zone = DropZone()
        top.addWidget(self.drop_zone, stretch=1)
        browse_col = QVBoxLayout()
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.setFixedWidth(110)
        browse_col.addWidget(self.browse_btn)
        self.pack_label = QLabel("No pack loaded")
        self.pack_label.setStyleSheet("color: #78909c; font-size: 11px;")
        self.pack_label.setWordWrap(True)
        browse_col.addWidget(self.pack_label)
        browse_col.addStretch()
        top.addLayout(browse_col)
        root.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        root.addWidget(self.progress)

        # Controls row
        controls = QHBoxLayout()
        controls.setSpacing(16)

        # Generation params
        params = QGroupBox("Generation")
        form = QFormLayout(params)
        form.setSpacing(6)

        self.bpm_spin = QSpinBox()
        self.bpm_spin.setRange(40, 300)
        self.bpm_spin.setValue(140)
        form.addRow("BPM", self.bpm_spin)

        self.density_slider = self._make_slider(0, 100, 70)
        form.addRow("Density", self.density_slider)

        self.complexity_slider = self._make_slider(0, 100, 60)
        form.addRow("Complexity", self.complexity_slider)

        self.swing_slider = self._make_slider(0, 100, 0)
        form.addRow("Swing", self.swing_slider)

        self.humanize_slider = self._make_slider(0, 100, 25)
        form.addRow("Humanize", self.humanize_slider)

        self.bars_spin = QSpinBox()
        self.bars_spin.setRange(1, 8)
        self.bars_spin.setValue(2)
        form.addRow("Bars", self.bars_spin)

        self.grid_combo = QComboBox()
        self.grid_combo.addItem("16 steps", 16)
        self.grid_combo.addItem("32 steps", 32)
        form.addRow("Grid", self.grid_combo)

        self.seed_edit = QLineEdit()
        self.seed_edit.setPlaceholderText("auto")
        self.seed_edit.setMaximumWidth(100)
        form.addRow("Seed", self.seed_edit)

        controls.addWidget(params)

        # Actions
        actions = QGroupBox("Actions")
        al = QVBoxLayout(actions)
        self.gen_btn = QPushButton("Generate")
        self.gen_btn.setObjectName("primary")
        self.gen_btn.setEnabled(False)
        al.addWidget(self.gen_btn)

        self.regen_btn = QPushButton("Regenerate")
        self.regen_btn.setEnabled(False)
        al.addWidget(self.regen_btn)

        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setEnabled(False)
        al.addWidget(self.play_btn)

        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setEnabled(False)
        al.addWidget(self.stop_btn)

        al.addSpacing(8)
        self.export_wav_btn = QPushButton("Export WAV…")
        self.export_wav_btn.setEnabled(False)
        al.addWidget(self.export_wav_btn)

        self.export_midi_btn = QPushButton("Export MIDI…")
        self.export_midi_btn.setEnabled(False)
        al.addWidget(self.export_midi_btn)

        al.addSpacing(8)
        self.save_preset_btn = QPushButton("Save Preset…")
        self.save_preset_btn.setEnabled(False)
        al.addWidget(self.save_preset_btn)

        self.load_preset_btn = QPushButton("Load Preset…")
        al.addWidget(self.load_preset_btn)

        al.addStretch()
        controls.addWidget(actions)

        # Sample counts
        info = QGroupBox("Samples")
        il = QVBoxLayout(info)
        self.sample_info = QLabel("—")
        self.sample_info.setStyleSheet("color: #b0bec5; font-family: monospace; font-size: 12px;")
        self.sample_info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        il.addWidget(self.sample_info)
        il.addStretch()
        controls.addWidget(info)

        root.addLayout(controls)

        # Sequencer
        seq_box = QGroupBox("Sequencer")
        seq_layout = QVBoxLayout(seq_box)
        self.sequencer = SequencerWidget()
        seq_layout.addWidget(self.sequencer)
        root.addWidget(seq_box, stretch=1)

        self.setStatusBar(QStatusBar())

    def _make_slider(self, lo, hi, val) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(val)
        label = QLabel(f"{val / 100:.2f}")
        label.setFixedWidth(36)
        slider.valueChanged.connect(lambda v, lb=label: lb.setText(f"{v / 100:.2f}"))
        h.addWidget(slider)
        h.addWidget(label)
        w.slider = slider  # type: ignore
        return w

    def _connect(self):
        self.drop_zone.folder_dropped.connect(self.load_pack)
        self.browse_btn.clicked.connect(self._browse_pack)
        self.gen_btn.clicked.connect(self.generate)
        self.regen_btn.clicked.connect(self.regenerate)
        self.play_btn.clicked.connect(self.play)
        self.stop_btn.clicked.connect(self.stop)
        self.export_wav_btn.clicked.connect(self.export_wav)
        self.export_midi_btn.clicked.connect(self.export_midi)
        self.save_preset_btn.clicked.connect(self.save_preset_dialog)
        self.load_preset_btn.clicked.connect(self.load_preset_dialog)

        self.sequencer.lock_changed.connect(self._on_lock)
        self.sequencer.mute_changed.connect(self._on_mute)
        self.sequencer.solo_changed.connect(self._on_solo)
        self.sequencer.step_toggled.connect(self._on_step_toggle)
        self.sequencer.sample_chosen.connect(self._on_sample_chosen)

        self.grid_combo.currentIndexChanged.connect(self._on_grid_changed)
        self.bars_spin.valueChanged.connect(self._on_bars_changed)

    # ------------------------------------------------------------------ Pack
    def _browse_pack(self):
        path = QFileDialog.getExistingDirectory(self, "Select sample pack folder")
        if path:
            self.load_pack(path)

    def load_pack(self, path: str):
        root = Path(path)
        if not root.is_dir():
            QMessageBox.warning(self, "Error", f"Not a folder:\n{path}")
            return

        self.sample_pack_root = root
        self.pack_label.setText(str(root))
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.statusBar().showMessage(f"Scanning {root}…")
        self.gen_btn.setEnabled(False)

        self._scan_worker = ScanWorker(root)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished_ok.connect(self._on_scan_done)
        self._scan_worker.failed.connect(self._on_scan_fail)
        self._scan_worker.start()

    def _on_scan_progress(self, cur, total, name):
        self.progress.setMaximum(total)
        self.progress.setValue(cur)
        self.progress.setFormat(f"%v / %m  {name}")

    def _on_scan_done(self, samples):
        self.progress.setVisible(False)
        self.samples = samples
        summary = sample_summary(samples)
        lines = [f"{k:9s}: {v}" for k, v in summary.items()]
        self.sample_info.setText("\n".join(lines))
        total = sum(summary.values())
        self.statusBar().showMessage(f"Loaded {total} samples from {self.sample_pack_root}")

        # Populate sample combos
        for kind in SampleType:
            items = [("Auto", None)]
            for s in samples.get(kind, []):
                items.append((s.path.name, s.path))
            self.sequencer.set_samples_for(kind, items)

        self.gen_btn.setEnabled(total > 0)
        self.save_preset_btn.setEnabled(True)

        missing = [k.value for k in (SampleType.KICK, SampleType.SNARE, SampleType.HAT)
                   if not samples.get(k)]
        if missing:
            self.statusBar().showMessage(
                f"Loaded {total} samples — warning: missing {', '.join(missing)}"
            )

    def _on_scan_fail(self, msg):
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Scan failed", msg)

    # ------------------------------------------------------------------ Generate
    def _read_settings(self) -> Settings:
        seed_text = self.seed_edit.text().strip()
        seed = int(seed_text) if seed_text.isdigit() else None
        return Settings(
            bpm=self.bpm_spin.value(),
            density=self.density_slider.slider.value() / 100.0,
            complexity=self.complexity_slider.slider.value() / 100.0,
            swing=self.swing_slider.slider.value() / 100.0,
            humanize=self.humanize_slider.slider.value() / 100.0,
            bars=self.bars_spin.value(),
            steps_per_bar=self.grid_combo.currentData(),
            seed=seed,
        )

    def generate(self):
        self.settings = self._read_settings()
        # Fresh generate: clear previous so locks don't carry stale data
        # unless user explicitly locked after a previous generate.
        self.pattern = generate_pattern(self.settings, self.track_states, previous=None)
        self.seed_edit.setText(str(self.pattern.seed_used))
        self.sequencer.set_pattern(self.pattern)
        self._render_audio()

    def regenerate(self):
        if self.pattern is None:
            self.generate()
            return
        # New seed unless user locked the seed field intentionally —
        # for regenerate we always pick a new seed for unlocked tracks.
        self.settings = self._read_settings()
        self.settings.seed = random.randint(0, 2**31 - 1)
        self.pattern = generate_pattern(
            self.settings, self.track_states, previous=self.pattern
        )
        self.seed_edit.setText(str(self.pattern.seed_used))
        self.sequencer.set_pattern(self.pattern)
        self._render_audio()

    def _render_audio(self):
        if self.pattern is None:
            return
        self.statusBar().showMessage("Rendering…")
        self.gen_btn.setEnabled(False)
        self.regen_btn.setEnabled(False)

        self._render_worker = RenderWorker(self.pattern, self.samples, self.track_states)
        self._render_worker.finished_ok.connect(self._on_render_done)
        self._render_worker.failed.connect(self._on_render_fail)
        self._render_worker.start()

    def _on_render_done(self, audio):
        self.audio = audio
        self.player.set_audio(audio, SAMPLE_RATE)
        self.gen_btn.setEnabled(True)
        self.regen_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.export_wav_btn.setEnabled(True)
        self.export_midi_btn.setEnabled(True)
        self.statusBar().showMessage(
            f"Ready — seed {self.pattern.seed_used}, "
            f"{len(self.pattern.events)} events, "
            f"{len(audio) / SAMPLE_RATE:.1f}s"
        )

    def _on_render_fail(self, msg):
        self.gen_btn.setEnabled(True)
        self.regen_btn.setEnabled(True)
        QMessageBox.critical(self, "Render failed", msg)

    # ------------------------------------------------------------------ Play
    def play(self):
        if self.audio is None:
            return
        self.player.play()
        self.play_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop(self):
        self.player.stop()
        self.play_btn.setEnabled(self.audio is not None)
        self.stop_btn.setEnabled(False)

    def _on_play_finished(self):
        self.play_btn.setEnabled(self.audio is not None)
        self.stop_btn.setEnabled(False)

    # ------------------------------------------------------------------ Export
    def export_wav(self):
        if self.audio is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export WAV", "beat.wav", "WAV (*.wav)"
        )
        if path:
            write_wav(self.audio, Path(path))
            self.statusBar().showMessage(f"Written {path}")

    def export_midi(self):
        if self.pattern is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export MIDI", "beat.mid", "MIDI (*.mid)"
        )
        if path:
            write_midi(self.pattern, Path(path))
            self.statusBar().showMessage(f"Written {path}")

    # ------------------------------------------------------------------ Presets
    def save_preset_dialog(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Preset", "preset.json", "JSON (*.json)"
        )
        if not path:
            return
        settings = self._read_settings()
        if self.pattern:
            settings.seed = self.pattern.seed_used
        save_preset(
            Path(path),
            settings,
            self.track_states,
            sample_pack_root=self.sample_pack_root,
            pattern=self.pattern,
            name=Path(path).stem,
        )
        self.statusBar().showMessage(f"Preset saved: {path}")

    def load_preset_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Preset", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            data = load_preset(Path(path))
        except Exception as e:
            QMessageBox.critical(self, "Preset error", str(e))
            return

        s = data["settings"]
        self.bpm_spin.setValue(int(s.bpm))
        self.density_slider.slider.setValue(int(s.density * 100))
        self.complexity_slider.slider.setValue(int(s.complexity * 100))
        self.swing_slider.slider.setValue(int(s.swing * 100))
        self.humanize_slider.slider.setValue(int(s.humanize * 100))
        self.bars_spin.setValue(s.bars)
        idx = self.grid_combo.findData(s.steps_per_bar)
        if idx >= 0:
            self.grid_combo.setCurrentIndex(idx)
        if data["seed_used"] is not None:
            self.seed_edit.setText(str(data["seed_used"]))
        elif s.seed is not None:
            self.seed_edit.setText(str(s.seed))

        self.track_states = data["track_states"]
        self.sequencer.set_track_states(self.track_states)
        self.sequencer.set_steps(s.steps_per_bar)

        root = data["sample_pack_root"]
        if root and root.is_dir():
            self.load_pack(str(root))
            # After scan we'll generate with the loaded seed
            self._pending_preset_generate = True
            self._pending_settings = s
        else:
            self.statusBar().showMessage(
                "Preset loaded (sample pack path missing — load pack manually)"
            )

    # ------------------------------------------------------------------ Track callbacks
    def _on_lock(self, kind, locked):
        self.track_states[kind].locked = locked

    def _on_mute(self, kind, muted):
        self.track_states[kind].muted = muted
        if self.pattern is not None:
            self._render_audio()

    def _on_solo(self, kind, solo):
        self.track_states[kind].solo = solo
        if self.pattern is not None:
            self._render_audio()

    def _on_sample_chosen(self, kind, path):
        self.track_states[kind].forced_sample = path
        if self.pattern is not None:
            self._render_audio()

    def _on_step_toggle(self, step, kind):
        if self.pattern is None:
            return
        # Toggle event in pattern
        existing = [e for e in self.pattern.events if e.kind == kind and e.step == step]
        if existing:
            self.pattern.events = [
                e for e in self.pattern.events if not (e.kind == kind and e.step == step)
            ]
        else:
            self.pattern.events.append(Event(kind, step, 0.8))
            self.pattern.events.sort(key=lambda e: (e.step, e.kind.value))
        self.sequencer.set_pattern(self.pattern)
        self._render_audio()

    def _on_grid_changed(self, _idx):
        steps = self.grid_combo.currentData()
        self.sequencer.set_steps(steps)

    def _on_bars_changed(self, bars):
        # Only affects next generate; sequencer shows current pattern length
        pass


APP_STYLE = """
QMainWindow, QWidget {
    background: #0f1419;
    color: #eceff1;
    font-family: "Segoe UI", "SF Pro Text", sans-serif;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #2a3a45;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #80cbc4;
}
QPushButton {
    background: #263238;
    border: 1px solid #37474f;
    border-radius: 5px;
    padding: 6px 12px;
    min-height: 22px;
}
QPushButton:hover {
    background: #314049;
    border-color: #546e7a;
}
QPushButton:pressed {
    background: #1a2329;
}
QPushButton:disabled {
    color: #546e7a;
    background: #1a2228;
}
QPushButton#primary {
    background: #00897b;
    border-color: #26a69a;
    font-weight: 600;
}
QPushButton#primary:hover {
    background: #26a69a;
}
QPushButton:checked {
    background: #455a64;
    border-color: #78909c;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #263238;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 14px;
    margin: -5px 0;
    background: #26a69a;
    border-radius: 7px;
}
QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {
    background: #1a2329;
    border: 1px solid #37474f;
    border-radius: 4px;
    padding: 3px 6px;
    min-height: 22px;
}
QProgressBar {
    border: 1px solid #37474f;
    border-radius: 4px;
    text-align: center;
    background: #1a2329;
}
QProgressBar::chunk {
    background: #00897b;
    border-radius: 3px;
}
QStatusBar {
    background: #0a0e12;
    color: #78909c;
}
"""
