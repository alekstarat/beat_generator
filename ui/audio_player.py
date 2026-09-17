"""
Audio player based on QAudioSink.

Unlike QMediaPlayer, this class sends PCM audio directly to Qt's
audio output layer. This avoids Windows Media Foundation / WAV backend
issues when playing rendered audio buffers.

Input:
    numpy.ndarray
        mono or stereo float32 audio in range [-1.0, 1.0]

Output:
    QAudioSink -> default system audio device
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from PySide6.QtCore import QObject, QIODevice, QTimer, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSink


def _to_stereo(audio: np.ndarray) -> np.ndarray:
    """
    Convert audio to contiguous stereo float32.

    Accepted:
        (N,)      -> duplicated to L/R
        (N, 1)    -> duplicated to L/R
        (N, 2+)   -> first two channels

    Returns:
        (N, 2) float32 contiguous array.
    """
    a = np.asarray(audio, dtype=np.float32)

    if a.size == 0:
        return np.empty((0, 2), dtype=np.float32)

    if a.ndim == 1:
        a = np.column_stack((a, a))

    elif a.ndim == 2:
        if a.shape[1] == 1:
            a = np.column_stack((a[:, 0], a[:, 0]))
        else:
            a = a[:, :2]

    else:
        raise ValueError(
            f"Unsupported audio shape: {a.shape}. "
            "Expected (N,), (N,1) or (N,2)."
        )

    # Remove NaN / +/-Inf that could otherwise poison the PCM stream.
    a = np.nan_to_num(
        a,
        nan=0.0,
        posinf=1.0,
        neginf=-1.0,
    )

    # Keep audio in the valid floating-point range.
    np.clip(a, -1.0, 1.0, out=a)

    return np.ascontiguousarray(a, dtype=np.float32)


def _float_to_pcm16(audio: np.ndarray) -> bytes:
    """
    Convert float32 [-1, 1] stereo audio to interleaved signed PCM16.
    """
    a = _to_stereo(audio)

    if len(a) == 0:
        return b""

    # Use symmetric-ish scaling and prevent integer overflow.
    pcm = np.clip(a * 32767.0, -32768.0, 32767.0).astype(
        np.int16,
        copy=False,
    )

    return pcm.tobytes()


class _AudioBufferDevice(QIODevice):
    """
    QIODevice backed by an immutable PCM byte buffer.

    QAudioSink operates in pull mode and repeatedly calls readData().
    """

    def __init__(self, data: bytes, parent: Optional[QObject] = None):
        super().__init__(parent)

        self._data = data
        self._position = 0

    def start(self) -> None:
        self._position = 0
        self.open(QIODevice.OpenModeFlag.ReadOnly)

    def stop(self) -> None:
        if self.isOpen():
            self.close()

    def readData(self, maxlen: int) -> bytes:
        if maxlen <= 0:
            return b""

        remaining = len(self._data) - self._position

        if remaining <= 0:
            return b""

        count = min(maxlen, remaining)

        chunk = self._data[
            self._position:self._position + count
        ]

        self._position += count
        return chunk

    def writeData(self, data: bytes) -> int:
        # This device is read-only.
        return -1

    def bytesAvailable(self) -> int:
        remaining = len(self._data) - self._position
        return max(0, remaining) + super().bytesAvailable()

    def atEnd(self) -> bool:
        return self._position >= len(self._data)


class AudioPlayer(QObject):
    """
    Main beat player + independent one-shot preview player.

    Public API intentionally remains compatible with the previous
    QMediaPlayer implementation:

        set_audio()
        play()
        stop()
        is_playing()

        play_oneshot()
        stop_oneshot()
        is_oneshot_playing()

    Signals:

        finished
        position_changed
        oneshot_finished
    """

    finished = Signal()
    position_changed = Signal(float)
    oneshot_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # ------------------------------------------------------------
        # Main beat
        # ------------------------------------------------------------

        self._audio: Optional[np.ndarray] = None
        self._sr = 44100

        self._playing = False
        self._pcm_data: bytes = b""
        self._device: Optional[_AudioBufferDevice] = None
        self._sink: Optional[QAudioSink] = None

        self._duration = 0.0

        # ------------------------------------------------------------
        # One-shot preview
        # ------------------------------------------------------------

        self._oneshot_playing = False
        self._oneshot_pcm_data: bytes = b""
        self._oneshot_device: Optional[_AudioBufferDevice] = None
        self._oneshot_sink: Optional[QAudioSink] = None
        self._oneshot_duration = 0.0

        # ------------------------------------------------------------
        # Position timer
        # ------------------------------------------------------------

        self._pos_timer = QTimer(self)
        self._pos_timer.setInterval(30)
        self._pos_timer.timeout.connect(self._emit_position)

    # ================================================================
    # Main beat
    # ================================================================

    def set_audio(
        self,
        audio: np.ndarray,
        sample_rate: int = 44100,
    ) -> None:
        """
        Store the rendered beat.

        The actual PCM conversion happens here so that playback itself
        does not have to perform NumPy conversion.
        """
        self.stop()

        if sample_rate <= 0:
            raise ValueError(
                f"Invalid sample rate: {sample_rate}"
            )

        stereo = _to_stereo(audio)

        self._audio = stereo
        self._sr = int(sample_rate)

        self._pcm_data = _float_to_pcm16(stereo)

        bytes_per_frame = 2 * 2  # stereo * int16
        frames = len(self._pcm_data) // bytes_per_frame

        self._duration = (
            frames / self._sr
            if self._sr > 0
            else 0.0
        )

    def play(self) -> None:
        """
        Start playback from the beginning.
        """
        if self._audio is None or len(self._audio) == 0:
            return

        self.stop()

        if not self._pcm_data:
            return

        fmt = self._make_format(self._sr)

        device = _AudioBufferDevice(
            self._pcm_data,
            self,
        )
        device.start()

        sink = QAudioSink(
            fmt,
            self,
        )

        sink.setVolume(1.0)

        # Store references before starting playback.
        self._device = device
        self._sink = sink
        self._playing = True

        sink.stateChanged.connect(self._on_main_state_changed)

        sink.start(device)

        if sink.error() != QAudioSink.Error.NoError:
            self._handle_main_error()

            return

        self._pos_timer.start()

    def stop(self) -> None:
        """
        Stop main playback immediately.
        """
        was_playing = self._playing

        self._playing = False

        if self._pos_timer.isActive():
            self._pos_timer.stop()

        if self._sink is not None:
            try:
                self._sink.stop()
            except Exception:
                pass

            self._sink.deleteLater()

        self._sink = None

        if self._device is not None:
            try:
                self._device.stop()
            except Exception:
                pass

            self._device.deleteLater()

        self._device = None

        if was_playing:
            self.position_changed.emit(0.0)

    def is_playing(self) -> bool:
        return self._playing

    # ================================================================
    # One-shot
    # ================================================================

    def play_oneshot(
        self,
        audio: np.ndarray,
        sample_rate: int = 44100,
    ) -> None:
        """
        Play a sample preview independently from the main beat.
        """
        if sample_rate <= 0:
            return

        stereo = _to_stereo(audio)

        if len(stereo) == 0:
            return

        self.stop_oneshot()

        pcm_data = _float_to_pcm16(stereo)

        if not pcm_data:
            return

        fmt = self._make_format(int(sample_rate))

        device = _AudioBufferDevice(
            pcm_data,
            self,
        )
        device.start()

        sink = QAudioSink(
            fmt,
            self,
        )

        sink.setVolume(1.0)

        self._oneshot_pcm_data = pcm_data
        self._oneshot_device = device
        self._oneshot_sink = sink
        self._oneshot_playing = True

        bytes_per_frame = 2 * 2
        frames = len(pcm_data) // bytes_per_frame

        self._oneshot_duration = (
            frames / sample_rate
        )

        sink.stateChanged.connect(
            self._on_oneshot_state_changed
        )

        sink.start(device)

        if sink.error() != QAudioSink.Error.NoError:
            self._handle_oneshot_error()

    def stop_oneshot(self) -> None:
        """
        Stop sample preview.
        """
        self._oneshot_playing = False

        if self._oneshot_sink is not None:
            try:
                self._oneshot_sink.stop()
            except Exception:
                pass

            self._oneshot_sink.deleteLater()

        self._oneshot_sink = None

        if self._oneshot_device is not None:
            try:
                self._oneshot_device.stop()
            except Exception:
                pass

            self._oneshot_device.deleteLater()

        self._oneshot_device = None
        self._oneshot_pcm_data = b""
        self._oneshot_duration = 0.0

    def is_oneshot_playing(self) -> bool:
        return self._oneshot_playing

    # ================================================================
    # Main playback state
    # ================================================================

    def _on_main_state_changed(self, state) -> None:
        if not self._playing:
            return

        if state == QAudioSink.State.IdleState:
            # QAudioSink reaches IdleState when the entire buffer
            # has been consumed.
            self._playing = False

            if self._pos_timer.isActive():
                self._pos_timer.stop()

            self.position_changed.emit(self._duration)
            self.finished.emit()

            self._release_main_resources()

        elif state == QAudioSink.State.StoppedState:
            # StoppedState can also happen because of stop().
            # Do not emit finished in that case.
            if self._playing:
                self._playing = False

                if self._pos_timer.isActive():
                    self._pos_timer.stop()

                self.finished.emit()

                self._release_main_resources()

        elif state == QAudioSink.State.SuspendedState:
            # Do nothing. Audio can be resumed by Qt if appropriate.
            pass

    def _handle_main_error(self) -> None:
        self._playing = False

        if self._pos_timer.isActive():
            self._pos_timer.stop()

        self._release_main_resources()

    # ================================================================
    # One-shot state
    # ================================================================

    def _on_oneshot_state_changed(self, state) -> None:
        if not self._oneshot_playing:
            return

        if state == QAudioSink.State.IdleState:
            self._oneshot_playing = False

            self.oneshot_finished.emit()

            self._release_oneshot_resources()

        elif state == QAudioSink.State.StoppedState:
            self._oneshot_playing = False

            self._release_oneshot_resources()

    def _handle_oneshot_error(self) -> None:
        self._oneshot_playing = False
        self._release_oneshot_resources()

    # ================================================================
    # Position
    # ================================================================

    def _emit_position(self) -> None:
        if not self._playing:
            return

        if self._sink is None:
            return

        try:
            position = self._sink.processedUSecs() / 1_000_000.0
        except Exception:
            return

        position = max(
            0.0,
            min(position, self._duration),
        )

        self.position_changed.emit(position)

    # ================================================================
    # Helpers
    # ================================================================

    @staticmethod
    def _make_format(sample_rate: int) -> QAudioFormat:
        """
        Create the exact PCM format used by _float_to_pcm16().
        """
        fmt = QAudioFormat()

        fmt.setSampleRate(int(sample_rate))
        fmt.setChannelCount(2)
        fmt.setSampleFormat(
            QAudioFormat.SampleFormat.Int16
        )

        return fmt

    def _release_main_resources(self) -> None:
        sink = self._sink
        device = self._device

        self._sink = None
        self._device = None

        if sink is not None:
            try:
                sink.stop()
            except Exception:
                pass

            sink.deleteLater()

        if device is not None:
            try:
                device.stop()
            except Exception:
                pass

            device.deleteLater()

    def _release_oneshot_resources(self) -> None:
        sink = self._oneshot_sink
        device = self._oneshot_device

        self._oneshot_sink = None
        self._oneshot_device = None
        self._oneshot_pcm_data = b""
        self._oneshot_duration = 0.0

        if sink is not None:
            try:
                sink.stop()
            except Exception:
                pass

            sink.deleteLater()

        if device is not None:
            try:
                device.stop()
            except Exception:
                pass

            device.deleteLater()