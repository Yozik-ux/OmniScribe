"""Дизайн-система застосунку: темна (дефолт) і світла тема.

Строго чорно-сіро-білий: жоден елемент хроми не несе кольору — акцент
будується вагою (bold), контрастом (чорне/біле) і лінією (підкреслення,
рамка), а не кольоровою плямою. Playfair Display для заголовків,
Inter/Jost — для решти тексту.

Шрифти вантажаться з assets/fonts/ у app.py — система рідко має їх
встановленими, а без цього QSS font-family тихо відкочується на дефолт.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

ORG, APP = "OmniScribe", "OmniScribe"

# Відступи — єдина шкала замість довільних чисел по файлу. Модулі імпортують
# ці імена, тож щільність множить їх один раз при старті (apply_density), а
# не в кожному місці використання.
SPACE_XS = 6
SPACE_SM = 10
SPACE_MD = 16
SPACE_LG = 24
SPACE_XL = 32

RADIUS_SM = 8

_BASE_SPACING = (6, 10, 16, 24, 32)

# Кастомізація не чіпає саму систему — вона крутить рівно три ручки, кожна
# з яких лишає дизайн цілим: відтінок основи, щільність і кегль. Акцентного
# кольору серед них немає свідомо: хрома тут монохромна за задумом.
DENSITY = {
    "compact": 0.8,
    "comfortable": 1.0,
    "spacious": 1.25,
}
TEXT_SCALE = {
    "small": 0.92,
    "normal": 1.0,
    "large": 1.12,
}
TONES = {
    "dark": {
        "coal": {"name": "Вугільна", "bg": "#0a0a0a", "surface": "#1a1a1a",
                 "surface_raised": "#212121", "surface_alt": "#272727",
                 "border": "#343434", "border_soft": "#222222"},
        "graphite": {"name": "Графітова", "bg": "#121214", "surface": "#1b1b1f",
                     "surface_raised": "#232328", "surface_alt": "#2a2a30",
                     "border": "#3a3a42", "border_soft": "#26262c"},
        "ink": {"name": "Чорнильна", "bg": "#0d1117", "surface": "#161b22",
                "surface_raised": "#1c232c", "surface_alt": "#222b35",
                "border": "#30363d", "border_soft": "#1d242c"},
    },
    "light": {
        "paper": {"name": "Папір", "bg": "#f1f1f1", "surface": "#ffffff",
                  "surface_raised": "#ffffff", "surface_alt": "#e9e9e9",
                  "border": "#dcdcdc", "border_soft": "#e7e7e7"},
        "snow": {"name": "Сніг", "bg": "#fafafa", "surface": "#ffffff",
                 "surface_raised": "#ffffff", "surface_alt": "#f0f0f0",
                 "border": "#e2e2e2", "border_soft": "#eeeeee"},
        "warm": {"name": "Тепла", "bg": "#f4f1ec", "surface": "#fffdfa",
                 "surface_raised": "#fffdfa", "surface_alt": "#ebe6dd",
                 "border": "#ddd6ca", "border_soft": "#e8e2d8"},
    },
}

PALETTES = {
    "dark": {
        "bg": "#0a0a0a",
        "surface": "#1a1a1a",
        "surface_raised": "#212121",
        "surface_alt": "#272727",
        "border": "#343434",
        "border_soft": "#222222",
        "text": "#e6e6e6",
        "text_dim": "#8a8a8a",
        # 4.7:1 на тлі #0a0a0a — найтемніше, що ще проходить WCAG AA для
        # дрібного тексту (попередній #5c5c5c давав лише 3.0:1).
        "text_faint": "#7a7a7a",
        "heading": "#ffffff",
        "accent": "#ffffff",
        "accent_hover": "#cfcfcf",
        "accent_soft": "#2a2a2a",
        "accent_text": "#0a0a0a",
        "rail": "#ffffff",
        "warning": "#ffffff",
        "danger": "#e6e6e6",
        # Колір існує ТІЛЬКИ для станів (правило Vercel): запис, успіх,
        # застереження, помилка. Ніде більше в хромі кольору немає.
        "status_live": "#f85149",
        "status_ok": "#3fb950",
        "status_warn": "#d29922",
        "status_err": "#f85149",
    },
    "light": {
        "bg": "#f1f1f1",
        "surface": "#ffffff",
        "surface_raised": "#ffffff",
        "surface_alt": "#e9e9e9",
        "border": "#dcdcdc",
        "border_soft": "#e7e7e7",
        "text": "#1a1a1a",
        "text_dim": "#5e5e5e",
        # 4.9:1 на тлі #f1f1f1 (попередній #9c9c9c давав 2.4:1).
        "text_faint": "#666666",
        "heading": "#000000",
        "accent": "#111111",
        "accent_hover": "#333333",
        "accent_soft": "#e4e4e4",
        "accent_text": "#ffffff",
        "rail": "#000000",
        "warning": "#000000",
        "danger": "#1a1a1a",
        "status_live": "#d1242f",
        "status_ok": "#1a7f37",
        "status_warn": "#9a6700",
        "status_err": "#d1242f",
    },
}


# Маркери тексту — єдине місце, де колір живе у ЗМІСТІ конспекту (хрома
# лишається чорно-сіро-білою). Кольори приглушені й попередньо змішані з
# фоном теми, тому не світяться на темному; пари fg/bg дають ≥7:1.
MARKERS: dict[str, dict[str, dict[str, str]]] = {
    "dark": {
        "yellow": {"bg": "#4a3f14", "fg": "#f3e3a0", "name": "Важливе"},
        "green": {"bg": "#1e3a24", "fg": "#a8e6b8", "name": "Означення"},
        "blue": {"bg": "#1c3448", "fg": "#a8d4f0", "name": "Приклад"},
        "rose": {"bg": "#45212a", "fg": "#f5b8c4", "name": "Застереження"},
        "orange": {"bg": "#4a3119", "fg": "#f5cba0", "name": "Запитають"},
    },
    "light": {
        "yellow": {"bg": "#fff3b8", "fg": "#4a3c00", "name": "Важливе"},
        "green": {"bg": "#ccf0d4", "fg": "#10401c", "name": "Означення"},
        "blue": {"bg": "#cfe6fa", "fg": "#0b3350", "name": "Приклад"},
        "rose": {"bg": "#fbd5dd", "fg": "#4d1120", "name": "Застереження"},
        "orange": {"bg": "#ffe0bd", "fg": "#4a2a05", "name": "Запитають"},
    },
}

# Яким маркером малюється розмітка, що приходить від Claude.
SEMANTIC_MARKER = {
    "highlight": "yellow",   # ==важливе==
    "definition": "green",   # ++означення++
    "warning": "rose",       # !!попередження!!
}


def markers(theme_name: str) -> dict[str, dict[str, str]]:
    return MARKERS.get(theme_name, MARKERS["dark"])


def settings() -> QSettings:
    return QSettings(ORG, APP)


def load_theme_name() -> str:
    return settings().value("theme", "dark")


def save_theme_name(name: str) -> None:
    settings().setValue("theme", name)


def preference(key: str, default: str) -> str:
    return settings().value(key, default)


def save_preference(key: str, value: str) -> None:
    settings().setValue(key, value)


def apply_density(level: str) -> None:
    """Перераховує модульну шкалу відступів під обрану щільність."""
    global SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG, SPACE_XL
    factor = DENSITY.get(level, 1.0)
    SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG, SPACE_XL = (
        max(2, round(value * factor)) for value in _BASE_SPACING
    )


def tones(theme_name: str) -> dict[str, dict[str, str]]:
    return TONES.get(theme_name, TONES["dark"])


def palette(name: str) -> dict:
    """Базова палітра теми з накладеним відтінком із налаштувань."""
    base = dict(PALETTES.get(name, PALETTES["dark"]))
    available = tones(name)
    tone_key = preference(f"tone_{name}", next(iter(available)))
    tone = available.get(tone_key)
    if tone:
        base.update({k: v for k, v in tone.items() if k != "name"})
    return base


def build_qss(name: str) -> str:
    c = palette(name)
    scale = TEXT_SCALE.get(preference("text_scale", "normal"), 1.0)

    def pt(size: float) -> str:
        """Кегль із урахуванням обраного розміру тексту."""
        return f"{round(size * scale, 1)}pt"

    return f"""
    * {{
        font-family: "Inter", "Jost", sans-serif;
        color: {c['text']};
        font-size: {pt(10.5)};
    }}
    QMainWindow, QWidget {{
        background-color: {c['bg']};
    }}
    QLabel {{
        /* QLabel теж QWidget — без цього він успадковує суцільний фон
        сторінки вище і малює прямокутник під текстом замість прозорого тла. */
        background-color: transparent;
    }}
    QWidget#Sidebar {{
        background-color: {c['bg']};
        border-right: 1px solid {c['border_soft']};
    }}
    QWidget#TopBar {{
        background-color: {c['surface']};
        border-bottom: 1px solid {c['border_soft']};
    }}
    QLabel#BrandRest {{
        font-family: "Playfair Display", serif;
        font-size: {pt(26)};
        font-weight: 600;
        color: {c['heading']};
    }}
    QLabel#SectionLabel {{
        /* Без tracked-out ALL CAPS: розріджені великі літери над кожним
        блоком — найпомітніша ознака шаблонного інтерфейсу. */
        color: {c['text_faint']};
        font-size: {pt(9.5)};
        font-weight: 500;
    }}
    QToolButton#Tool {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 6px;
        color: {c['text_dim']};
        font-size: {pt(10.5)};
        padding: 0;
    }}
    QToolButton#Tool:hover {{
        background-color: {c['surface_alt']};
        color: {c['heading']};
    }}
    QToolButton#Tool:pressed {{
        background-color: {c['border_soft']};
    }}
    QToolButton#Tool:checked {{
        background-color: {c['surface_alt']};
        border-color: {c['border']};
        color: {c['heading']};
    }}
    QToolButton#Tool::menu-indicator {{
        image: none;
    }}
    QComboBox#BlockStyle {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 3px 8px;
        min-height: 18px;
        color: {c['text_dim']};
    }}
    QComboBox#BlockStyle:hover {{
        background-color: {c['surface_alt']};
        color: {c['heading']};
    }}
    QFrame#ToolDivider {{
        background-color: {c['border_soft']};
        max-width: 1px;
        min-width: 1px;
        border: none;
    }}
    QMenu {{
        background-color: {c['surface_raised']};
        border: 1px solid {c['border']};
        border-radius: {RADIUS_SM}px;
        padding: 5px;
    }}
    QMenu::item {{
        padding: 6px 14px;
        border-radius: 5px;
        color: {c['text']};
    }}
    QMenu::item:selected {{
        background-color: {c['surface_alt']};
        color: {c['heading']};
    }}
    QMenu::separator {{
        height: 1px;
        background: {c['border_soft']};
        margin: 4px 6px;
    }}
    QLabel#FieldLabel {{
        color: {c['text_dim']};
        font-size: {pt(9.5)};
    }}
    QLabel#LiveDot {{
        background-color: {c['status_live']};
        border-radius: 4px;
    }}
    QLabel#LiveDotIdle {{
        background-color: {c['text_faint']};
        border-radius: 4px;
    }}
    QLabel#Kbd {{
        background-color: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: 5px;
        color: {c['text_dim']};
        font-family: "Inter", sans-serif;
        font-size: {pt(8.5)};
        font-weight: 600;
        padding: 2px 6px;
    }}
    QLabel#Pill, QLabel#PillOk, QLabel#PillWarn, QLabel#PillLive {{
        border: 1px solid {c['border']};
        border-radius: 9px;
        font-size: {pt(8.5)};
        font-weight: 600;
        letter-spacing: 0.4px;
        padding: 2px 9px;
        color: {c['text_dim']};
    }}
    QLabel#PillOk {{
        color: {c['status_ok']};
        border-color: {c['status_ok']};
    }}
    QLabel#PillWarn {{
        color: {c['status_warn']};
        border-color: {c['status_warn']};
    }}
    QLabel#PillLive {{
        color: {c['status_live']};
        border-color: {c['status_live']};
    }}
    QLabel#CardTitle {{
        font-family: "Playfair Display", serif;
        font-size: {pt(14)};
        font-weight: 600;
        color: {c['heading']};
    }}
    QLabel#MetaText {{
        color: {c['text_faint']};
        font-size: {pt(9)};
    }}
    QLineEdit {{
        background-color: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: {RADIUS_SM}px;
        padding: 7px 10px;
        selection-background-color: {c['accent']};
        selection-color: {c['accent_text']};
    }}
    QLineEdit:focus {{
        border-color: {c['accent']};
    }}
    QLineEdit#Search {{
        background-color: transparent;
        border: 1px solid {c['border_soft']};
        padding: 6px 10px;
        color: {c['text']};
    }}
    QLineEdit#Search:focus {{
        border-color: {c['border']};
        background-color: {c['surface']};
    }}
    QProgressBar#Quota {{
        background-color: {c['surface_alt']};
        border: none;
        border-radius: 2px;
        max-height: 4px;
        min-height: 4px;
    }}
    QProgressBar#Quota::chunk {{
        background-color: {c['text_dim']};
        border-radius: 2px;
    }}
    /* Стан — динамічна властивість, а не інший objectName: інакше правило
    вище перестає збігатись і прогрес-бар втрачає висоту й радіус. */
    QProgressBar#Quota[state="warn"]::chunk {{
        background-color: {c['status_warn']};
    }}
    QProgressBar#Quota[state="full"]::chunk {{
        background-color: {c['status_err']};
    }}
    QDialog#Palette {{
        background-color: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 14px;
    }}
    QLineEdit#PaletteInput {{
        background-color: transparent;
        border: none;
        border-bottom: 1px solid {c['border_soft']};
        border-radius: 0;
        font-size: {pt(14)};
        padding: 14px 18px;
        color: {c['heading']};
    }}
    QListWidget#PaletteList::item {{
        padding: 0;
        margin: 2px 8px;
        border-left: 0;
        border-radius: {RADIUS_SM}px;
    }}
    QListWidget#PaletteList::item:selected {{
        background-color: {c['surface_alt']};
        color: {c['heading']};
        border-left: 0;
    }}
    QListWidget#SettingsNav {{
        background-color: {c['surface']};
        border-right: 1px solid {c['border_soft']};
        padding: {SPACE_MD}px {SPACE_SM}px;
    }}
    QListWidget#SettingsNav::item {{
        padding: {SPACE_SM}px {SPACE_MD}px;
        margin: 2px 0;
        border-left: 3px solid transparent;
        border-radius: {RADIUS_SM}px;
        /* Ліві кути прямі: інакше рамка-рейка вигинається дугою разом з
        радіусом і читається як випадковий артефакт. */
        border-top-left-radius: 0;
        border-bottom-left-radius: 0;
        color: {c['text_dim']};
    }}
    QListWidget#SettingsNav::item:selected {{
        background-color: {c['accent_soft']};
        border-left: 3px solid {c['rail']};
        color: {c['heading']};
    }}
    QListWidget#SettingsNav::item:hover:!selected {{
        background-color: {c['surface_raised']};
        color: {c['text']};
    }}
    QCheckBox {{
        spacing: 8px;
        color: {c['text']};
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {c['border']};
        border-radius: 4px;
        background-color: {c['surface_alt']};
    }}
    QCheckBox::indicator:checked {{
        background-color: {c['accent']};
        border-color: {c['accent']};
    }}
    QFrame#Divider {{
        background-color: {c['border_soft']};
        max-height: 1px;
        min-height: 1px;
        border: none;
    }}
    QListWidget {{
        background-color: transparent;
        border: none;
        outline: none;
    }}
    QListWidget::item {{
        padding: {SPACE_SM}px {SPACE_MD}px {SPACE_SM}px {SPACE_MD - 3}px;
        border-left: 3px solid transparent;
        margin: 2px 2px;
        color: {c['text_dim']};
    }}
    QListWidget::item:selected {{
        background-color: {c['accent_soft']};
        border-left: 3px solid {c['rail']};
        color: {c['heading']};
    }}
    QListWidget::item:hover:!selected {{
        background-color: {c['surface_raised']};
        color: {c['text']};
    }}
    QTextEdit, QTextBrowser {{
        background-color: transparent;
        border: none;
        padding: 2px;
        selection-background-color: {c['accent']};
        selection-color: {c['accent_text']};
    }}
    QComboBox {{
        background-color: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: {RADIUS_SM}px;
        padding: 7px 12px;
        min-height: 20px;
    }}
    QComboBox:hover {{
        border-color: {c['accent']};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {c['surface_raised']};
        border: 1px solid {c['border']};
        border-radius: {RADIUS_SM}px;
        selection-background-color: {c['accent_soft']};
        padding: 4px;
    }}
    QPushButton {{
        background-color: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: {RADIUS_SM}px;
        padding: 9px 18px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        border-color: {c['accent']};
        color: {c['heading']};
    }}
    QPushButton:pressed {{
        background-color: {c['border_soft']};
    }}
    QPushButton:disabled {{
        color: {c['text_faint']};
        border-color: {c['border_soft']};
    }}
    /* Суцільна заливка лишилась тільки для рішень у діалогах (зберегти,
    створити акаунт, обрати план). У головному вікні таких плям немає —
    там усі дії тональні, бо постійна біла пляма на темному тлі кричить
    гучніше за сам конспект. */
    QPushButton#Primary {{
        background-color: {c['accent']};
        color: {c['accent_text']};
        border: none;
        font-weight: 600;
        padding: 9px 22px;
        border-radius: 10px;
    }}
    QPushButton#Primary:hover {{
        background-color: {c['accent_hover']};
    }}
    QPushButton#Tonal {{
        background-color: {c['surface_alt']};
        border: 1px solid {c['border_soft']};
        border-radius: 10px;
        padding: 9px 16px;
        color: {c['text']};
        font-weight: 500;
    }}
    QPushButton#Tonal:hover {{
        background-color: {c['surface_raised']};
        border-color: {c['border']};
        color: {c['heading']};
    }}
    QPushButton#Tonal:pressed {{
        background-color: {c['border_soft']};
    }}
    QPushButton#Link {{
        background: transparent;
        border: none;
        padding: 0 2px;
        color: {c['text']};
        font-size: {pt(9.5)};
        text-decoration: underline;
    }}
    QPushButton#Link:hover {{
        color: {c['heading']};
    }}
    QPushButton#BottomIcon {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 14px;
        color: {c['text_dim']};
        font-size: {pt(11)};
        padding: 0;
    }}
    QPushButton#BottomIcon:hover {{
        background-color: {c['surface_alt']};
        color: {c['heading']};
    }}
    QPushButton#Avatar {{
        background-color: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: 17px;
        color: {c['text']};
        font-size: {pt(9.5)};
        font-weight: 600;
        padding: 0;
    }}
    QPushButton#Avatar:hover {{
        border-color: {c['accent']};
        color: {c['heading']};
    }}
    QPushButton#Ghost {{
        background-color: transparent;
        border: 1px solid transparent;
    }}
    QPushButton#Ghost:hover {{
        background-color: {c['surface_alt']};
        border-color: transparent;
    }}
    QPushButton#IconToggle {{
        background-color: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: 18px;
        font-size: {pt(12)};
        padding: 0;
    }}
    QPushButton#SidebarAction {{
        background-color: transparent;
        border: 1px dashed {c['border']};
        text-align: left;
        padding: 9px 14px;
        color: {c['text_dim']};
    }}
    QPushButton#SidebarAction:hover {{
        border-color: {c['accent']};
        color: {c['heading']};
    }}
    QStatusBar {{
        background-color: {c['bg']};
        color: {c['text_faint']};
        border-top: 1px solid {c['border_soft']};
        font-size: {pt(9)};
        padding: 2px 4px;
    }}
    QSplitter::handle {{
        background-color: transparent;
        width: {SPACE_MD}px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 4px 0;
    }}
    QScrollBar::handle:vertical {{
        background: {c['border']};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c['accent']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    """


def html_colors(name: str) -> dict:
    c = palette(name)
    return {
        "text": c["text"],
        "text_dim": c["text_dim"],
        "heading": c["heading"],
        "accent": c["accent"],
        "warning": c["warning"],
        "border": c["border_soft"],
        "markers": markers(name),
    }
