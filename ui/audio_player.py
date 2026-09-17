"""
Audio player — Qt Multimedia only (no sounddevice).

sounddevice + threads caused intermittent PortAudio double-free crashes.
Two independent QMediaPlayer instances handle the full beat and oneshot
previews safely on the GUI thread.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

from PySide6.QtCore import QObject, QUrl, Signal, QTimer
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


def _to_stereo(audio: np.ndarray) -> np.ndarray:
    a = np.asarray(audio, dtype=np.float32)
    if a.ndim == 1:
        return np.column_stack([a, a])
    if a.shape[1] == 1:
        return np.column_stack([a[:, 0], a[:, 0]])
    return a[:, :2].copy()


class AudioPlayer(QObject):
    finished = Signal()
    position_changed = Signal(float)
    oneshot_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._audio: Optional[np.ndarray] = None
        self._sr = 44100
        self._playing = False
        self._oneshot_playing = False

        # Main beat player
        self._qt_player = QMediaPlayer(self)
        self._audio_out = QAudioOutput(self)
        self._qt_player.setAudioOutput(self._audio_out)
        self._qt_player.playbackStateChanged.connect(self._on_qt_state)
        self._qt_player.errorOccurred.connect(self._on_qt_error)
        self._tmp_path: Optional[Path] = None

        # Oneshot / sample preview player (independent)
        self._qt_oneshot = QMediaPlayer(self)
        self._oneshot_out = QAudioOutput(self)
        self._qt_oneshot.setAudioOutput(self._oneshot_out)
        self._qt_oneshot.playbackStateChanged.connect(self._on_oneshot_qt_state)
        self._qt_oneshot.errorOccurred.connect(self._on_oneshot_error)
        self._oneshot_tmp: Optional[Path] = None

        self._pos_timer = QTimer(self)
        self._pos_timer.setInterval(50)
        self._pos_timer.timeout.connect(self._emit_position)

    # ------------------------------------------------------------------ main
    def set_audio(self, audio: np.ndarray, sample_rate: int = 44100) -> None:
        self.stop()
        self._audio = _to_stereo(audio)
        self._sr = int(sample_rate)

    def play(self) -> None:
        if self._audio is None or len(self._audio) == 0:
            return
        self.stop()

        self._tmp_path = self._write_temp_wav(self._audio, self._sr)
        self._qt_player.setSource(QUrl.fromLocalFile(str(self._tmp_path)))
        self._audio_out.setVolume(1.0)
        self._qt_player.play()
        self._playing = True
        self._pos_timer.start()

    def stop(self) -> None:
        self._playing = False
        if self._pos_timer.isActive():
            self._pos_timer.stop()
        self._qt_player.stop()
        # Clear source so the temp file can be deleted safely
        self._qt_player.setSource(QUrl())
        self._cleanup_tmp(self._tmp_path)
        self._tmp_path = None

    def is_playing(self) -> bool:
        return self._playing

    # ------------------------------------------------------------------ oneshot
    def play_oneshot(self, audio: np.ndarray, sample_rate: int = 44100) -> None:
        buf = _to_stereo(audio)
        if len(buf) == 0:
            return

        self.stop_oneshot()
        self._oneshot_tmp = self._write_temp_wav(buf, int(sample_rate))
        self._qt_oneshot.setSource(QUrl.fromLocalFile(str(self._oneshot_tmp)))
        self._oneshot_out.setVolume(1.0)
        self._qt_oneshot.play()
        self._oneshot_playing = True

    def stop_oneshot(self) -> None:
        self._oneshot_playing = False
        self._qt_oneshot.stop()
        self._qt_oneshot.setSource(QUrl())
        self._cleanup_tmp(self._oneshot_tmp)
        self._oneshot_tmp = None

    def is_oneshot_playing(self) -> bool:
        return self._oneshot_playing

    # ------------------------------------------------------------------ slots
    def _on_qt_state(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.StoppedState and self._playing:
            self._playing = False
            if self._pos_timer.isActive():
                self._pos_timer.stop()
            self.finished.emit()

    def _on_oneshot_qt_state(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.StoppedState and self._oneshot_playing:
            self._oneshot_playing = False
            self.oneshot_finished.emit()

    def _on_qt_error(self, *_args) -> None:
        self._playing = False
        if self._pos_timer.isActive():
            self._pos_timer.stop()

    def _on_oneshot_error(self, *_args) -> None:
        self._oneshot_playing = False

    def _emit_position(self) -> None:
        if not self._playing:
            return
        self.position_changed.emit(self._qt_player.position() / 1000.0)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _write_temp_wav(audio: np.ndarray, sr: int) -> Path:
        import os
        # Clip to prevent encoder issues
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak > 1.0:
            audio = audio / peak
        fd, name = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        path = Path(name)
        sf.write(str(path), audio, sr, subtype="PCM_16")
        return path

    def _cleanup_tmp(self, path: Optional[Path]) -> None:
        if path is None:
            return
        # Defer deletion so the media backend can release the file handle.
        def _unlink():
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass
        QTimer.singleShot(500, _unlink)
