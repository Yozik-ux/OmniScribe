"""Локалізація інтерфейсу.

Ключ перекладу — сам український рядок (підхід gettext). Через це не
доводиться вигадувати й синхронізувати штучні ідентифікатори, а відсутній
переклад деградує до української, а не до "settings.button.label".

Мова зберігається в QSettings і застосовується наживо: MainWindow
перебудовує інтерфейс, бо рядки вшиті у віджети при створенні.
"""

from __future__ import annotations

LANGUAGES = {"uk": "Українська", "en": "English"}
DEFAULT = "uk"

_EN: dict[str, str] = {
    # --- шапка й керування записом ---
    "Мікрофон": "Microphone",
    "Оновити список пристроїв": "Refresh device list",
    "Мікрофон не знайдено": "No microphone found",
    "Записати": "Record",
    "Стоп": "Stop",
    "Пауза": "Pause",
    "Продовжити": "Resume",
    "Почати запис  ·  Ctrl+R": "Start recording  ·  Ctrl+R",
    "Зупинити запис  ·  Ctrl+R": "Stop recording  ·  Ctrl+R",
    "Пауза  ·  Ctrl+Space": "Pause  ·  Ctrl+Space",
    "Увійти або створити акаунт": "Sign in or create an account",
    # --- сайдбар ---
    "+  Нова сесія": "+  New session",
    "Нова сесія  ·  Ctrl+N": "New session  ·  Ctrl+N",
    "Пошук сесій…   Ctrl+L": "Search sessions…   Ctrl+L",
    "Сесії": "Sessions",
    "Експорт": "Export",
    "Markdown": "Markdown",
    "Word": "Word",
    "Експорт .md  ·  Ctrl+E": "Export .md  ·  Ctrl+E",
    "Експорт .docx  ·  Ctrl+Shift+E": "Export .docx  ·  Ctrl+Shift+E",
    "Подвійний клік — перейменувати лекцію": "Double-click to rename a lecture",
    "Змінити": "Change",
    "Плани  ·  Ctrl+P": "Plans  ·  Ctrl+P",
    # --- картки ---
    "Чує зараз": "Hearing now",
    "Конспект": "Notes",
    "Сховати панель  ·  Ctrl+Shift+L": "Hide panel  ·  Ctrl+Shift+L",
    "Натисни «Записати» — і тут з'явиться те, що чує модель.":
        "Press Record and whatever the model hears shows up here.",
    "Конспект з'явиться тут, коли почнеться запис — або просто почни писати сам.":
        "Notes appear here once recording starts — or just start typing.",
    "ЗАПИС": "RECORDING",
    "ЗБЕРЕЖЕНО": "SAVED",
    "ЧЕРНЕТКА": "DRAFT",
    "хв мовлення": "min of speech",
    "слів": "words",
    # --- редактор ---
    "Скасувати": "Undo",
    "Повторити": "Redo",
    "Текст": "Body text",
    "Заголовок 1": "Heading 1",
    "Заголовок 2": "Heading 2",
    "Заголовок 3": "Heading 3",
    "Стиль абзацу  ·  Ctrl+Alt+1…3": "Paragraph style  ·  Ctrl+Alt+1…3",
    "Жирний": "Bold",
    "Курсив": "Italic",
    "Підкреслений": "Underline",
    "Закреслений": "Strikethrough",
    "Колір тексту і маркер": "Text colour and highlighter",
    "Маркер": "Highlighter",
    "Колір тексту": "Text colour",
    "Без маркера": "No highlight",
    "Звичайний": "Default",
    "Приглушений": "Muted",
    "Контрастний": "Strong",
    "Важливе": "Key fact",
    "Означення": "Definition",
    "Приклад": "Example",
    "Застереження": "Caution",
    "Запитають": "Will be asked",
    "Маркований список": "Bulleted list",
    "Нумерований список": "Numbered list",
    "Зменшити відступ": "Decrease indent",
    "Збільшити відступ": "Increase indent",
    "Вставити таблицю 3×2": "Insert 3×2 table",
    "Горизонтальна лінія": "Horizontal rule",
    "Прибрати форматування": "Clear formatting",
    "Знайти в конспекті": "Find in notes",
    "Далі": "Next",
    "Закрити": "Close",
    "Нічого не знайшлося": "No matches",
    # --- команди ---
    "Почати запис": "Start recording",
    "Зупинити запис": "Stop recording",
    "Мікрофон → конспект у реальному часі": "Microphone → live notes",
    "Пауза / продовжити": "Pause / resume",
    "Призупинити потік, не закриваючи сесію": "Pause the stream without closing the session",
    "Нова сесія": "New session",
    "Почати нову лекцію з власною назвою": "Start a new lecture with your own title",
    "Перейменувати лекцію": "Rename lecture",
    "Змінити назву поточної сесії": "Change the current session title",
    "Експорт у Markdown": "Export to Markdown",
    "Зберегти конспект як .md": "Save notes as .md",
    "Експорт у Word": "Export to Word",
    "Зберегти конспект як .docx": "Save notes as .docx",
    "Плани й підписка": "Plans and subscription",
    "Налаштування": "Settings",
    "Ключі API, моделі, пресети конспектування": "API keys, models, note presets",
    "Перемкнути тему": "Switch theme",
    "Темна ↔ світла": "Dark ↔ light",
    "Показати панель «Чує зараз»": "Show the Hearing now panel",
    "Сховати панель «Чує зараз»": "Hide the Hearing now panel",
    "Більше місця конспекту": "More room for the notes",
    "Оновити список мікрофонів": "Refresh microphone list",
    "Перечитати доступні пристрої запису": "Re-read available input devices",
    "Скинути лічильник квоти": "Reset the usage counter",
    "Демо: обнулити використані хвилини цього місяця":
        "Demo: zero out this month's used minutes",
    "Що зробити?": "What do you want to do?",
    "Команди  ·  Ctrl+K": "Commands  ·  Ctrl+K",
    "Тема  ·  Ctrl+D": "Theme  ·  Ctrl+D",
    "Налаштування  ·  Ctrl+,": "Settings  ·  Ctrl+,",
    "Зараз": "Now",
    # --- тости й статуси ---
    "Запис почався": "Recording started",
    "Запис зупинено, конспект збережено": "Recording stopped, notes saved",
    "Запис зупинено": "Recording stopped",
    "Налаштування збережено": "Settings saved",
    "Назву оновлено": "Title updated",
    "Збережено": "Saved",
    "Ви вийшли з акаунта": "Signed out",
    "Вітаємо": "Welcome",
    "Щоб змінити план, потрібен акаунт": "Changing the plan needs an account",
    "Експорт у Word доступний з плану Pro": "Word export starts with the Pro plan",
    "Місячна квота вичерпана — запис зупинено":
        "Monthly quota used up — recording stopped",
    "Лічильник квоти обнулено (демо)": "Usage counter reset (demo)",
    "Ctrl+K — усі команди · Ctrl+R — запис · Ctrl+N — нова сесія":
        "Ctrl+K — all commands · Ctrl+R — record · Ctrl+N — new session",
    "Немає ключів API": "API keys missing",
    "Додай у налаштуваннях": "Add them in Settings",
    "Назва лекції": "Lecture title",
    "Як називається лекція?": "What is this lecture called?",
    "Назва лекції:": "Lecture title:",
    "Лекція": "Lecture",
    "Сесія": "Session",
    "створена": "created",
    # --- акаунт ---
    "Увійти": "Sign in",
    "Створити акаунт": "Create account",
    "Вийти": "Sign out",
    "План": "Plan",
    "Без акаунта все працює локально": "Everything works locally without an account",
    "Вхід": "Sign in",
    "Акаунт OmniScribe": "OmniScribe account",
    "Ім'я та прізвище": "Full name",
    "Пошта": "Email",
    "Пароль": "Password",
    "Уже є акаунт?": "Already have an account?",
    "Ще немає акаунта?": "No account yet?",
    "Зареєструватися": "Sign up",
    "Потрібен для оплати плану й синхронізації між пристроями.":
        "Needed to pay for a plan and sync across devices.",
    "Конспекти лишаються на цьому комп'ютері в будь-якому разі.":
        "Your notes stay on this computer either way.",
    "Акаунт зберігається лише на цьому комп'ютері — сервера поки немає.":
        "The account is stored on this computer only — there is no server yet.",
    # --- плани ---
    "Плани": "Plans",
    "Плани OmniScribe": "OmniScribe plans",
    "Поточний план": "Current plan",
    "ПОТОЧНИЙ": "CURRENT",
    "Обрати": "Choose",
    "/ міс": "/ mo",
    "без ліміту": "unlimited",
    "год/міс": "h/mo",
    "Квота рахується за хвилинами запису. Зміна плану діє одразу, "
    "конспекти лишаються локальними в будь-якому плані.":
        "Quota counts recorded minutes. Plan changes apply immediately; "
        "notes stay local on every plan.",
    "Демо-режим: оплата не проводиться, дані картки нікуди не надсилаються.":
        "Demo mode: no payment is taken, card details go nowhere.",
    "ДЕМО — платіж не проводиться": "DEMO — no payment is taken",
    "Номер тестової картки": "Test card number",
    "Термін дії": "Expiry",
    "Приймається лише тестовий номер 4242 4242 4242 4242.":
        "Only the test number 4242 4242 4242 4242 is accepted.",
    "Це демо — введи тестовий номер 4242 4242 4242 4242.":
        "This is a demo — enter the test number 4242 4242 4242 4242.",
    "Оформити за": "Subscribe for",
    "Обробка…": "Processing…",
    "модель": "model",
    "активовано": "activated",
    "хв": "min",
    "год": "h",
    "цього місяця": "this month",
    "з": "of",
    # --- налаштування ---
    "Акаунт": "Account",
    "Загальні": "General",
    "Вигляд": "Appearance",
    "Моделі": "Models",
    "Про застосунок": "About",
    "Мова інтерфейсу": "Interface language",
    "Застосовується одразу, без перезапуску.": "Applies immediately, no restart.",
    "Тема": "Theme",
    "Темна": "Dark",
    "Світла": "Light",
    "Відтінок": "Base tone",
    "Щільність": "Density",
    "Компактно": "Compact",
    "Зручно": "Comfortable",
    "Просторо": "Spacious",
    "Розмір тексту": "Text size",
    "Дрібний": "Small",
    "Звичайний розмір": "Default",
    "Великий": "Large",
    "Вугільна": "Coal",
    "Графітова": "Graphite",
    "Чорнильна": "Ink",
    "Папір": "Paper",
    "Сніг": "Snow",
    "Тепла": "Warm",
    "Панель «Чує зараз»": "Hearing now panel",
    "Показувати сирий текст розпізнавання поруч із конспектом":
        "Show raw transcription next to the notes",
    "Ключ Groq": "Groq key",
    "Ключ Anthropic": "Anthropic key",
    "Потрібен для розпізнавання мовлення (Whisper).":
        "Needed for speech recognition (Whisper).",
    "Потрібен для оформлення конспекту (Claude).":
        "Needed for turning speech into notes (Claude).",
    "Модель Claude": "Claude model",
    "Зусилля": "Effort",
    "Нижче зусилля — швидша відповідь під час лекції.":
        "Lower effort means a faster reply during the lecture.",
    "Модель Whisper": "Whisper model",
    "Мова лекції": "Lecture language",
    "Код мови, яку говорить лектор: uk, en, pl…":
        "Code of the language the lecturer speaks: uk, en, pl…",
    "Пресет конспектування": "Note-taking preset",
    "Детальний конспект": "Detailed notes",
    "Стислі тези": "Key points only",
    "Підготовка до іспиту": "Exam preparation",
    "Зберегти": "Save",
    "Версія": "Version",
    "База конспектів": "Notes database",
    "Шрифти": "Fonts",
    "Усі конспекти зберігаються локально. Жоден запис не залишає цей комп'ютер, "
    "крім фрагментів аудіо й тексту, які йдуть у Groq і Anthropic для обробки.":
        "All notes are stored locally. Nothing leaves this computer except the audio "
        "and text fragments sent to Groq and Anthropic for processing.",
}

_TABLES = {"en": _EN}
_current = DEFAULT


def set_language(code: str) -> None:
    global _current
    _current = code if code in LANGUAGES else DEFAULT


def language() -> str:
    return _current


def t(text: str) -> str:
    table = _TABLES.get(_current)
    return table.get(text, text) if table else text
