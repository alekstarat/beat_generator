"""
Simple in-memory audio player using sounddevice (optional) or a fallback
thread that writes a temp WAV and plays via system tools.

We prefer sounddevice if available; otherwise we use QMediaPlayer via a
temporary file so the UI still works without extra deps.
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False

from PySide6.QtCore import QObject, QUrl, Signal, QTimer
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class AudioPlayer(QObject):
    """Plays a stereo float32 numpy buffer."""

    finished = Signal()
    position_changed = Signal(float)  # seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self._audio: Optional[np.ndarray] = None
        self._sr = 44100
        self._playing = False
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()

        # Fallback Qt player
        self._qt_player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._qt_player.setAudioOutput(self._audio_out)
        self._qt_player.playbackStateChanged.connect(self._on_qt_state)
        self._tmp_path: Optional[Path] = None

        self._pos_timer = QTimer(self)
        self._pos_timer.setInterval(50)
        self._pos_timer.timeout.connect(self._emit_position)

    def set_audio(self, audio: np.ndarray, sample_rate: int = 44100) -> None:
        self.stop()
        self._audio = np.asarray(audio, dtype=np.float32)
        self._sr = sample_rate

    def play(self) -> None:
        if self._audio is None or len(self._audio) == 0:
            return
        self.stop()
        self._stop_flag.clear()

        if HAS_SOUNDDEVICE:
            self._playing = True
            self._thread = threading.Thread(target=self._play_sd, daemon=True)
            self._thread.start()
            self._pos_timer.start()
        else:
            # Write temp WAV and use Qt
            fd, name = tempfile.mkstemp(suffix=".wav")
            import os
            os.close(fd)
            self._tmp_path = Path(name)
            sf.write(str(self._tmp_path), self._audio, self._sr, subtype="PCM_16")
            self._qt_player.setSource(QUrl.fromLocalFile(str(self._tmp_path)))
            self._audio_out.setVolume(1.0)
            self._qt_player.play()
            self._playing = True
            self._pos_timer.start()

    def stop(self) -> None:
        self._stop_flag.set()
        self._playing = False
        self._pos_timer.stop()
        if HAS_SOUNDDEVICE:
            try:
                sd.stop()
            except Exception:
                pass
        self._qt_player.stop()
        if self._tmp_path and self._tmp_path.exists():
            try:
                self._tmp_path.unlink()
            except Exception:
                pass
            self._tmp_path = None

    def is_playing(self) -> bool:
        return self._playing

    def _play_sd(self) -> None:
        try:
            sd.play(self._audio, self._sr, blocking=True)
        except Exception:
            pass
        self._playing = False
        self._pos_timer.stop()
        self.finished.emit()

    def _on_qt_state(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.StoppedState and self._playing:
            self._playing = False
            self._pos_timer.stop()
            self.finished.emit()

    def _emit_position(self) -> None:
        if not self._playing:
            return
        if HAS_SOUNDDEVICE:
            # sounddevice doesn't expose easy position; skip precise cursor
            return
        pos_ms = self._qt_player.position()
        self.position_changed.emit(pos_ms / 1000.0)
