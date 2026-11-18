"""Локальне зберігання конспекту замість Google Docs.

Чому простіше, ніж docs_writer.py: там NamedRange і перерахунок індексів
символів існували лише через те, що студент міг одночасно редагувати
документ у Google Docs, а індекси "їхали". Тут немає зовнішнього редактора —
єдиний писар у SQLite — тому секція "дописати в розділ X" це просто "додати
рядки в кінець із тим самим section_id", без збереження позицій символів.

Схема: сесія (одна лекція) -> блоки конспекту (heading/bullet/number/para),
кожен блок зберігає чистий текст + діапазони (bold/highlight/warning) з
mdlite.Block, щоб експорт у .md/.docx міг повністю відтворити форматування.
"""

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mdlite import Block

PENDING_PREFIX = "▸ "

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    notes_html TEXT,
    duration_seconds REAL NOT NULL DEFAULT 0,
    word_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    section_id INTEGER,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    bold TEXT NOT NULL DEFAULT '[]',
    highlight TEXT NOT NULL DEFAULT '[]',
    warning TEXT NOT NULL DEFAULT '[]',
    definition TEXT NOT NULL DEFAULT '[]',
    rows TEXT NOT NULL DEFAULT '[]',
    edges TEXT NOT NULL DEFAULT '[]',
    pending INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_blocks_session ON blocks(session_id, position);
"""

# Для баз, створених до появи таблиць/діаграм — CREATE TABLE IF NOT EXISTS не
# додає нові стовпці в уже існуючу таблицю.
_MIGRATIONS = (
    "ALTER TABLE blocks ADD COLUMN rows TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE blocks ADD COLUMN edges TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE sessions ADD COLUMN notes_html TEXT",
    "ALTER TABLE sessions ADD COLUMN duration_seconds REAL NOT NULL DEFAULT 0",
    "ALTER TABLE sessions ADD COLUMN word_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE blocks ADD COLUMN definition TEXT NOT NULL DEFAULT '[]'",
)


@dataclass
class SessionRow:
    id: int
    title: str
    created_at: str
    duration_seconds: float
    word_count: int

    @property
    def meta_label(self) -> str:
        """Рядок під назвою в списку: "18 лис · 42 хв · 1 240 слів"."""
        parts = [_short_date(self.created_at)]
        if self.duration_seconds >= 30:
            minutes = int(round(self.duration_seconds / 60))
            parts.append(f"{minutes} хв" if minutes else "<1 хв")
        if self.word_count:
            parts.append(f"{self.word_count:,} слів".replace(",", " "))
        return "  ·  ".join(parts)


_MONTHS = (
    "січ", "лют", "бер", "кві", "тра", "чер",
    "лип", "сер", "вер", "жов", "лис", "гру",
)


def _short_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{dt.day} {_MONTHS[dt.month - 1]}, {dt:%H:%M}"


@dataclass
class StoredBlock:
    id: int
    kind: str
    text: str
    level: int
    bold: list[tuple[int, int]]
    highlight: list[tuple[int, int]]
    warning: list[tuple[int, int]]
    definition: list[tuple[int, int]]
    rows: list[list[str]]
    edges: list[tuple[str, str]]
    pending: bool

    def to_block(self) -> Block:
        return Block(
            kind="para" if self.kind == "pending" else self.kind,
            text=self.text,
            level=self.level,
            bold=self.bold,
            highlight=self.highlight,
            warning=self.warning,
            definition=self.definition,
            rows=self.rows,
            edges=self.edges,
        )


def default_db_path() -> Path:
    base = Path.home() / ".omniscribe"
    base.mkdir(parents=True, exist_ok=True)
    return base / "notes.db"


class LocalNotesStore:
    """Локальний аналог DocsWriter: той самий insert_pending/commit API,
    щоб конвеєр transcribe -> polish -> writer у app.py лишався незмінним.
    """

    def __init__(self, db_path: Path | str | None = None, session_title: str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_db_path()
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        for migration in _MIGRATIONS:
            try:
                self._conn.execute(migration)
            except sqlite3.OperationalError:
                pass  # стовпець уже є
        self._conn.commit()

        title = session_title or f"Лекція {datetime.now():%d.%m.%Y %H:%M}"
        cur = self._conn.execute(
            "INSERT INTO sessions (title, created_at) VALUES (?, ?)",
            (title, datetime.now().isoformat(timespec="seconds")),
        )
        self._conn.commit()
        self.session_id = cur.lastrowid
        self.title = title
        self.created = True

    @property
    def url(self) -> str:
        return str(self.db_path)

    # ------------------------------------------------------------ публічне API

    def write_session_header(self) -> None:
        self.commit(None, [Block("heading", self.title)])

    def insert_pending(self, raw_text: str) -> int | None:
        """Одразу зберегти сирий транскрипт (показується GUI тьмяним, поки
        Claude не оформив фрагмент). Повертає id рядка для подальшого commit().
        """
        with self._lock:
            pos = self._next_position()
            cur = self._conn.execute(
                "INSERT INTO blocks (session_id, kind, text, pending, position) "
                "VALUES (?, 'pending', ?, 1, ?)",
                (self.session_id, PENDING_PREFIX + raw_text.strip(), pos),
            )
            self._conn.commit()
            return cur.lastrowid

    def commit(
        self,
        pending_id: int | None,
        blocks: list[Block],
        target_section_id: int | None = None,
    ) -> bool:
        if not blocks:
            if pending_id is not None:
                self._delete_pending(pending_id)
            return False

        with self._lock:
            if pending_id is not None:
                self._conn.execute(
                    "DELETE FROM blocks WHERE id = ? AND session_id = ?",
                    (pending_id, self.session_id),
                )

            pos = self._next_position()
            for block in blocks:
                self._conn.execute(
                    "INSERT INTO blocks "
                    "(session_id, section_id, kind, text, level, bold, highlight, warning, "
                    " definition, rows, edges, pending, position) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
                    (
                        self.session_id,
                        target_section_id,
                        block.kind,
                        block.text,
                        block.level,
                        json.dumps(block.bold),
                        json.dumps(block.highlight),
                        json.dumps(block.warning),
                        json.dumps(block.definition),
                        json.dumps(block.rows),
                        json.dumps(block.edges),
                        pos,
                    ),
                )
                pos += 1
            self._conn.commit()
            return True

    def _delete_pending(self, pending_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM blocks WHERE id = ? AND session_id = ?",
                (pending_id, self.session_id),
            )
            self._conn.commit()

    def _next_position(self) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM blocks WHERE session_id = ?",
            (self.session_id,),
        ).fetchone()
        return row[0]

    # --------------------------------------------------------------- читання

    def list_sessions(self) -> list[SessionRow]:
        """Найновіші перші, з метаданими для списку в сайдбарі."""
        rows = self._conn.execute(
            "SELECT id, title, created_at, duration_seconds, word_count "
            "FROM sessions ORDER BY id DESC"
        ).fetchall()
        return [SessionRow(r[0], r[1], r[2], r[3], r[4]) for r in rows]

    def load_blocks(self, session_id: int | None = None) -> list[StoredBlock]:
        sid = session_id if session_id is not None else self.session_id
        rows = self._conn.execute(
            "SELECT id, kind, text, level, bold, highlight, warning, definition, "
            "rows, edges, pending "
            "FROM blocks WHERE session_id = ? ORDER BY position",
            (sid,),
        ).fetchall()
        result = []
        for r in rows:
            result.append(
                StoredBlock(
                    id=r[0],
                    kind=r[1],
                    text=r[2],
                    level=r[3],
                    bold=[tuple(p) for p in json.loads(r[4])],
                    highlight=[tuple(p) for p in json.loads(r[5])],
                    warning=[tuple(p) for p in json.loads(r[6])],
                    definition=[tuple(p) for p in json.loads(r[7])],
                    rows=json.loads(r[8]),
                    edges=[tuple(p) for p in json.loads(r[9])],
                    pending=bool(r[10]),
                )
            )
        return result

    def session_title(self, session_id: int) -> str:
        row = self._conn.execute(
            "SELECT title FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row[0] if row else ""

    def rename_session(self, session_id: int, title: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET title = ? WHERE id = ?", (title, session_id)
            )
            self._conn.commit()

    def save_notes_override(self, session_id: int, html: str) -> None:
        """Користувач редагував конспект напряму в редакторі — зберігаємо
        сирий HTML і надалі показуємо/експортуємо саме його, а не
        реконструкцію з blocks (яку перезаписали ручні правки)."""
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET notes_html = ? WHERE id = ?", (html, session_id)
            )
            self._conn.commit()

    def load_notes_override(self, session_id: int) -> str | None:
        row = self._conn.execute(
            "SELECT notes_html FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row[0] if row and row[0] else None

    def add_session_stats(self, session_id: int, seconds: float = 0.0, words: int = 0) -> None:
        """Накопичує тривалість і кількість слів — це дає сайдбару й шапці
        реальні цифри замість порожніх плейсхолдерів."""
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET duration_seconds = duration_seconds + ?, "
                "word_count = word_count + ? WHERE id = ?",
                (seconds, words, session_id),
            )
            self._conn.commit()

    def session_stats(self, session_id: int) -> tuple[float, int]:
        row = self._conn.execute(
            "SELECT duration_seconds, word_count FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return (row[0], row[1]) if row else (0.0, 0)

    def delete_session(self, session_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------- експорт

    def export_markdown(self, session_id: int | None = None) -> str:
        from export import blocks_to_markdown

        sid = session_id if session_id is not None else self.session_id
        override = self.load_notes_override(sid)
        if override:
            return _richtext_to_markdown(override)
        blocks = [b.to_block() for b in self.load_blocks(sid) if not b.pending]
        return blocks_to_markdown(blocks)

    def export_docx(self, path: Path | str, session_id: int | None = None) -> None:
        from export import blocks_to_docx

        sid = session_id if session_id is not None else self.session_id
        override = self.load_notes_override(sid)
        if override:
            from mdlite import parse

            blocks_to_docx(parse(_richtext_to_markdown(override)), self.session_title(sid), path)
            return
        blocks = [b.to_block() for b in self.load_blocks(sid) if not b.pending]
        blocks_to_docx(blocks, self.session_title(sid), path)


def _richtext_to_markdown(html: str) -> str:
    """Ручні правки живуть як HTML у QTextEdit — тут вони йдуть в markdown.

    QTextDocument.toMarkdown() розуміє заголовки/жирний/таблиці нашого
    HTML напряму, тож не треба писати окремий конвертер; якщо з якоїсь
    причини Qt недоступний — груба заміна тегів порожнім рядком, аби
    експорт не впав зовсім.
    """
    try:
        from PySide6.QtGui import QTextDocument

        doc = QTextDocument()
        doc.setHtml(html)
        return doc.toMarkdown()
    except Exception:  # noqa: BLE001 — експорт має віддати хоч щось
        import re

        return re.sub(r"<[^>]+>", "", html)
