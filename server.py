"""AI-конспектор: приймає аудіопотік, пише конспект у Google Docs у реальному часі.

Архітектура (три незалежні потоки, щоб мережа ніколи не чекала на API):

    C++ клієнт --TCP--> [reader thread] --VAD--> queue --> [worker thread] --> Google Docs
                         тільки recv               сегменти    Whisper + Claude

Раніше обробка викликалась із recv-циклу: поки йшли Whisper і Claude (кілька
секунд), conn.recv() не викликався, TCP-буфер набивався, backpressure доходив до
C++ і вбивав аудіо-callback. Тепер reader лише читає, а вся мережа до API живе в
окремому воркері.
"""

import io
import queue
import signal
import socket
import struct
import sys
import threading

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


def worker_loop(work_q: "queue.Queue", notes, writer) -> None:
    """Один воркер = гарантований порядок фрагментів у документі."""
    while True:
        item = work_q.get()
        try:
            if item is None:
                return
            _process_segment(item, notes, writer)
        except Exception as exc:  # noqa: BLE001 — один поганий сегмент не валить сесію
            print(f"❌ Помилка обробки сегмента: {exc}", flush=True)
        finally:
            work_q.task_done()


def _process_segment(segment, notes, writer) -> None:
    print(f"\n⏳ Розпізнаю {segment.duration:.1f} с…", flush=True)
    raw = notes.transcribe(segment.pcm, segment.sample_rate)
    if not raw:
        print("   тиша або шум — пропускаю.", flush=True)
        return

    print(f"🎤 {raw}", flush=True)

    # Чернетку видно студенту одразу, ще до Claude.
    pending = writer.insert_pending(raw) if writer else None

    blocks = notes.polish(raw, cut_mid_sentence=segment.cut_mid_sentence)
    if blocks is None:
        # Claude не спрацював — краще лишити сирий текст, ніж нічого.
        blocks = [Block("para", raw)]
        print("📝 (сирий текст)", flush=True)
    else:
        print("📝 " + " / ".join(b.text for b in blocks), flush=True)

    if writer:
        writer.commit(pending, blocks)


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


def _enqueue(work_q: "queue.Queue", segment) -> None:
    """Не даємо черзі рости нескінченно, але й не приховуємо втрати."""
    try:
        work_q.put_nowait(segment)
        return
    except queue.Full:
        pass
    try:
        dropped = work_q.get_nowait()
        work_q.task_done()
        print(
            f"⚠️ ЧЕРГА ПЕРЕПОВНЕНА: відкинуто найстаріший фрагмент "
            f"({dropped.duration:.1f} с). API не встигає за мовленням.",
            flush=True,
        )
    except queue.Empty:
        pass
    try:
        work_q.put_nowait(segment)
    except queue.Full:
        print("⚠️ Фрагмент втрачено — черга досі повна.", flush=True)


def handle_client(conn: socket.socket, addr, work_q: "queue.Queue", cfg: Config) -> None:
    conn.settimeout(1.0)
    rate, leftover = _read_handshake(conn, cfg.sample_rate)
    print(f"🤝 Клієнт {addr}, потік {rate} Hz. Пишемо конспект!", flush=True)

    segmenter = Segmenter(sample_rate=rate)
    total_bytes = len(leftover)

    if leftover:
        for seg in segmenter.feed(leftover):
            _enqueue(work_q, seg)

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
            _enqueue(work_q, seg)

    # Хвіст потоку теж має потрапити в конспект.
    for seg in segmenter.flush():
        _enqueue(work_q, seg)

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

    writer = None
    try:
        from docs_writer import DocsWriter

        writer = DocsWriter(
            credentials_file=cfg.credentials_file,
            document_id=cfg.document_id,
            share_with=cfg.share_with,
        )
        print(f"✅ Google Docs: {writer.url}", flush=True)
        if not writer.created:
            writer.write_session_header()
    except Exception as exc:  # noqa: BLE001 — без Docs сервер усе одно корисний у консолі
        print(f"⚠️ Google Docs не підключено ({exc}). Пишу лише в консоль.", flush=True)

    work_q: queue.Queue = queue.Queue(maxsize=cfg.queue_max)
    worker = threading.Thread(target=worker_loop, args=(work_q, notes, writer), name="worker")
    worker.start()

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
                handle_client(conn, addr, work_q, cfg)
            finally:
                conn.close()
            if not _stop.is_set():
                print(f"📡 Знову чекаю клієнта на {cfg.host}:{cfg.port}…", flush=True)
    finally:
        server.close()
        work_q.put(None)
        worker.join(timeout=120)
        print("👋 Готово.", flush=True)
        if writer:
            print(f"📄 Конспект: {writer.url}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
