"""
Piano-roll melody editor/generator.
"""
from __future__ import annotations

import random
from typing import Optional

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QSpinBox,
    QSlider, QDial, QLabel, QFileDialog, QGroupBox, QFormLayout, QScrollArea,
)

from core.melody import MelodyNote, MelodyPattern, SCALES, generate_melody, write_midi


PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def pitch_name(pitch: int) -> str:
    return f"{PITCH_NAMES[pitch % 12]}{pitch // 12 - 1}"


class PianoRoll(QWidget):
    note_changed = Signal()
    note_preview = Signal(int)

    ROW_H = 24
    STEP_W = 34
    LOW = 48
    HIGH = 84
    KEY_W = 54

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps = 32
        self.notes: list[MelodyNote] = []
        self.root = 60
        self.scale = "Minor"
        self.setMinimumHeight((self.HIGH - self.LOW + 1) * self.ROW_H + 2)
        self.setFocusPolicy(Qt.StrongFocus)
        self._drag_note: Optional[MelodyNote] = None

    def set_grid(self, steps: int):
        self.steps = steps
        self.setMinimumWidth(self.KEY_W + steps * self.STEP_W + 2)
        self.update()

    def set_state(self, notes, root, scale, steps):
        self.notes = [MelodyNote(n.start, n.pitch, n.length, n.velocity) for n in notes]
        self.root, self.scale, self.steps = root, scale, steps
        self.set_grid(steps)
        self.update()

    def _note_at(self, x, y):
        step = int((x - self.KEY_W) / self.STEP_W)
        pitch = self.HIGH - int(y / self.ROW_H)
        if step < 0 or step >= self.steps or pitch < self.LOW or pitch > self.HIGH:
            return None
        for n in reversed(self.notes):
            if n.start <= step < n.start + n.length and n.pitch == pitch:
                return n
        return None

    def mousePressEvent(self, event):
        x, y = event.position().x(), event.position().y()
        if x < self.KEY_W:
            pitch = self.HIGH - int(y / self.ROW_H)
            if self.LOW <= pitch <= self.HIGH:
                self.note_preview.emit(pitch)
            return

        existing = self._note_at(x, y)
        if event.button() == Qt.RightButton:
            if existing:
                self.notes.remove(existing)
                self.note_changed.emit()
                self.update()
            return

        if event.button() == Qt.LeftButton:
            if existing:
                self._drag_note = existing
                self.note_preview.emit(existing.pitch)
                return

            step = max(0, min(self.steps - 1, int((x - self.KEY_W) / self.STEP_W)))
            pitch = max(self.LOW, min(self.HIGH, self.HIGH - int(y / self.ROW_H)))
            # Snap to the selected scale.
            allowed = [p for p in range(self.LOW, self.HIGH + 1)
                       if (p - self.root) % 12 in SCALES.get(self.scale, SCALES["Minor"])]
            if allowed:
                pitch = min(allowed, key=lambda p: abs(p - pitch))
            self.notes = [n for n in self.notes if not (n.start == step and n.pitch == pitch)]
            self.notes.append(MelodyNote(step, pitch, 1, 0.82))
            self.notes.sort(key=lambda n: (n.start, n.pitch))
            self.note_changed.emit()
            self.note_preview.emit(pitch)
            self.update()

    def mouseMoveEvent(self, event):
        if not self._drag_note or not (event.buttons() & Qt.LeftButton):
            return

        # Dragging is free in both directions: horizontal = time, vertical = pitch.
        step = max(0, min(
            self.steps - 1,
            int((event.position().x() - self.KEY_W) / self.STEP_W)
        ))
        raw_pitch = self.HIGH - int(event.position().y() / self.ROW_H)
        raw_pitch = max(self.LOW, min(self.HIGH, raw_pitch))

        # Keep dragged notes on the currently selected scale, just like newly
        # created notes. This also prevents landing between piano-roll rows.
        allowed = [
            p for p in range(self.LOW, self.HIGH + 1)
            if (p - self.root) % 12 in SCALES.get(self.scale, SCALES["Minor"])
        ]
        if allowed:
            pitch = min(allowed, key=lambda p: abs(p - raw_pitch))
        else:
            pitch = raw_pitch

        self._drag_note.start = step
        self._drag_note.pitch = pitch
        self._drag_note.length = max(1, min(self._drag_note.length, self.steps - step))
        self.notes.sort(key=lambda n: (n.start, n.pitch))
        self.note_changed.emit()
        self.update()

    def mouseReleaseEvent(self, event):
        self._drag_note = None

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        allowed = {p for p in range(self.LOW, self.HIGH + 1)
                   if (p - self.root) % 12 in SCALES.get(self.scale, SCALES["Minor"])}

        # Background + piano keys.
        for row, pitch in enumerate(range(self.HIGH, self.LOW - 1, -1)):
            y = row * self.ROW_H
            is_black = PITCH_NAMES[pitch % 12] in {"C#", "D#", "F#", "G#", "A#"}
            key = QColor("#151d22" if is_black else "#cfd8dc")
            if pitch not in allowed:
                key = QColor("#202a30") if is_black else QColor("#8b969b")
            p.fillRect(QRectF(0, y, self.KEY_W - 1, self.ROW_H - 1), key)
            p.setPen(QColor("#455a64"))
            p.drawRect(QRectF(0, y, self.KEY_W - 1, self.ROW_H - 1))
            p.setPen(QColor("#11171b" if is_black else "#263238"))
            p.drawText(QRectF(4, y, self.KEY_W - 6, self.ROW_H), Qt.AlignVCenter, pitch_name(pitch))

        # Grid.
        for step in range(self.steps + 1):
            x = self.KEY_W + step * self.STEP_W
            strong = step % 16 == 0
            medium = step % 4 == 0
            p.setPen(QPen(QColor("#546e7a" if strong else "#34434c" if medium else "#263238"),
                          1 if not strong else 2))
            p.drawLine(x, 0, x, (self.HIGH - self.LOW + 1) * self.ROW_H)

        for row, pitch in enumerate(range(self.HIGH, self.LOW - 1, -1)):
            y = row * self.ROW_H
            p.setPen(QPen(QColor("#314049" if pitch % 12 == 0 else "#222c31"), 1))
            p.drawLine(self.KEY_W, y, self.KEY_W + self.steps * self.STEP_W, y)

        # Notes.
        for n in self.notes:
            x = self.KEY_W + n.start * self.STEP_W + 2
            y = (self.HIGH - n.pitch) * self.ROW_H + 2
            w = max(8, n.length * self.STEP_W - 4)
            p.setBrush(QBrush(QColor("#26a69a")))
            p.setPen(QPen(QColor("#80cbc4"), 1))
            p.drawRoundedRect(QRectF(x, y, w, self.ROW_H - 4), 4, 4)
            p.setPen(QColor("#d7fffb"))
            p.drawText(QRectF(x + 6, y, max(0, w - 8), self.ROW_H - 4),
                       Qt.AlignVCenter, pitch_name(n.pitch))

        p.end()


class MelodyWidget(QWidget):
    """Self-contained melody tab: generate, edit, audition and export MIDI."""

    def __init__(self, audio_player=None, parent=None):
        super().__init__(parent)
        self.audio_player = audio_player
        self.pattern = MelodyPattern()
        self._build_ui()
        self._connect()
        self._generate()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(8)

        controls = QHBoxLayout()
        params = QGroupBox("Melody")
        form = QFormLayout(params)

        self.bpm = QSpinBox()
        self.bpm.setRange(40, 300)
        self.bpm.setValue(120)
        form.addRow("BPM", self.bpm)

        self.root_combo = QComboBox()
        for p in range(48, 73):
            self.root_combo.addItem(pitch_name(p), p)
        self.root_combo.setCurrentIndex(self.root_combo.findData(60))
        form.addRow("Key", self.root_combo)

        self.scale_combo = QComboBox()
        self.scale_combo.addItems(list(SCALES))
        self.scale_combo.setCurrentText("Minor")
        form.addRow("Scale", self.scale_combo)

        self.bars = QSpinBox()
        self.bars.setRange(1, 8)
        self.bars.setValue(2)
        form.addRow("Bars", self.bars)

        self.grid_combo = QComboBox()
        self.grid_combo.addItem("16 steps / bar", 16)
        self.grid_combo.addItem("32 steps / bar", 32)
        self.grid_combo.setCurrentIndex(0)
        form.addRow("Grid", self.grid_combo)

        self.density = QSlider(Qt.Horizontal)
        self.density.setRange(10, 100)
        self.density.setValue(62)
        form.addRow("Density", self.density)

        # Rotary macro controls for the generator.
        knobs = QGroupBox("Customize")
        knob_layout = QHBoxLayout(knobs)
        self.variation_knob = self._make_knob(45, 0, 100, "Variation")
        self.length_knob = self._make_knob(1, 1, 4, "Length")
        self.velocity_knob = self._make_knob(78, 30, 100, "Velocity")
        self.register_knob = self._make_knob(4, 3, 6, "Register")
        for knob, label in (
            (self.variation_knob, "Variation"),
            (self.length_knob, "Length"),
            (self.velocity_knob, "Velocity"),
            (self.register_knob, "Register"),
        ):
            knob_layout.addWidget(self._knob_column(knob, label))
        controls.addWidget(knobs)

        controls.addWidget(params)

        actions = QGroupBox("Actions")
        al = QVBoxLayout(actions)
        self.generate_btn = QPushButton("Generate melody")
        self.generate_btn.setObjectName("primary")
        al.addWidget(self.generate_btn)
        self.play_btn = QPushButton("▶ Play")
        al.addWidget(self.play_btn)
        self.clear_btn = QPushButton("Clear")
        al.addWidget(self.clear_btn)
        self.export_btn = QPushButton("Export MIDI…")
        al.addWidget(self.export_btn)
        controls.addWidget(actions)

        hint = QLabel("Left click: add / drag • Right click: delete • Click piano key: preview")
        hint.setStyleSheet("color: #78909c;")
        hint.setWordWrap(True)
        controls.addWidget(hint, stretch=1)
        root.addLayout(controls)

        self.roll = PianoRoll()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.roll)
        root.addWidget(scroll, stretch=1)

        self.info = QLabel()
        self.info.setStyleSheet("color: #78909c;")
        root.addWidget(self.info)

    def _make_knob(self, value: int, minimum: int, maximum: int, _label: str):
        knob = QDial()
        knob.setRange(minimum, maximum)
        knob.setValue(value)
        knob.setNotchesVisible(True)
        knob.setWrapping(False)
        knob.setFixedSize(56, 56)
        knob.setToolTip(_label)
        return knob

    def _knob_column(self, knob, label):
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(2)
        text = QLabel(label)
        text.setAlignment(Qt.AlignCenter)
        value = QLabel(str(knob.value()))
        value.setAlignment(Qt.AlignCenter)
        value.setStyleSheet("color: #80cbc4; font-weight: 600;")
        knob.valueChanged.connect(value.setNum)
        layout.addWidget(knob, alignment=Qt.AlignCenter)
        layout.addWidget(text)
        layout.addWidget(value)
        return box

    def _connect(self):
        self.generate_btn.clicked.connect(self._generate)
        self.play_btn.clicked.connect(self._play)
        self.clear_btn.clicked.connect(self._clear)
        self.export_btn.clicked.connect(self._export)
        self.roll.note_changed.connect(self._sync_pattern)
        self.roll.note_preview.connect(self._preview_note)
        self.bpm.valueChanged.connect(self._sync_pattern)
        self.root_combo.currentIndexChanged.connect(self._regenerate_from_controls)
        self.scale_combo.currentIndexChanged.connect(self._regenerate_from_controls)
        self.bars.valueChanged.connect(self._regenerate_from_controls)
        self.grid_combo.currentIndexChanged.connect(self._regenerate_from_controls)
        self.density.valueChanged.connect(self._regenerate_from_controls)
        self.variation_knob.valueChanged.connect(self._regenerate_from_controls)
        self.length_knob.valueChanged.connect(self._regenerate_from_controls)
        self.velocity_knob.valueChanged.connect(self._regenerate_from_controls)
        self.register_knob.valueChanged.connect(self._regenerate_from_controls)

    def _regenerate_from_controls(self):
        # Changing structural controls keeps the tab immediately coherent.
        self._generate()

    def _generate(self):
        steps_per_bar = int(self.grid_combo.currentData())
        total_steps = self.bars.value() * steps_per_bar
        seed = random.randint(0, 2**31 - 1)
        self.pattern = generate_melody(
            bpm=self.bpm.value(),
            steps=total_steps,
            root=self.root_combo.currentData(),
            scale=self.scale_combo.currentText(),
            density=self.density.value() / 100.0,
            seed=seed,
            steps_per_bar=steps_per_bar,
            variation=self.variation_knob.value() / 100.0,
            note_length=self.length_knob.value(),
            velocity=self.velocity_knob.value() / 100.0,
            register=self.register_knob.value(),
        )
        self.roll.set_state(self.pattern.notes, self.pattern.root, self.pattern.scale, self.pattern.steps)
        self.info.setText(f"Seed {seed} • {len(self.pattern.notes)} notes • {self.pattern.steps} steps")

    def _sync_pattern(self):
        self.pattern.notes = sorted(self.roll.notes, key=lambda n: (n.start, n.pitch))
        self.pattern.bpm = self.bpm.value()
        self.pattern.root = self.root_combo.currentData()
        self.pattern.scale = self.scale_combo.currentText()
        self.info.setText(f"{len(self.pattern.notes)} notes • {self.pattern.steps} steps")

    def _preview_note(self, pitch):
        if self.audio_player is None:
            return
        from core.melody import MelodyPattern, MelodyNote, synthesize
        preview = MelodyPattern([MelodyNote(0, pitch, 4, 0.8)], self.bpm.value(), 4, 16, self.pattern.root, self.pattern.scale)
        self.audio_player.play_oneshot(synthesize(preview), 44100)

    def _play(self):
        self._sync_pattern()
        if self.audio_player is not None:
            from core.melody import synthesize
            self.audio_player.play_oneshot(synthesize(self.pattern), 44100)
            self.info.setText(f"▶ Playing • {len(self.pattern.notes)} notes")

    def _clear(self):
        self.roll.notes.clear()
        self._sync_pattern()
        self.roll.update()

    def _export(self):
        self._sync_pattern()
        path, _ = QFileDialog.getSaveFileName(self, "Export Melody MIDI", "melody.mid", "MIDI (*.mid)")
        if path:
            try:
                write_midi(self.pattern, __import__("pathlib").Path(path))
                self.info.setText(f"Written {path}")
            except Exception as e:
                self.info.setText(f"Export failed: {e}")
