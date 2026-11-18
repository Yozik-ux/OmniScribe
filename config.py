"""Налаштування конспектора: читаються з оточення або з файлу .env.

Ключі більше не живуть у коді. Порядок пріоритету:
   змінна оточення  >  .env  >  значення за замовчуванням
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def _load_env_file(path: Path) -> None:
    """Мінімальний парсер .env, щоб не тягнути python-dotenv."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        # setdefault — справжнє оточення завжди сильніше за .env
        os.environ.setdefault(key.strip(), value)


_load_env_file(ENV_PATH)


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except ValueError:
        return default


class Config:
    def __init__(self) -> None:
        self.groq_api_key = _get("GROQ_API_KEY")
        self.anthropic_api_key = _get("ANTHROPIC_API_KEY")

        self.theme = _get("OMNISCRIBE_THEME", "dark")

        # Дефолт — найдешевша модель ($1/$5 за 1M токенів). Для вищої якості
        # редактури постав у .env CONSPEKT_MODEL=claude-sonnet-5 ($3/$15)
        # або claude-opus-5 ($5/$25).
        self.model = _get("CONSPEKT_MODEL", "claude-haiku-4-5")
        self.effort = _get("CONSPEKT_EFFORT", "low")
        self.whisper_model = _get("CONSPEKT_WHISPER_MODEL", "whisper-large-v3")
        self.language = _get("CONSPEKT_LANGUAGE", "uk")
        # detailed | concise | exam — див. notes_ai.PRESET_NOTES
        self.preset = _get("CONSPEKT_PRESET", "detailed")

        self.host = _get("CONSPEKT_HOST", "0.0.0.0")
        self.port = _get_int("CONSPEKT_PORT", 8085)
        self.sample_rate = _get_int("CONSPEKT_SAMPLE_RATE", 16000)

        # Скільки готових сегментів тримати в черзі перед воркером.
        self.queue_max = _get_int("CONSPEKT_QUEUE_MAX", 16)

    def missing_keys(self) -> list[str]:
        missing = []
        if not self.groq_api_key:
            missing.append("GROQ_API_KEY")
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        return missing
