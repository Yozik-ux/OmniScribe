"""OmniScribe: приймає аудіопотік, пише конспект у Google Docs у реальному часі.

Архітектура (чотири незалежні потоки, щоб мережа ніколи не чекала на API):

    C++ клієнт --TCP--> [reader] --VAD--> audio_q --> [transcriber] --> text_q --> [composer] --> Google Docs
                         тільки recv       сегменти    Whisper            текст      Claude + запис

Раніше обробка викликалась із recv-циклу: поки йшли Whisper і Claude (кілька
секунд), conn.recv() не викликався, TCP-буфер набивався, backpressure доходив до
C++ і вбивав аудіо-callback. Тепер reader лише читає.

Транскрибування й конспектування теж розділені на окремі потоки: раніше один
воркер робив Whisper → Claude → запис послідовно, і поки Claude (найповільніший
крок) дописував фрагмент, наступний шматок мовлення чекав розпізнавання.
Тепер transcriber безперервно забирає аудіо з audio_q і кладе розпізнаний текст
у text_q, а composer окремим потоком забирає звідти й пише в Docs — Claude
більше не блокує Whisper, і контекст лекції не втрачається через черговість.
"""

import io
import queue
import signal
import socket
import struct
import sys
import threading
from dataclasses import dataclass

from config import Config
from mdlite import Block
from vad import Segmenter

# Windows-консоль інакше падає на кирилиці.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

MAGIC = b"CNSP"
HEADER_SIZE = 8
RECV_SIZE = 4096

_stop = threading.Event()


# ---------------------------------------------------------------------- воркер


@dataclass
class Transcribed:
    raw: str
    pending: str | None
    cut_mid_sentence: bool


def transcribe_loop(audio_q: "queue.Queue", text_q: "queue.Queue", notes, writer) -> None:
    """Безперервно розпізнає аудіо (Whisper) — не чекає, поки Claude допише
    попередній фрагмент, тому мовлення ніколи не втрачає контекст черговістю.
    """
    while True:
        segment = audio_q.get()
        try:
            if segment is None:
                text_q.put(None)  # передати сигнал завершення далі по конвеєру
                return
            _transcribe_segment(segment, text_q, notes, writer)
        except Exception as exc:  # noqa: BLE001 — один поганий сегмент не валить сесію
            print(f"❌ Помилка розпізнавання: {exc}", flush=True)
        finally:
            audio_q.task_done()


def _transcribe_segment(segment, text_q: "queue.Queue", notes, writer) -> None:
    print(f"\n⏳ Розпізнаю {segment.duration:.1f} с…", flush=True)
    raw = notes.transcribe(segment.pcm, segment.sample_rate)
    if not raw:
        print("   тиша або шум — пропускаю.", flush=True)
        return

    print(f"🎤 {raw}", flush=True)

    # Чернетку видно студенту одразу, ще до Claude.
    pending = writer.insert_pending(raw) if writer else None

    _enqueue(
        text_q,
        Transcribed(raw=raw, pending=pending, cut_mid_sentence=segment.cut_mid_sentence),
        describe=lambda t: f"розпізнаний текст ({len(t.raw)} символів)",
    )


def polish_loop(text_q: "queue.Queue", notes, writer) -> None:
    """Окремий потік: Claude формує конспект і пише в Docs, без очікування —
    поки він працює, transcribe_loop вже розпізнає наступний фрагмент.
    """
    while True:
        item = text_q.get()
        try:
            if item is None:
                return
            _polish_item(item, notes, writer)
        except Exception as exc:  # noqa: BLE001 — один поганий фрагмент не валить сесію
            print(f"❌ Помилка конспектування: {exc}", flush=True)
        finally:
            text_q.task_done()


def _polish_item(item: "Transcribed", notes, writer) -> None:
    result = notes.polish(item.raw, cut_mid_sentence=item.cut_mid_sentence)
    if result is None:
        # Claude не спрацював — краще лишити сирий текст, ніж нічого.
        section_id, blocks = None, [Block("para", item.raw)]
        print("📝 (сирий текст)", flush=True)
    else:
        section_id, blocks = result
        print("📝 " + " / ".join(b.text for b in blocks), flush=True)

    if writer:
        writer.commit(item.pending, blocks, target_section_id=section_id)


# ---------------------------------------------------------------------- reader


def _recv_exactly(conn: socket.socket, count: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < count:
        try:
            chunk = conn.recv(count - len(buf))
        except socket.timeout:
            if _stop.is_set():
                return None
            continue
        except OSError:
            return None
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def _read_handshake(conn: socket.socket, default_rate: int) -> tuple[int, bytes]:
    """Читає заголовок 'CNSP' + частота. Повертає (частота, залишок байтів)."""
    header = _recv_exactly(conn, HEADER_SIZE)
    if header is None:
        return default_rate, b""
    if header[:4] != MAGIC:
        print(
            f"⚠️ Клієнт без заголовка — вважаю потік {default_rate} Hz mono int16.",
            flush=True,
        )
        return default_rate, header  # це вже аудіо, не втрачаємо його
    rate = struct.unpack("<I", header[4:8])[0]
    if not 8000 <= rate <= 96000:
        print(f"⚠️ Дивна частота {rate} — беру {default_rate}.", flush=True)
        rate = default_rate
    return rate, b""


def _enqueue(q: "queue.Queue", item, describe=lambda x: "найстаріший фрагмент") -> None:
    """Не даємо черзі рости нескінченно, але й не приховуємо втрати."""
    try:
        q.put_nowait(item)
        return
    except queue.Full:
        pass
    try:
        dropped = q.get_nowait()
        q.task_done()
        print(
            f"⚠️ ЧЕРГА ПЕРЕПОВНЕНА: відкинуто {describe(dropped)}. "
            f"API не встигає за мовленням.",
            flush=True,
        )
    except queue.Empty:
        pass
    try:
        q.put_nowait(item)
    except queue.Full:
        print("⚠️ Елемент втрачено — черга досі повна.", flush=True)


def _describe_segment(segment) -> str:
    return f"найстаріший фрагмент ({segment.duration:.1f} с)"


def handle_client(conn: socket.socket, addr, work_q: "queue.Queue", cfg: Config) -> None:
    conn.settimeout(1.0)
    rate, leftover = _read_handshake(conn, cfg.sample_rate)
    print(f"🤝 Клієнт {addr}, потік {rate} Hz. Пишемо конспект!", flush=True)

    segmenter = Segmenter(sample_rate=rate)
    total_bytes = len(leftover)

    if leftover:
        for seg in segmenter.feed(leftover):
            _enqueue(work_q, seg, describe=_describe_segment)

    while not _stop.is_set():
        try:
            data = conn.recv(RECV_SIZE)
        except socket.timeout:
            continue
        except OSError:
            break
        if not data:
            break

        total_bytes += len(data)
        for seg in segmenter.feed(data):
            _enqueue(work_q, seg, describe=_describe_segment)

    # Хвіст потоку теж має потрапити в конспект.
    for seg in segmenter.flush():
        _enqueue(work_q, seg, describe=_describe_segment)

    minutes = total_bytes / 2 / rate / 60
    print(
        f"🔌 Клієнт від'єднався. Прийнято {minutes:.1f} хв аудіо; "
        f"коротких сегментів відкинуто: {segmenter.discarded_short}, "
        f"різок по ліміту: {segmenter.forced_cuts}.",
        flush=True,
    )


# ------------------------------------------------------------------------ main


def main() -> int:
    cfg = Config()

    missing = cfg.missing_keys()
    if missing:
        print(
            "❌ Немає ключів: " + ", ".join(missing) + "\n"
            "   Додай їх у .env або в оточення (див. README.md).",
            flush=True,
        )
        return 1

    # Імпорти після перевірки ключів — щоб помилка була зрозумілою, а не трейсбеком.
    from notes_ai import NoteBuilder

    notes = NoteBuilder(
        groq_api_key=cfg.groq_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
        model=cfg.model,
        effort=cfg.effort,
        whisper_model=cfg.whisper_model,
        language=cfg.language,
    )

    from local_notes import LocalNotesStore

    writer = LocalNotesStore()
    print(f"✅ Конспект: {writer.url} (сесія {writer.session_id})", flush=True)

    audio_q: queue.Queue = queue.Queue(maxsize=cfg.queue_max)
    text_q: queue.Queue = queue.Queue(maxsize=cfg.queue_max)
    transcriber = threading.Thread(
        target=transcribe_loop, args=(audio_q, text_q, notes, writer), name="transcriber"
    )
    composer = threading.Thread(
        target=polish_loop, args=(text_q, notes, writer), name="composer"
    )
    transcriber.start()
    composer.start()

    def _on_signal(_sig, _frame):
        if not _stop.is_set():
            print("\n🛑 Завершую: дочекаюсь поточних фрагментів…", flush=True)
            _stop.set()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((cfg.host, cfg.port))
    server.listen(1)
    server.settimeout(1.0)
    print(f"📡 Чекаю аудіопотік на {cfg.host}:{cfg.port}…", flush=True)

    try:
        # Приймаємо клієнтів по черзі: обрив зв'язку не вбиває сервер.
        while not _stop.is_set():
            try:
                conn, addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                handle_client(conn, addr, audio_q, cfg)
            finally:
                conn.close()
            if not _stop.is_set():
                print(f"📡 Знову чекаю клієнта на {cfg.host}:{cfg.port}…", flush=True)
    finally:
        server.close()
        audio_q.put(None)
        transcriber.join(timeout=120)
        composer.join(timeout=120)
        print("👋 Готово.", flush=True)
        if writer:
            print(f"📄 Конспект: {writer.url}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
