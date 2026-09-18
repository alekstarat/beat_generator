"""
16/32-step sequencer grid widget.

Shows the FULL pattern length (bars × steps_per_bar), not just one bar.
Horizontal scroll when the grid is wider than the window.
Bar boundaries get a stronger visual separator.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QScrollArea, QSizePolicy,
)

from core.types import SampleType, Pattern, TrackState


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

CELL_W = 18
CELL_H = 26


class StepCell(QWidget):
    toggled = Signal(int, object)            # step, SampleType (LMB)
    preview_requested = Signal(int, object)  # step, SampleType (RMB)

    def __init__(self, step: int, kind: SampleType, parent=None):
        super().__init__(parent)
        self.step = step
        self.kind = kind
        self.active = False
        self.velocity = 0.0
        self.setFixedSize(CELL_W, CELL_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"step {step}  ·  LMB toggle  ·  RMB preview")

    def set_event(self, active: bool, velocity: float = 0.0) -> None:
        self.active = active
        self.velocity = velocity
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggled.emit(self.step, self.kind)
        elif event.button() == Qt.RightButton:
            self.preview_requested.emit(self.step, self.kind)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 2, -1, -2)

        # Downbeat / beat accents relative to local position in bar is handled
        # by parent; here we just use global step for a light grid feel.
        base = QColor("#2c3e50")
        if self.step % 4 == 0:
            base = QColor("#3d566e")

        if self.active:
            c = QColor(TRACK_COLORS[self.kind])
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

        p.drawRoundedRect(rect, 2, 2)
        p.end()


class TrackRow(QWidget):
    lock_changed = Signal(object, bool)
    mute_changed = Signal(object, bool)
    solo_changed = Signal(object, bool)
    step_toggled = Signal(int, object)
    sample_chosen = Signal(object, object)
    sample_lock_changed = Signal(object, bool)
    preview_track = Signal(object)
    preview_step = Signal(int, object)

    def __init__(self, kind: SampleType, total_steps: int, steps_per_bar: int, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.total_steps = total_steps
        self.steps_per_bar = steps_per_bar
        self.cells: list[StepCell] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(3)

        lbl = QLabel(TRACK_LABELS[kind])
        lbl.setFixedWidth(48)
        lbl.setStyleSheet(f"color: {TRACK_COLORS[kind]}; font-weight: 600;")
        layout.addWidget(lbl)

        self.lock_btn = QPushButton("🔓")
        self.lock_btn.setFixedSize(28, 26)
        self.lock_btn.setCheckable(True)
        self.lock_btn.setToolTip("Lock track (keep on generate)")
        self.lock_btn.toggled.connect(self._on_lock)
        layout.addWidget(self.lock_btn)

        self.mute_btn = QPushButton("M")
        self.mute_btn.setFixedSize(24, 26)
        self.mute_btn.setCheckable(True)
        self.mute_btn.setToolTip("Mute")
        self.mute_btn.toggled.connect(lambda v: self.mute_changed.emit(self.kind, v))
        layout.addWidget(self.mute_btn)

        self.solo_btn = QPushButton("S")
        self.solo_btn.setFixedSize(24, 26)
        self.solo_btn.setCheckable(True)
        self.solo_btn.setToolTip("Solo")
        self.solo_btn.toggled.connect(lambda v: self.solo_changed.emit(self.kind, v))
        layout.addWidget(self.solo_btn)

        self.steps_container = QWidget()
        self.steps_layout = QHBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(1)
        self._rebuild_cells(total_steps, steps_per_bar)
        layout.addWidget(self.steps_container)

        self.sample_combo = QComboBox()
        self.sample_combo.setMinimumWidth(120)
        self.sample_combo.setMaximumWidth(180)
        self.sample_combo.setToolTip("Force a specific sample (or Auto)")
        self.sample_combo.currentIndexChanged.connect(self._on_sample)
        layout.addWidget(self.sample_combo)

        self.sample_lock_btn = QPushButton("🔓")
        self.sample_lock_btn.setFixedSize(28, 26)
        self.sample_lock_btn.setCheckable(True)
        self.sample_lock_btn.setToolTip("Lock selected sample (keep it when randomizing samples)")
        self.sample_lock_btn.toggled.connect(self._on_sample_lock)
        layout.addWidget(self.sample_lock_btn)

        self.preview_btn = QPushButton("▶")
        self.preview_btn.setFixedSize(28, 26)
        self.preview_btn.setToolTip("Preview sample for this track")
        self.preview_btn.clicked.connect(lambda: self.preview_track.emit(self.kind))
        layout.addWidget(self.preview_btn)

        self._updating_combo = False

    def _rebuild_cells(self, total_steps: int, steps_per_bar: int) -> None:
        while self.steps_layout.count():
            item = self.steps_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.cells.clear()
        self.total_steps = total_steps
        self.steps_per_bar = steps_per_bar

        for i in range(total_steps):
            cell = StepCell(i, self.kind)
            cell.toggled.connect(self.step_toggled.emit)
            cell.preview_requested.connect(self.preview_step.emit)
            self.cells.append(cell)
            self.steps_layout.addWidget(cell)

            # Beat group (every 4 steps)
            next_i = i + 1
            if next_i < total_steps and next_i % 4 == 0:
                # Stronger separator on bar boundary
                if next_i % steps_per_bar == 0:
                    sep = QFrame()
                    sep.setFixedWidth(6)
                    sep.setStyleSheet("background: #26a69a; border-radius: 1px;")
                    sep.setToolTip(f"bar {next_i // steps_per_bar + 1}")
                    self.steps_layout.addWidget(sep)
                else:
                    sep = QFrame()
                    sep.setFixedWidth(3)
                    sep.setStyleSheet("background: transparent;")
                    self.steps_layout.addWidget(sep)

    def set_length(self, total_steps: int, steps_per_bar: int) -> None:
        if total_steps != self.total_steps or steps_per_bar != self.steps_per_bar:
            self._rebuild_cells(total_steps, steps_per_bar)

    def set_pattern_row(self, pattern: Pattern) -> None:
        steps_map: dict[int, float] = {}
        for e in pattern.events_for(self.kind):
            # keep loudest if duplicates
            if e.step not in steps_map or e.velocity > steps_map[e.step]:
                steps_map[e.step] = e.velocity
        for cell in self.cells:
            if cell.step in steps_map:
                cell.set_event(True, steps_map[cell.step])
            else:
                cell.set_event(False)

    def set_samples(self, names: list[tuple[str, object]]) -> None:
        self._updating_combo = True
        self.sample_combo.clear()
        for name, path in names:
            self.sample_combo.addItem(name, path)
        self._updating_combo = False

    def set_selected_sample(self, path) -> None:
        """Select a sample path without emitting sample_chosen."""
        self._updating_combo = True
        try:
            if path is None:
                self.sample_combo.setCurrentIndex(0 if self.sample_combo.count() else -1)
            else:
                idx = self.sample_combo.findData(path)
                if idx >= 0:
                    self.sample_combo.setCurrentIndex(idx)
        finally:
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

        self.sample_lock_btn.blockSignals(True)
        self.sample_lock_btn.setChecked(getattr(st, "sample_locked", False))
        self.sample_lock_btn.setText("🔒" if getattr(st, "sample_locked", False) else "🔓")
        self.sample_lock_btn.blockSignals(False)

        if st.forced_sample is not None:
            idx = self.sample_combo.findData(st.forced_sample)
            if idx >= 0:
                self._updating_combo = True
                self.sample_combo.setCurrentIndex(idx)
                self._updating_combo = False

    def _on_lock(self, locked: bool) -> None:
        self.lock_btn.setText("🔒" if locked else "🔓")
        self.lock_changed.emit(self.kind, locked)

    def current_sample_path(self):
        return self.sample_combo.currentData()

    def _on_sample_lock(self, locked: bool) -> None:
        self.sample_lock_btn.setText("🔒" if locked else "🔓")
        self.sample_lock_changed.emit(self.kind, locked)

    def _on_sample(self, _idx: int) -> None:
        if self._updating_combo:
            return
        path = self.sample_combo.currentData()
        self.sample_chosen.emit(self.kind, path)
        if path is not None:
            self.preview_track.emit(self.kind)


class StepHeader(QWidget):
    """Ruler above the grid: step numbers + bar labels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.total_steps = 16
        self.steps_per_bar = 16
        self.setFixedHeight(18)

    def set_length(self, total_steps: int, steps_per_bar: int) -> None:
        self.total_steps = total_steps
        self.steps_per_bar = steps_per_bar
        # width follows cells + separators roughly
        n_bar_seps = max(0, (total_steps // steps_per_bar) - 1) if steps_per_bar else 0
        n_beat_seps = max(0, (total_steps // 4) - 1 - n_bar_seps)
        w = total_steps * CELL_W + n_bar_seps * 6 + n_beat_seps * 3 + 4
        self.setFixedWidth(max(w, 100))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setPen(QColor("#78909c"))
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)

        # Mirror TrackRow spacing as closely as possible
        x = 0
        for i in range(self.total_steps):
            if i % self.steps_per_bar == 0:
                bar = i // self.steps_per_bar + 1
                p.setPen(QColor("#80cbc4"))
                p.drawText(x, 0, CELL_W * 2, 16, Qt.AlignLeft | Qt.AlignVCenter, f"B{bar}")
                p.setPen(QColor("#78909c"))
            elif i % 4 == 0:
                local = (i % self.steps_per_bar) + 1
                p.drawText(x, 0, CELL_W, 16, Qt.AlignCenter, str(local))

            x += CELL_W
            next_i = i + 1
            if next_i < self.total_steps and next_i % 4 == 0:
                if next_i % self.steps_per_bar == 0:
                    x += 6
                else:
                    x += 3
        p.end()


class SequencerWidget(QWidget):
    """Full multi-track sequencer with horizontal scroll for long patterns."""

    lock_changed = Signal(object, bool)
    mute_changed = Signal(object, bool)
    solo_changed = Signal(object, bool)
    step_toggled = Signal(int, object)
    sample_chosen = Signal(object, object)
    sample_lock_changed = Signal(object, bool)
    preview_track = Signal(object)
    preview_step = Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: dict[SampleType, TrackRow] = {}
        self.total_steps = 16
        self.steps_per_bar = 16

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # Scrollable grid area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.inner = QWidget()
        self.inner_layout = QVBoxLayout(self.inner)
        self.inner_layout.setContentsMargins(0, 0, 0, 0)
        self.inner_layout.setSpacing(2)

        # Header row: spacer matching controls + ruler
        header_row = QHBoxLayout()
        header_row.setContentsMargins(4, 0, 4, 0)
        header_row.setSpacing(3)
        # match: label 48 + lock 28 + M 24 + S 24 + spacings ≈ 48+28+24+24+3*3 = 133, plus margins
        left_spacer = QWidget()
        left_spacer.setFixedWidth(48 + 28 + 24 + 24 + 12)
        header_row.addWidget(left_spacer)
        self.header = StepHeader()
        header_row.addWidget(self.header)
        header_row.addStretch()
        self.inner_layout.addLayout(header_row)

        for kind in SampleType:
            row = TrackRow(kind, self.total_steps, self.steps_per_bar)
            row.lock_changed.connect(self.lock_changed)
            row.mute_changed.connect(self.mute_changed)
            row.solo_changed.connect(self.solo_changed)
            row.step_toggled.connect(self.step_toggled)
            row.sample_chosen.connect(self.sample_chosen)
            row.sample_lock_changed.connect(self.sample_lock_changed)
            row.preview_track.connect(self.preview_track)
            row.preview_step.connect(self.preview_step)
            self.rows[kind] = row
            self.inner_layout.addWidget(row)

        self.inner_layout.addStretch()
        self.scroll.setWidget(self.inner)
        outer.addWidget(self.scroll)

        self.info = QLabel("")
        self.info.setStyleSheet("color: #78909c; font-size: 11px;")
        outer.addWidget(self.info)

    def set_length(self, bars: int, steps_per_bar: int) -> None:
        total = max(1, bars) * steps_per_bar
        self.total_steps = total
        self.steps_per_bar = steps_per_bar
        self.header.set_length(total, steps_per_bar)
        for row in self.rows.values():
            row.set_length(total, steps_per_bar)
        self.info.setText(
            f"{bars} bar{'s' if bars != 1 else ''} × {steps_per_bar} steps  "
            f"= {total} steps total  (teal line = bar boundary)"
        )

    def set_steps(self, steps: int) -> None:
        """Backward-compatible: treat as steps_per_bar, keep current bar count."""
        bars = max(1, self.total_steps // self.steps_per_bar) if self.steps_per_bar else 1
        self.set_length(bars, steps)

    def set_pattern(self, pattern: Pattern) -> None:
        # Sync grid length to pattern settings before painting hits
        bars = pattern.settings.bars
        spb = pattern.settings.steps_per_bar
        self.set_length(bars, spb)
        for kind, row in self.rows.items():
            row.set_pattern_row(pattern)

        n_events = len(pattern.events)
        shown = sum(1 for e in pattern.events if 0 <= e.step < self.total_steps)
        self.info.setText(
            f"{bars} bar{'s' if bars != 1 else ''} × {spb} steps  ·  "
            f"{n_events} hits  ·  seed {pattern.seed_used}"
            + (f"  ·  ⚠ {n_events - shown} off-grid" if shown < n_events else "")
        )

    def set_samples_for(self, kind: SampleType, names: list[tuple[str, object]]) -> None:
        self.rows[kind].set_samples(names)

    def set_selected_sample(self, kind: SampleType, path) -> None:
        if kind in self.rows:
            self.rows[kind].set_selected_sample(path)

    def set_sample_locked(self, kind: SampleType, locked: bool) -> None:
        if kind not in self.rows:
            return
        row = self.rows[kind]
        row.sample_lock_btn.blockSignals(True)
        row.sample_lock_btn.setChecked(locked)
        row.sample_lock_btn.setText("🔒" if locked else "🔓")
        row.sample_lock_btn.blockSignals(False)

    def set_track_states(self, states: dict[SampleType, TrackState]) -> None:
        for kind, st in states.items():
            if kind in self.rows:
                self.rows[kind].set_track_state(st)
