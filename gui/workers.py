"""Конвеєр VAD -> Whisper -> Claude -> локальний конспект, усередині GUI-процесу.

Той самий поділ на потоки, що був у server.py (reader/transcribe/polish), і з
тієї самої причини: поки Claude дописує фрагмент (найповільніший крок),
Whisper не має чекати — наступний сегмент мовлення вже розпізнається.
Різниця лише в тому, що замість TCP-сокета джерело PCM — callback sounddevice
(audio_io.py), а замість Google Docs — LocalNotesStore; результати йдуть у
GUI через Qt-сигнали (автоматично queued між потоками), а не через лог.
"""

from __future__ import annotations

import queue
import threading

from PySide6.QtCore import QObject, Signal

from audio_io import Device, MicCapture, PcmFeeder
from mdlite import Block
from vad import Segmenter

TARGET_RATE = 16000


class TranscriptionPipeline(QObject):
    heard = Signal(str)
    noteBlocks = Signal(list)
    levelChanged = Signal(float)
    statusChanged = Signal(str)
    # Секунди реально розпізнаного мовлення — з цього рахується квота плану
    # (тиша між репліками не списується, бо VAD її й не віддає).
    usageSeconds = Signal(float)

    def __init__(self, notes_builder, store, queue_max: int = 16) -> None:
        super().__init__()
        self.notes = notes_builder
        self.store = store
        self._queue_max = queue_max
        self._audio_q: "queue.Queue" = queue.Queue(maxsize=queue_max)
        self._text_q: "queue.Queue" = queue.Queue(maxsize=queue_max)
        self._feeder = PcmFeeder()
        self._segmenter = Segmenter(sample_rate=TARGET_RATE)
        self._mic: MicCapture | None = None
        self._threads: list[threading.Thread] = []

    # --------------------------------------------------------------- lifecycle

    def start(self, device: Device) -> None:
        self._mic = MicCapture(
            device, on_pcm=self._feeder.push, on_level=self.levelChanged.emit
        )
        self._mic.start()
        self._threads = [
            threading.Thread(target=self._feed_loop, name="feed", daemon=True),
            threading.Thread(target=self._transcribe_loop, name="transcribe", daemon=True),
            threading.Thread(target=self._polish_loop, name="polish", daemon=True),
        ]
        for t in self._threads:
            t.start()
        self.statusChanged.emit(f"Запис: {device.name}")

    def pause(self) -> None:
        if self._mic:
            self._mic.pause()

    def resume(self) -> None:
        if self._mic:
            self._mic.resume()

    def stop(self) -> None:
        if self._mic:
            self._mic.stop()
            self._mic = None
        self._feeder.stop()

    # ------------------------------------------------------------------ loops

    def _feed_loop(self) -> None:
        for pcm in self._feeder:
            for seg in self._segmenter.feed(pcm):
                self._enqueue(self._audio_q, seg)
        for seg in self._segmenter.flush():
            self._enqueue(self._audio_q, seg)
        self._audio_q.put(None)

    def _transcribe_loop(self) -> None:
        while True:
            segment = self._audio_q.get()
            try:
                if segment is None:
                    self._text_q.put(None)
                    return
                raw = self.notes.transcribe(segment.pcm, segment.sample_rate)
                if not raw:
                    continue
                self.usageSeconds.emit(segment.duration)
                self.heard.emit(raw)
                pending_id = self.store.insert_pending(raw)
                self._enqueue(self._text_q, (raw, pending_id, segment.cut_mid_sentence))
            except Exception as exc:  # noqa: BLE001 — один сегмент не має валити конвеєр
                self.statusChanged.emit(f"Помилка розпізнавання: {exc}")
            finally:
                self._audio_q.task_done()

    def _polish_loop(self) -> None:
        while True:
            item = self._text_q.get()
            try:
                if item is None:
                    return
                raw, pending_id, cut_mid = item
                result = self.notes.polish(raw, cut_mid_sentence=cut_mid)
                if result is None:
                    section_id, blocks = None, [Block("para", raw)]
                else:
                    section_id, blocks = result
                self.store.commit(pending_id, blocks, target_section_id=section_id)
                self.noteBlocks.emit(blocks)
            except Exception as exc:  # noqa: BLE001
                self.statusChanged.emit(f"Помилка конспектування: {exc}")
            finally:
                self._text_q.task_done()

    @staticmethod
    def _enqueue(q: "queue.Queue", item) -> None:
        try:
            q.put_nowait(item)
            return
        except queue.Full:
            pass
        try:
            q.get_nowait()
            q.task_done()
        except queue.Empty:
            pass
        try:
            q.put_nowait(item)
        except queue.Full:
            pass
