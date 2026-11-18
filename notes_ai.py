"""Розпізнавання мовлення (Groq Whisper) + оформлення конспекту (Claude).

Головна відмінність від першої версії: Claude бачить контекст. Раніше кожні 15
секунд оброблялися незалежно, тому модель повторно вводила ті самі терміни й не
могла побудувати наскрізну структуру. Тепер їй передається хвіст уже написаного
конспекту та поточний план лекції — і вона додає заголовок лише тоді, коли тема
справді змінилася.
"""

import io
import wave

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

ФОРМАТ (використовуй ЛИШЕ ці конструкції — Google Docs нічого іншого не вміє):
# Тема            — головний розділ лекції (найвищий рівень)
## Підтема        — підрозділ усередині теми
### Деталь        — вужчий підрозділ (рідко, лише якщо рівнів справді три)
- пункт           — теза верхнього рівня списку
  - пункт         — уточнення/приклад/властивість до пункту вище (2 пробіли
                     відступу = рівень вкладеності; можна й третій рівень)
1. пункт          — нумерований пункт (послідовність кроків/етапів), теж
                     можна вкладати відступом так само, як "-"
звичайний абзац   — лише для зв'язного пояснення, яке не розкладається на пункти
**жирний**        — ключовий термін чи поняття (без кольору, лише вага)
==важливе==       — жовтий маркер: критичний для іспиту факт — дата, формула,
                     число, закон, назва
++означення++     — зелений маркер: саме формулювання означення ("це коли…",
                     "називається…"), тобто те, що відповідають на питання
!!попередження!!  — рожевий маркер: застереження лектора — виняток,
                     "не плутати з", "часта помилка", дедлайн

Маркери — як текстовиділювач у паперовому конспекті: ними має бути позначено
відсотків десять тексту, не більше. Якщо виділено все — не виділено нічого.
Жирний і маркер на тому самому фрагменті не поєднуй.

ТАБЛИЦЯ (лише якщо лектор явно порівнює кілька речей за кількома ознаками —
наприклад "є два підходи, перший швидший, другий простіший"):
| Колонка1 | Колонка2 |
| --- | --- |
| значення | значення |

ПРОСТА СХЕМА (лише якщо лектор описує послідовність етапів, причинно-
наслідковий зв'язок чи процес — "спочатку X, потім Y, в результаті Z"):
@@diagram
Вузол 1 -> Вузол 2
Вузол 2 -> Вузол 3
@@
Імена вузлів короткі (2-4 слова). Розгалуження — просто кілька рядків з
однаковим вузлом зліва ("Вузол 2 -> Вузол 3а" і "Вузол 2 -> Вузол 3б").

ЯК КОНСПЕКТУВАТИ (а не стенографувати):
- Лектор говорить реченнями — ти пишеш тезами: підмет + присудок + ключові
  слова, без "ну", "тобто", "коротше кажучи" та інших розмовних зв'язок.
- Будуй ІЄРАРХІЮ замість суцільного тексту: якщо лектор називає кілька
  прикладів, властивостей чи етапів одного явища — це вкладені пункти під
  тим явищем (відступом), а не окремі абзаци чи плаский список. Рукописні
  конспекти для цього малюють дерево зі стрілками — тут та сама ієрархія
  виражається вкладеністю списку.
- Дати, формули, назви законів/термінів, числові показники — майже завжди
  ==виділяй==, саме такі деталі найчастіше питають на іспиті.
- Якщо лектор наголошує "зверніть увагу", "це часта помилка", "не плутайте
  з X" — оформлюй як !!попередження!!.
- Не зловживай вкладеністю заради вкладеності: якщо природний рівень один —
  лишай плаский список.

ЛЕКЦІЯ ЧИ ЗАУВАЖЕННЯ:
Лектор іноді перериває виклад, щоб звернутись до конкретної людини: зробити
організаційне зауваження ("Степане, поклади телефон", "тихіше на задніх
партах", "перерва 10 хвилин", відповідь студенту не по темі лекції) — це НЕ
матеріал лекції. Такі фрази пропускай і не вноси в конспект, навіть якщо вони
трапились посеред фрагмента; лишай лише те, що лектор каже аудиторії як
навчальний матеріал. Якщо весь фрагмент — це тільки таке зауваження без
жодного навчального змісту, поверни SKIP.

ЗАБОРОНЕНО:
- Будь-яка інша розмітка: код, цитати (>), розділювачі (---), емодзі.
- Таблицю чи схему, коли звичайний список чи абзац передає те саме —
  це виключення для реальних порівнянь/процесів, а не прикраса.
- Виділяти маркером цілий пункт чи абзац: маркер бере саме факт
  ("==12 квітня 1961==", "++сукупність елементів із заданою операцією++"),
  а не речення навколо нього.
- Заголовки рівня 4-6 (####+) — у форматі є лише # / ## / ###.
- Мета-коментарі, вступи, відмови, звертання до користувача, фрази на кшталт
  "фрагмент надто короткий" або "ось оформлений текст". Видавай ВИКЛЮЧНО текст конспекту.
- Повторювати те, що вже є в розділах нижче. Продовжуй, а не перепиши.
- Вигадувати факти, яких не було у фрагменті. Фрагмент може обриватися на
  півслові — тоді просто завершуй речення природно, без домислів.

ПАМ'ЯТЬ ПРО КОНСПЕКТ:
Тобі даємо повний список уже написаних розділів (<розділи_конспекту>), кожен —
"id: Заголовок — короткий підсумок уже написаного в ньому". Лектор часто
повертається до теми, яку вже закривав раніше, — тоді новий фрагмент треба
дописати саме в той розділ, а не в кінець.

ПЕРШИЙ РЯДОК ВІДПОВІДІ — завжди рядок-директива:
- "ЦІЛЬ: <id>" — якщо фрагмент продовжує чи уточнює розділ <id> зі списку.
- "ЦІЛЬ: НОВИЙ" — якщо це новий матеріал, що не належить жодному існуючому розділу.
Після директиви — звичайний перехід на новий рядок і далі текст конспекту за
форматом вище.

Якщо фрагмент — це беззмістовний шум або службова фраза, поверни рівно: SKIP"""

# Пресети конспектування: та сама база-промпт + короткий дозапис, що зміщує
# акцент. Окремі промпти з нуля для кожного пресету дублювали б 90% тексту і
# розходились би між собою з часом — тут усі три гарантовано узгоджені.
PRESET_NOTES = {
    "detailed": "",
    "concise": (
        "\n\nРЕЖИМ \"СТИСЛІ ТЕЗИ\": лише найважливіше, без прикладів і "
        "уточнень. Максимум один рівень вкладеності списку. Жодних абзаців —"
        " тільки тези."
    ),
    "exam": (
        "\n\nРЕЖИМ \"ПІДГОТОВКА ДО ІСПИТУ\": максимально позначай ==важливе=="
        " (дати, формули, означення, назви) і !!попередження!! (винятки, "
        "часті помилки). Другорядні деталі й приклади пропускай — лишай те,"
        " що справді питають на іспиті."
    ),
}
PRESET_LABELS = {
    "detailed": "Детальний конспект",
    "concise": "Стислі тези",
    "exam": "Підготовка до іспиту",
}


def build_system_prompt(preset: str) -> str:
    return SYSTEM_PROMPT + PRESET_NOTES.get(preset, "")


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
        preset: str = "detailed",
    ) -> None:
        self.groq = OpenAI(api_key=groq_api_key, base_url="https://api.groq.com/openai/v1")
        self.claude = anthropic.Anthropic(api_key=anthropic_api_key)
        self.model = model
        self.effort = effort
        self._tuning_supported = model.startswith(_EFFORT_MODELS)
        self.whisper_model = whisper_model
        self.language = language
        self.system_prompt = build_system_prompt(preset)

        # Наскрізна пам'ять про конспект: кожен розділ — окремий запис, назавжди.
        self._sections: list[dict] = []  # {"id": int, "heading": str, "summary": str}
        self._next_id = 1
        self._last_raw = ""  # підказка для Whisper

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

    def polish(
        self, raw_text: str, cut_mid_sentence: bool = False
    ) -> tuple[int, list[Block]] | None:
        """Сирий текст -> (id розділу, блоки конспекту). None, якщо оформлювати нічого."""
        parts = []
        if self._sections:
            sections = "\n".join(
                f"{s['id']}: {s['heading']} — {s['summary']}" for s in self._sections
            )
            parts.append(f"<розділи_конспекту>\n{sections}\n</розділи_конспекту>")
        if cut_mid_sentence:
            parts.append(
                "<примітка>Фрагмент обрізано по ліміту довжини, він може "
                "обриватися на півслові.</примітка>"
            )
        parts.append(f"<новий_фрагмент>\n{raw_text}\n</новий_фрагмент>")

        kwargs = {
            "model": self.model,
            "max_tokens": 1500,
            "system": self.system_prompt,
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

        directive, _, rest = text.partition("\n")
        directive_id = self._parse_directive(directive)
        if directive_id is not None or directive.strip().upper().startswith("ЦІЛЬ"):
            text = rest.strip()

        blocks = mdlite.parse(text)
        if not blocks:
            return None

        section_id = self._remember(directive_id, blocks)
        return section_id, blocks

    @staticmethod
    def _parse_directive(line: str) -> int | None:
        """Розбирає "ЦІЛЬ: <id>" -> id. Для "ЦІЛЬ: НОВИЙ" чи сміття -> None."""
        head, _, value = line.strip().partition(":")
        if head.strip().upper() != "ЦІЛЬ":
            return None
        value = value.strip()
        return int(value) if value.isdigit() else None

    def _remember(self, directive_id: int | None, blocks: list[Block]) -> int:
        plain = " ".join(b.text for b in blocks if b.kind != "heading")
        tail = plain[-700:] if plain else ""

        existing = next((s for s in self._sections if s["id"] == directive_id), None)
        if existing is not None:
            if tail:
                existing["summary"] = (existing["summary"] + " " + tail)[-700:]
            return existing["id"]

        heading = next((b.text for b in blocks if b.kind == "heading"), "(без заголовка)")
        section_id = self._next_id
        self._next_id += 1
        self._sections.append({"id": section_id, "heading": heading, "summary": tail})
        return section_id
