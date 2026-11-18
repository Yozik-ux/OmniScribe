"""Локальні акаунти OmniScribe.

Поки що акаунт живе тільки на цьому комп'ютері: сервера немає, нічого
нікуди не йде. Але логіка справжня, щоб її не переписувати, коли з'явиться
синхронізація:

    реєстрація -> пароль солиться і проганяється через PBKDF2-HMAC-SHA256
                  (200k ітерацій), у базі лежить лише хеш;
    вхід       -> перевірка через hmac.compare_digest, без витоку часу;
    сесія      -> у таблиці зберігається email активного акаунта, тож
                  застосунок пам'ятає вхід між запусками.

Акаунт не обов'язковий: без нього все працює локально. Він потрібен лише
там, де без особи не обійтися — оплата плану й майбутня синхронізація.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_ITERATIONS = 200_000
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
MIN_PASSWORD = 8

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    email TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_session (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    email TEXT
);
"""


@dataclass(frozen=True)
class Account:
    email: str
    name: str
    created_at: str

    @property
    def initials(self) -> str:
        parts = [p for p in self.name.replace("-", " ").split() if p]
        if not parts:
            return self.email[:1].upper()
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][:1] + parts[1][:1]).upper()


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
    ).hex()


def validate(email: str, password: str, name: str | None = None) -> str:
    """Повертає текст помилки для показу користувачу, або "" якщо все гаразд.

    Формулювання за правилом "що сталося + як виправити" — помилка має
    вести далі, а не просто констатувати невдачу.
    """
    if name is not None and not name.strip():
        return "Вкажи ім'я — воно буде на конспектах і в експорті."
    if not _EMAIL_RE.match(email.strip()):
        return "Схоже, в адресі помилка. Приклад: ivan@kpi.ua"
    if len(password) < MIN_PASSWORD:
        return f"Пароль закороткий — потрібно хоча б {MIN_PASSWORD} символів."
    return ""


class AccountStore:
    def __init__(self, db_path: Path | str) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------ реєстрація

    def sign_up(self, email: str, name: str, password: str) -> tuple[Account | None, str]:
        email = email.strip().lower()
        name = name.strip()

        error = validate(email, password, name)
        if error:
            return None, error

        if self._row(email):
            return None, "Акаунт із такою адресою вже є. Спробуй увійти."

        salt = secrets.token_hex(16)
        created = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute(
                "INSERT INTO accounts (email, name, salt, password_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (email, name, salt, _hash(password, salt), created),
            )
            self._conn.commit()

        account = Account(email=email, name=name, created_at=created)
        self._remember(email)
        return account, ""

    def sign_in(self, email: str, password: str) -> tuple[Account | None, str]:
        email = email.strip().lower()
        row = self._row(email)
        if row is None:
            return None, "Такого акаунта немає. Перевір адресу або зареєструйся."

        _, name, salt, stored, created = row
        if not hmac.compare_digest(_hash(password, salt), stored):
            return None, "Пароль не підходить. Спробуй ще раз."

        account = Account(email=email, name=name, created_at=created)
        self._remember(email)
        return account, ""

    def sign_out(self) -> None:
        self._remember(None)

    def current(self) -> Account | None:
        row = self._conn.execute("SELECT email FROM account_session WHERE id = 1").fetchone()
        if not row or not row[0]:
            return None
        data = self._row(row[0])
        if data is None:
            return None
        return Account(email=data[0], name=data[1], created_at=data[4])

    # ------------------------------------------------------------- внутрішнє

    def _row(self, email: str):
        return self._conn.execute(
            "SELECT email, name, salt, password_hash, created_at FROM accounts WHERE email = ?",
            (email,),
        ).fetchone()

    def _remember(self, email: str | None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO account_session (id, email) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET email = excluded.email",
                (email,),
            )
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()
