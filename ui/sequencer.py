"""
16/32-step sequencer grid widget.

Displays one row per SampleType with step cells that light up when an
event exists. Click a cell to toggle (manual edit). Lock button per row.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QSizePolicy, QComboBox, QCheckBox, QFrame,
)

from core.types import SampleType, Pattern, TrackState, Event


# Visual colours per track
TRACK_COLORS = {
    SampleType.KICK: "#e74c3c",
    SampleType.SNARE: "#3498db",
    SampleType.CLAP: "#9b59b6",
    SampleType.HAT: "#f1c40f",
    SampleType.OPEN_HAT: "#e67e22",
    SampleType.PERC: "#1abc9c",
}

TRACK_LABELS = {
    SampleType.KICK: "Kick",
    SampleType.SNARE: "Snare",
    SampleType.CLAP: "Clap",
    SampleType.HAT: "Hat",
    SampleType.OPEN_HAT: "Open",
    SampleType.PERC: "Perc",
}


class StepCell(QWidget):
    toggled = Signal(int, object)  # step, SampleType

    def __init__(self, step: int, kind: SampleType, parent=None):
        super().__init__(parent)
        self.step = step
        self.kind = kind
        self.active = False
        self.velocity = 0.0
        self.setFixedSize(22, 28)
        self.setCursor(Qt.PointingHandCursor)

    def set_event(self, active: bool, velocity: float = 0.0) -> None:
        self.active = active
        self.velocity = velocity
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggled.emit(self.step, self.kind)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)

        # Beat accent (every 4 steps in 16, every 8 in 32 — handled by parent opacity)
        base = QColor("#2c3e50")
        if self.step % 4 == 0:
            base = QColor("#34495e")

        if self.active:
            c = QColor(TRACK_COLORS[self.kind])
            # Velocity modulates brightness
            factor = 0.45 + 0.55 * max(0.15, min(1.0, self.velocity))
            c = QColor(
                int(c.red() * factor),
                int(c.green() * factor),
                int(c.blue() * factor),
            )
            p.setBrush(QBrush(c))
            p.setPen(Qt.NoPen)
        else:
            p.setBrush(QBrush(base))
            p.setPen(QPen(QColor("#1a252f"), 1))

        p.drawRoundedRect(rect, 3, 3)
        p.end()


class TrackRow(QWidget):
    lock_changed = Signal(object, bool)       # SampleType, locked
    mute_changed = Signal(object, bool)
    solo_changed = Signal(object, bool)
    step_toggled = Signal(int, object)        # step, SampleType
    sample_chosen = Signal(object, object)    # SampleType, path|None

    def __init__(self, kind: SampleType, steps: int, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.steps = steps
        self.cells: list[StepCell] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(3)

        # Label
        lbl = QLabel(TRACK_LABELS[kind])
        lbl.setFixedWidth(48)
        lbl.setStyleSheet(f"color: {TRACK_COLORS[kind]}; font-weight: 600;")
        layout.addWidget(lbl)

        # Lock
        self.lock_btn = QPushButton("🔓")
        self.lock_btn.setFixedSize(28, 28)
        self.lock_btn.setCheckable(True)
        self.lock_btn.setToolTip("Lock track (keep on regenerate)")
        self.lock_btn.toggled.connect(self._on_lock)
        layout.addWidget(self.lock_btn)

        # Mute / Solo
        self.mute_btn = QPushButton("M")
        self.mute_btn.setFixedSize(24, 28)
        self.mute_btn.setCheckable(True)
        self.mute_btn.setToolTip("Mute")
        self.mute_btn.toggled.connect(lambda v: self.mute_changed.emit(self.kind, v))
        layout.addWidget(self.mute_btn)

        self.solo_btn = QPushButton("S")
        self.solo_btn.setFixedSize(24, 28)
        self.solo_btn.setCheckable(True)
        self.solo_btn.setToolTip("Solo")
        self.solo_btn.toggled.connect(lambda v: self.solo_changed.emit(self.kind, v))
        layout.addWidget(self.solo_btn)

        # Steps
        self.steps_container = QWidget()
        self.steps_layout = QHBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(1)
        self._rebuild_cells(steps)
        layout.addWidget(self.steps_container, stretch=1)

        # Sample picker
        self.sample_combo = QComboBox()
        self.sample_combo.setMinimumWidth(140)
        self.sample_combo.setToolTip("Force a specific sample (or Auto)")
        self.sample_combo.currentIndexChanged.connect(self._on_sample)
        layout.addWidget(self.sample_combo)

        self._updating_combo = False

    def _rebuild_cells(self, steps: int) -> None:
        while self.steps_layout.count():
            item = self.steps_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.cells.clear()
        self.steps = steps
        for i in range(steps):
            cell = StepCell(i, self.kind)
            cell.toggled.connect(self.step_toggled.emit)
            self.cells.append(cell)
            self.steps_layout.addWidget(cell)
            # Visual group separator every 4 / 8 steps
            if (i + 1) % 4 == 0 and i + 1 < steps:
                sep = QFrame()
                sep.setFixedWidth(4)
                sep.setStyleSheet("background: transparent;")
                self.steps_layout.addWidget(sep)

    def set_steps(self, steps: int) -> None:
        if steps != self.steps:
            self._rebuild_cells(steps)

    def set_pattern_row(self, pattern: Pattern) -> None:
        steps_map = {}
        for e in pattern.events_for(self.kind):
            steps_map[e.step] = e.velocity
        for cell in self.cells:
            if cell.step in steps_map:
                cell.set_event(True, steps_map[cell.step])
            else:
                cell.set_event(False)

    def set_samples(self, names: list[tuple[str, object]]) -> None:
        """names: list of (display_name, path_or_None). First is always Auto."""
        self._updating_combo = True
        self.sample_combo.clear()
        for name, path in names:
            self.sample_combo.addItem(name, path)
        self._updating_combo = False

    def set_track_state(self, st: TrackState) -> None:
        self.lock_btn.blockSignals(True)
        self.lock_btn.setChecked(st.locked)
        self.lock_btn.setText("🔒" if st.locked else "🔓")
        self.lock_btn.blockSignals(False)

        self.mute_btn.blockSignals(True)
        self.mute_btn.setChecked(st.muted)
        self.mute_btn.blockSignals(False)

        self.solo_btn.blockSignals(True)
        self.solo_btn.setChecked(st.solo)
        self.solo_btn.blockSignals(False)

        if st.forced_sample is not None:
            idx = self.sample_combo.findData(st.forced_sample)
            if idx >= 0:
                self._updating_combo = True
                self.sample_combo.setCurrentIndex(idx)
                self._updating_combo = False

    def _on_lock(self, locked: bool) -> None:
        self.lock_btn.setText("🔒" if locked else "🔓")
        self.lock_changed.emit(self.kind, locked)

    def _on_sample(self, _idx: int) -> None:
        if self._updating_combo:
            return
        path = self.sample_combo.currentData()
        self.sample_chosen.emit(self.kind, path)


class SequencerWidget(QWidget):
    """Full multi-track sequencer."""

    lock_changed = Signal(object, bool)
    mute_changed = Signal(object, bool)
    solo_changed = Signal(object, bool)
    step_toggled = Signal(int, object)
    sample_chosen = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: dict[SampleType, TrackRow] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        for kind in SampleType:
            row = TrackRow(kind, 16)
            row.lock_changed.connect(self.lock_changed)
            row.mute_changed.connect(self.mute_changed)
            row.solo_changed.connect(self.solo_changed)
            row.step_toggled.connect(self.step_toggled)
            row.sample_chosen.connect(self.sample_chosen)
            self.rows[kind] = row
            layout.addWidget(row)

        layout.addStretch()

    def set_steps(self, steps: int) -> None:
        for row in self.rows.values():
            row.set_steps(steps)

    def set_pattern(self, pattern: Pattern) -> None:
        for kind, row in self.rows.items():
            row.set_pattern_row(pattern)

    def set_samples_for(self, kind: SampleType, names: list[tuple[str, object]]) -> None:
        self.rows[kind].set_samples(names)

    def set_track_states(self, states: dict[SampleType, TrackState]) -> None:
        for kind, st in states.items():
            if kind in self.rows:
                self.rows[kind].set_track_state(st)
