"""Розпізнавання мовлення (Groq Whisper) + оформлення конспекту (Claude).

Головна відмінність від першої версії: Claude бачить контекст. Раніше кожні 15
секунд оброблялися незалежно, тому модель повторно вводила ті самі терміни й не
могла побудувати наскрізну структуру. Тепер їй передається хвіст уже написаного
конспекту та поточний план лекції — і вона додає заголовок лише тоді, коли тема
справді змінилася.
"""

import io
import wave
from collections import deque

import anthropic
from openai import OpenAI

import mdlite
from mdlite import Block

SYSTEM_PROMPT = """Ти — редактор академічних конспектів. Ти отримуєш фрагмент сирої транскрипції лекції і перетворюєш його на акуратну частину конспекту.

ЩО РОБИТИ:
1. Виправляй обмовки, фонетичні помилки Whisper та русизми.
2. Прибирай слова-паразити, повтори й розмовне сміття; лишай суть.
3. Виділяй **ключові терміни та поняття** жирним.
4. Структуруй: означення й перелічення — списком, розгорнуті думки — абзацом.

ФОРМАТ (використовуй ЛИШЕ ці конструкції, нічого іншого):
## Заголовок     — новий підрозділ; додавай ТІЛЬКИ якщо тема справді змінилася
- пункт          — елемент списку
1. пункт         — нумерований елемент
звичайний абзац
**жирний**       — терміни всередині будь-якого рядка

ЗАБОРОНЕНО:
- Будь-яка інша розмітка: таблиці, код, цитати, ###, ---, емодзі.
- Мета-коментарі, вступи, відмови, звертання до користувача, фрази на кшталт
  "фрагмент надто короткий" або "ось оформлений текст". Видавай ВИКЛЮЧНО текст конспекту.
- Повторювати те, що вже є в блоці <уже_в_конспекті>. Продовжуй, а не перепиши.
- Вигадувати факти, яких не було у фрагменті. Фрагмент може обриватися на
  півслові — тоді просто завершуй речення природно, без домислів.

Якщо фрагмент — це беззмістовний шум або службова фраза, поверни рівно: SKIP"""

# Типові галюцинації Whisper на тиші/шумі (він добудовує титри з YouTube).
HALLUCINATIONS = {
    "дякую за перегляд",
    "дякую",
    "дякую за увагу",
    "підписуйтесь на канал",
    "підписуйтеся на канал",
    "субтитри",
    "субтитри створено спільнотою",
    "редактор субтитрів",
    "продовження випливає",
    "продовження далі",
    "музика",
    "оплески",
    "ось і все",
    "всім привіт",
    "до зустрічі",
}

_PUNCT = ".,!?;:—–-\"'«»()[]…"

# Моделі, які приймають output_config.effort і adaptive thinking. На старших
# (haiku-4-5, sonnet-4-5) ці параметри повертають 400, тому їх просто не шлемо:
# thinking там і так вимкнене, якщо поле відсутнє.
_EFFORT_MODELS = (
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-opus-5",
    "claude-sonnet-4-6",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-mythos-5",
)


def _normalize(text: str) -> str:
    lowered = text.lower()
    for ch in _PUNCT:
        lowered = lowered.replace(ch, " ")
    return " ".join(lowered.split())


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> io.BytesIO:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    buf.seek(0)
    buf.name = "audio.wav"
    return buf


class NoteBuilder:
    def __init__(
        self,
        groq_api_key: str,
        anthropic_api_key: str,
        model: str = "claude-haiku-4-5",
        effort: str = "low",
        whisper_model: str = "whisper-large-v3",
        language: str = "uk",
        context_blocks: int = 3,
    ) -> None:
        self.groq = OpenAI(api_key=groq_api_key, base_url="https://api.groq.com/openai/v1")
        self.claude = anthropic.Anthropic(api_key=anthropic_api_key)
        self.model = model
        self.effort = effort
        self._tuning_supported = model.startswith(_EFFORT_MODELS)
        self.whisper_model = whisper_model
        self.language = language

        # Наскрізний контекст лекції.
        self._recent: deque[str] = deque(maxlen=context_blocks)  # хвіст конспекту
        self._outline: list[str] = []                            # заголовки по порядку
        self._last_raw = ""                                      # підказка для Whisper

    # ------------------------------------------------------------- Whisper

    def transcribe(self, pcm: bytes, sample_rate: int) -> str | None:
        """PCM -> текст. None, якщо це тиша, шум або галюцинація."""
        wav = _pcm_to_wav(pcm, sample_rate)

        kwargs = {
            "model": self.whisper_model,
            "file": wav,
            "language": self.language,
            "temperature": 0.0,
        }
        # Хвіст попереднього фрагмента як підказка: тримає термінологію
        # й імена власні однаковими між сегментами.
        if self._last_raw:
            kwargs["prompt"] = self._last_raw[-400:]

        transcription = self.groq.audio.transcriptions.create(**kwargs)
        raw = (transcription.text or "").strip()
        if not raw:
            return None

        normalized = _normalize(raw)
        if len(normalized) < 8 or normalized in HALLUCINATIONS:
            return None
        # Whisper на тиші любить повторювати одну фразу N разів.
        words = normalized.split()
        if len(words) >= 6 and len(set(words)) <= 2:
            return None

        self._last_raw = raw
        return raw

    # -------------------------------------------------------------- Claude

    def polish(self, raw_text: str, cut_mid_sentence: bool = False) -> list[Block] | None:
        """Сирий текст -> блоки конспекту. None, якщо оформлювати нічого."""
        parts = []
        if self._recent:
            parts.append("<уже_в_конспекті>\n" + "\n\n".join(self._recent) + "\n</уже_в_конспекті>")
        if self._outline:
            plan = "\n".join(f"- {h}" for h in self._outline[-8:])
            parts.append(f"<план_лекції>\n{plan}\n</план_лекції>")
        if cut_mid_sentence:
            parts.append(
                "<примітка>Фрагмент обрізано по ліміту довжини, він може "
                "обриватися на півслові.</примітка>"
            )
        parts.append(f"<новий_фрагмент>\n{raw_text}\n</новий_фрагмент>")

        kwargs = {
            "model": self.model,
            "max_tokens": 1500,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": "\n\n".join(parts)}],
        }
        if self._tuning_supported:
            kwargs["output_config"] = {"effort": self.effort}
            # Для realtime-конвеєра думати немає сенсу: завдання —
            # редактура короткого фрагмента, а латентність видно студенту.
            # Виняток: Opus 5 не дозволяє вимкнене thinking на xhigh/max.
            if self.effort not in ("xhigh", "max"):
                kwargs["thinking"] = {"type": "disabled"}

        try:
            message = self.claude.messages.create(**kwargs)
        except anthropic.APIError as exc:
            print(f"⚠️ Claude недоступний ({exc}) — лишаю сирий текст.", flush=True)
            return None

        if message.stop_reason == "refusal":
            print("⚠️ Claude відмовився оформлювати фрагмент — лишаю сирий текст.", flush=True)
            return None

        text = ""
        for block in message.content:
            if block.type == "text":
                text = block.text
                break

        text = text.strip()
        if not text or text.strip().upper() == "SKIP":
            return None

        blocks = mdlite.parse(text)
        if not blocks:
            return None

        self._remember(blocks)
        return blocks

    def _remember(self, blocks: list[Block]) -> None:
        plain = " ".join(b.text for b in blocks if b.kind != "heading")
        if plain:
            self._recent.append(plain[-700:])
        for block in blocks:
            if block.kind == "heading" and block.text not in self._outline:
                self._outline.append(block.text)
