"""Плани користування OmniScribe, квота й облік використання.

ДЕМО: справжнього білінгу тут немає — це робоча заготовка під майбутню
підписку. Платіж нікуди не надсилається, реквізити картки не зберігаються
і не залишають вікно. Усе, що працює по-справжньому — облік хвилин запису
й ліміти плану (вони реально блокують запис, коли місячна квота вичерпана).

Облік живе в тій самій локальній базі, що й конспекти (~/.omniscribe/notes.db),
окремим з'єднанням — SQLite спокійно тримає кілька з'єднань до одного файлу.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage (
    month TEXT PRIMARY KEY,   -- YYYY-MM
    seconds REAL NOT NULL DEFAULT 0,
    sessions INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    price_uah: int
    minutes_month: int | None  # None — без ліміту
    tagline: str
    model: str
    features: tuple[str, ...]
    locked: tuple[str, ...] = ()  # чого в плані немає (сіріє у порівнянні)

    @property
    def price_label(self) -> str:
        return "0 ₴" if self.price_uah == 0 else f"{self.price_uah} ₴"

    @property
    def limit_label(self) -> str:
        if self.minutes_month is None:
            return "без ліміту"
        hours = self.minutes_month // 60
        return f"{hours} год/міс"


PLANS: dict[str, Plan] = {
    "free": Plan(
        id="free",
        name="Free",
        price_uah=0,
        minutes_month=180,
        tagline="Спробувати на кількох парах",
        model="claude-haiku-4-5",
        features=(
            "3 години запису на місяць",
            "Розпізнавання Whisper large-v3",
            "Конспект моделлю Haiku 4.5",
            "Локальне зберігання, нічого в хмарі",
            "Експорт у Markdown",
        ),
        locked=("Таблиці та схеми", "Пресети конспектування", "Експорт у Word"),
    ),
    "pro": Plan(
        id="pro",
        name="Pro",
        price_uah=199,
        minutes_month=1800,
        tagline="Для цілого семестру",
        model="claude-sonnet-5",
        features=(
            "30 годин запису на місяць",
            "Конспект моделлю Sonnet 5",
            "Таблиці та схеми в конспекті",
            "Усі пресети конспектування",
            "Експорт у Markdown і Word",
            "Пріоритетна черга розпізнавання",
        ),
        locked=("Спільні сесії", "API доступ"),
    ),
    "team": Plan(
        id="team",
        name="Team",
        price_uah=499,
        minutes_month=None,
        tagline="Для групи або кафедри",
        model="claude-opus-5",
        features=(
            "Без ліміту годин",
            "Конспект моделлю Opus 5",
            "Спільні сесії для групи",
            "Спільна база термінів лекторів",
            "API доступ і вебхуки",
            "Пріоритетна підтримка",
        ),
    ),
}

DEFAULT_PLAN = "free"


def plan(plan_id: str) -> Plan:
    return PLANS.get(plan_id, PLANS[DEFAULT_PLAN])


@dataclass
class Usage:
    used_seconds: float
    limit_minutes: int | None
    sessions: int

    @property
    def used_minutes(self) -> float:
        return self.used_seconds / 60

    @property
    def percent(self) -> int:
        if not self.limit_minutes:
            return 0
        return min(100, int(self.used_minutes / self.limit_minutes * 100))

    @property
    def exhausted(self) -> bool:
        return self.limit_minutes is not None and self.used_minutes >= self.limit_minutes

    @property
    def label(self) -> str:
        used = _fmt_minutes(self.used_minutes)
        if self.limit_minutes is None:
            return f"{used} цього місяця"
        return f"{used} з {_fmt_minutes(self.limit_minutes)}"


def _fmt_minutes(minutes: float) -> str:
    total = int(round(minutes))
    if total < 60:
        return f"{total} хв"
    return f"{total // 60} год {total % 60:02d} хв"


def current_month() -> str:
    return datetime.now().strftime("%Y-%m")


class BillingStore:
    def __init__(self, db_path: Path | str) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------ план

    def plan_id(self) -> str:
        row = self._conn.execute("SELECT value FROM meta WHERE key = 'plan'").fetchone()
        return row[0] if row and row[0] in PLANS else DEFAULT_PLAN

    def plan(self) -> Plan:
        return plan(self.plan_id())

    def set_plan(self, plan_id: str) -> None:
        if plan_id not in PLANS:
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES ('plan', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (plan_id,),
            )
            self._conn.commit()

    def has_feature(self, feature: str) -> bool:
        """Фічі, прив'язані до плану: 'rich' (таблиці/схеми), 'presets', 'docx'."""
        pid = self.plan_id()
        if pid == "free":
            return False
        if pid == "pro":
            return feature in {"rich", "presets", "docx"}
        return True

    # ------------------------------------------------------------- облік

    def add_seconds(self, seconds: float) -> None:
        if seconds <= 0:
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO usage (month, seconds) VALUES (?, ?) "
                "ON CONFLICT(month) DO UPDATE SET seconds = seconds + excluded.seconds",
                (current_month(), seconds),
            )
            self._conn.commit()

    def add_session(self) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO usage (month, sessions) VALUES (?, 1) "
                "ON CONFLICT(month) DO UPDATE SET sessions = sessions + 1",
                (current_month(),),
            )
            self._conn.commit()

    def usage(self) -> Usage:
        row = self._conn.execute(
            "SELECT seconds, sessions FROM usage WHERE month = ?", (current_month(),)
        ).fetchone()
        seconds, sessions = (row[0], row[1]) if row else (0.0, 0)
        return Usage(
            used_seconds=seconds,
            limit_minutes=self.plan().minutes_month,
            sessions=sessions,
        )

    def reset_usage(self) -> None:
        """Демо-зручність: скинути лічильник поточного місяця."""
        with self._lock:
            self._conn.execute("DELETE FROM usage WHERE month = ?", (current_month(),))
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()
