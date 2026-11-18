"""Захоплення мікрофона через sounddevice (PortAudio) — заміна audio_capture.

Чому sounddevice замість C++ бінарника (legacy/server.cpp): PortAudio C++
працював лише на Linux, під Windows довелось би крос-компілювати бінарник
(неможливо перевірити без Windows-машини). sounddevice — Python-пакет із
готовими wheel-колесами під Linux/Windows/macOS, тож той самий код працює
скрізь без збірки.

Архітектура як у C++ клієнта: аудіо-callback PortAudio має бути коротким і
без блокувань (інакше звук глітчить), тож callback лише кладе кадри у
queue.Queue; усе важче (ресемплінг, VAD) робить окремий потік.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

TARGET_RATE = 16000
BLOCK_FRAMES = 1024


@dataclass
class Device:
    index: int
    name: str
    default_rate: int


def list_input_devices() -> list[Device]:
    devices = []
    for idx, info in enumerate(sd.query_devices()):
        if info["max_input_channels"] > 0:
            devices.append(
                Device(index=idx, name=info["name"], default_rate=int(info["default_samplerate"]))
            )
    return devices


def default_input_device() -> Device | None:
    try:
        idx = sd.default.device[0]
    except Exception:
        idx = None
    devices = list_input_devices()
    if not devices:
        return None
    if idx is not None:
        for d in devices:
            if d.index == idx:
                return d
    return devices[0]


def _resample_linear(pcm: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or len(pcm) == 0:
        return pcm
    duration = len(pcm) / src_rate
    dst_len = max(1, int(round(duration * dst_rate)))
    src_x = np.linspace(0.0, duration, num=len(pcm), endpoint=False)
    dst_x = np.linspace(0.0, duration, num=dst_len, endpoint=False)
    return np.interp(dst_x, src_x, pcm).astype(np.int16)


class MicCapture:
    """Записує з обраного пристрою в окремому потоці sounddevice, видає
    16 кГц mono int16 PCM-байти через callback `on_pcm(bytes)`.
    """

    def __init__(self, device: Device, on_pcm, on_level=None) -> None:
        self.device = device
        self._on_pcm = on_pcm
        self._on_level = on_level
        self._paused = threading.Event()
        self._stream: sd.InputStream | None = None
        self._rate = device.default_rate or TARGET_RATE

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        if self._paused.is_set():
            return
        mono = indata[:, 0] if indata.ndim > 1 else indata
        pcm16 = (mono * 32767.0).astype(np.int16)
        if self._on_level:
            level = float(np.abs(mono).mean()) if len(mono) else 0.0
            self._on_level(level)
        resampled = _resample_linear(pcm16, self._rate, TARGET_RATE)
        self._on_pcm(resampled.tobytes())

    def start(self) -> None:
        self._stream = sd.InputStream(
            device=self.device.index,
            channels=1,
            samplerate=self._rate,
            blocksize=BLOCK_FRAMES,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class PcmFeeder:
    """Буферизує PCM між callback-потоком sounddevice і потоком, що годує
    Segmenter (vad.py) — той самий паттерн, що reader-потік у server.py.
    """

    def __init__(self) -> None:
        self._q: "queue.Queue[bytes | None]" = queue.Queue()

    def push(self, pcm: bytes) -> None:
        self._q.put(pcm)

    def stop(self) -> None:
        self._q.put(None)

    def __iter__(self):
        while True:
            item = self._q.get()
            if item is None:
                return
            yield item
