"""Різка аудіопотоку на репліки за паузами (VAD на енергії).

Чому не по таймеру: фіксовані 15 с ріжуть слова навпіл, Whisper втрачає межі
речень, а Claude отримує уривок без початку думки. Тут ми ріжемо там, де людина
справді зробила паузу, і додаємо преролл, щоб не з'їдати перший склад.

Реалізація без webrtcvad/scipy — тільки numpy, з адаптивним шумовим порогом,
який сам підстроюється під аудиторію/мікрофон.
"""

from collections import deque
from dataclasses import dataclass

import numpy as np

FRAME_MS = 20  # довжина кадру аналізу


@dataclass
class Segment:
    pcm: bytes  # mono int16 LE
    sample_rate: int
    duration: float
    forced: bool  # True -> різали не на паузі, а по ліміту довжини

    @property
    def cut_mid_sentence(self) -> bool:
        return self.forced


class Segmenter:
    def __init__(
        self,
        sample_rate: int = 16000,
        min_speech: float = 1.2,      # коротші сегменти вважаємо шумом
        max_speech: float = 25.0,     # запобіжник: не тримати нескінченний монолог
        silence_to_cut: float = 0.7,  # пауза, після якої ріжемо
        preroll: float = 0.3,         # скільки звуку ДО початку мовлення лишати
        tail_keep: float = 0.2,       # скільки тишi лишати в хвості сегмента
        start_frames: int = 3,        # стільки кадрів підряд, щоб визнати мовлення
        noise_ratio: float = 3.0,     # у скільки разів мовлення гучніше за шум
        abs_floor: float = 0.004,     # абсолютна підлога (тиша в цифрі не нульова)
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_samples = sample_rate * FRAME_MS // 1000
        self.frame_bytes = self.frame_samples * 2

        self.min_bytes = int(min_speech * sample_rate) * 2
        self.max_bytes = int(max_speech * sample_rate) * 2
        self.silence_frames = max(1, int(silence_to_cut * 1000 / FRAME_MS))
        self.tail_frames = max(0, int(tail_keep * 1000 / FRAME_MS))
        self.start_frames = start_frames
        self.noise_ratio = noise_ratio
        self.abs_floor = abs_floor

        self._pending = bytearray()                                  # неповний кадр
        self._preroll: deque[bytes] = deque(maxlen=max(1, int(preroll * 1000 / FRAME_MS)))
        self._current = bytearray()                                  # поточний сегмент
        self._in_speech = False
        self._voiced_run = 0
        self._silence_run = 0
        self._noise = None

        # Статистика — щоб було видно, що саме відкидається.
        self.discarded_short = 0
        self.forced_cuts = 0

    # ------------------------------------------------------------------ public

    def feed(self, chunk: bytes) -> list[Segment]:
        """Додати сирі байти з сокета, отримати готові до розпізнавання сегменти."""
        self._pending.extend(chunk)
        out: list[Segment] = []

        while len(self._pending) >= self.frame_bytes:
            frame = bytes(self._pending[: self.frame_bytes])
            del self._pending[: self.frame_bytes]
            seg = self._process_frame(frame)
            if seg is not None:
                out.append(seg)
        return out

    def flush(self) -> list[Segment]:
        """Кінець потоку: віддати те, що ще накопичилось."""
        out = []
        if self._in_speech and len(self._current) >= self.min_bytes:
            out.append(self._emit(forced=False))
        self._reset_segment()
        self._pending.clear()
        return out

    # ----------------------------------------------------------------- internal

    def _rms(self, frame: bytes) -> float:
        samples = np.frombuffer(frame, dtype="<i2").astype(np.float32) / 32768.0
        return float(np.sqrt(np.mean(samples * samples)) + 1e-9)

    def _update_noise(self, rms: float) -> None:
        if self._noise is None:
            self._noise = rms
        elif rms < self._noise:
            self._noise = 0.9 * self._noise + 0.1 * rms      # швидко вниз
        else:
            self._noise = 0.995 * self._noise + 0.005 * rms  # повільно вгору

    def _process_frame(self, frame: bytes) -> Segment | None:
        rms = self._rms(frame)
        self._update_noise(rms)
        threshold = max(self._noise * self.noise_ratio, self.abs_floor)
        is_speech = rms > threshold

        if not self._in_speech:
            self._preroll.append(frame)
            self._voiced_run = self._voiced_run + 1 if is_speech else 0
            if self._voiced_run >= self.start_frames:
                self._in_speech = True
                self._current = bytearray(b"".join(self._preroll))
                self._preroll.clear()
                self._silence_run = 0
            return None

        self._current.extend(frame)
        self._silence_run = 0 if is_speech else self._silence_run + 1

        if self._silence_run >= self.silence_frames:
            if len(self._current) >= self.min_bytes:
                return self._emit(forced=False)
            # Занадто коротко — це був стук/кашель, а не репліка.
            self.discarded_short += 1
            self._reset_segment()
            return None

        if len(self._current) >= self.max_bytes:
            self.forced_cuts += 1
            seg = self._emit(forced=True)
            # Людина ще говорить: продовжуємо новий сегмент без преролла.
            self._in_speech = True
            self._current = bytearray()
            self._silence_run = 0
            return seg

        return None

    def _emit(self, forced: bool) -> Segment:
        pcm = bytes(self._current)
        if not forced and self._silence_run > self.tail_frames:
            # Обрізаємо надлишкову тишу в хвості, лишаючи tail_keep.
            drop = (self._silence_run - self.tail_frames) * self.frame_bytes
            if drop < len(pcm):
                pcm = pcm[: len(pcm) - drop]
        self._reset_segment()
        return Segment(
            pcm=pcm,
            sample_rate=self.sample_rate,
            duration=len(pcm) / 2 / self.sample_rate,
            forced=forced,
        )

    def _reset_segment(self) -> None:
        self._current = bytearray()
        self._in_speech = False
        self._voiced_run = 0
        self._silence_run = 0
