"""Налаштування: розділи ліворуч, поля праворуч.

Одна плоска форма з восьми полів змушувала читати все, щоб знайти одне.
Тут параметри розкладені за тим, навіщо людина прийшла: акаунт, загальні,
вигляд, моделі, про застосунок. Під кожним полем — рядок, який пояснює
наслідок зміни, а не повторює назву поля.

Що застосовується одразу (мова, тема, відтінок, щільність, кегль, панель
«Чує зараз»), а що — при збереженні (ключі, моделі, пресет): перше змінює
лише вигляд і скасовується так само легко, друге впливає на гроші й якість
конспекту, тож потребує свідомого «Зберегти».
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import i18n
from accounts import AccountStore
from config import Config, ENV_PATH
from env_file import update_env
from gui.theme import DENSITY, TEXT_SCALE, SPACE_LG, SPACE_MD, SPACE_SM, palette, tones
from gui.toggle import ToggleSwitch
from i18n import t
from notes_ai import PRESET_LABELS

_MODELS = ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"]
_EFFORTS = ["low", "medium", "high", "xhigh", "max"]
_VERSION = "0.1.0"

_DENSITY_LABELS = {"compact": "Компактно", "comfortable": "Зручно", "spacious": "Просторо"}
_SCALE_LABELS = {"small": "Дрібний", "normal": "Звичайний", "large": "Великий"}


class SettingsDialog(QDialog):
    """Сигнал appearanceChanged летить одразу при зміні вигляду — вікно
    налаштувань не має чекати «Зберегти», щоб показати результат."""

    appearanceChanged = Signal()

    def __init__(
        self,
        cfg: Config,
        theme_name: str,
        accounts: AccountStore,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.accounts = accounts
        self._theme_name = theme_name
        self._c = palette(theme_name)

        self.setWindowTitle(t("Налаштування"))
        self.setMinimumSize(760, 520)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setObjectName("SettingsNav")
        self.nav.setFixedWidth(196)
        self.nav.setFrameShape(QListWidget.Shape.NoFrame)
        root.addWidget(self.nav)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(SPACE_LG + 4, SPACE_LG, SPACE_LG + 4, SPACE_MD)
        right_layout.setSpacing(SPACE_MD)

        self.pages = QStackedWidget()
        right_layout.addWidget(self.pages, 1)

        footer = QHBoxLayout()
        self.footer_note = QLabel("")
        self.footer_note.setObjectName("MetaText")
        footer.addWidget(self.footer_note, 1)
        close_btn = QPushButton(t("Закрити"))
        close_btn.setObjectName("Tonal")
        close_btn.clicked.connect(self.reject)
        footer.addWidget(close_btn)
        self.save_btn = QPushButton(t("Зберегти"))
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(self._save)
        footer.addWidget(self.save_btn)
        right_layout.addLayout(footer)

        root.addWidget(right, 1)

        for title, builder in (
            ("Акаунт", self._page_account),
            ("Загальні", self._page_general),
            ("Вигляд", self._page_appearance),
            ("Моделі", self._page_models),
            ("Про застосунок", self._page_about),
        ):
            item = QListWidgetItem(t(title))
            item.setSizeHint(QSize(0, 38))
            self.nav.addItem(item)
            self.pages.addWidget(builder())

        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(1)

    # ------------------------------------------------------------- сторінки

    def _page_account(self) -> QWidget:
        page, layout = _page(t("Акаунт"))
        account = self.accounts.current()

        if account is None:
            layout.addWidget(_body(t("Без акаунта все працює локально"), self._c))
            layout.addWidget(
                _hint(t("Потрібен для оплати плану й синхронізації між пристроями."), self._c)
            )
        else:
            name = QLabel(account.name)
            name.setStyleSheet(
                f"color: {self._c['heading']}; font-size: 13pt; font-weight: 600;"
            )
            layout.addWidget(name)
            layout.addWidget(_hint(account.email, self._c))
            layout.addWidget(
                _hint(f"{t('Акаунт')}: {account.created_at.replace('T', ', ')}", self._c)
            )

        layout.addSpacing(SPACE_SM)
        layout.addWidget(
            _hint(t("Акаунт зберігається лише на цьому комп'ютері — сервера поки немає."), self._c)
        )
        layout.addStretch(1)
        return page

    def _page_general(self) -> QWidget:
        page, layout = _page(t("Загальні"))

        self.language = QComboBox()
        for code, label in i18n.LANGUAGES.items():
            self.language.addItem(label, code)
        self.language.setCurrentIndex(max(0, self.language.findData(i18n.language())))
        self.language.activated.connect(self._on_language)
        layout.addWidget(
            _field(t("Мова інтерфейсу"), self.language, t("Застосовується одразу, без перезапуску."), self._c)
        )

        self.live_panel_toggle = ToggleSwitch(
            self._theme_name, _pref("live_panel", "1") == "1"
        )
        self.live_panel_toggle.toggled.connect(self._on_live_panel)
        layout.addWidget(
            _switch_field(
                t("Панель «Чує зараз»"),
                t("Показувати сирий текст розпізнавання поруч із конспектом"),
                self.live_panel_toggle,
                self._c,
            )
        )

        self.lecture_language = QLineEdit(self.cfg.language)
        layout.addWidget(
            _field(
                t("Мова лекції"),
                self.lecture_language,
                t("Код мови, яку говорить лектор: uk, en, pl…"),
                self._c,
            )
        )

        layout.addStretch(1)
        return page

    def _page_appearance(self) -> QWidget:
        page, layout = _page(t("Вигляд"))

        self.theme_choice = QComboBox()
        self.theme_choice.addItem(t("Темна"), "dark")
        self.theme_choice.addItem(t("Світла"), "light")
        self.theme_choice.setCurrentIndex(0 if self._theme_name == "dark" else 1)
        self.theme_choice.activated.connect(self._on_theme)
        layout.addWidget(_field(t("Тема"), self.theme_choice, "", self._c))

        self.tone = QComboBox()
        self._fill_tones()
        self.tone.activated.connect(self._on_tone)
        layout.addWidget(_field(t("Відтінок"), self.tone, "", self._c))

        self.density = QComboBox()
        for key in DENSITY:
            self.density.addItem(t(_DENSITY_LABELS[key]), key)
        self.density.setCurrentIndex(
            max(0, self.density.findData(_pref("density", "comfortable")))
        )
        self.density.activated.connect(self._on_density)
        layout.addWidget(_field(t("Щільність"), self.density, "", self._c))

        self.text_scale = QComboBox()
        for key in TEXT_SCALE:
            self.text_scale.addItem(t(_SCALE_LABELS[key]), key)
        self.text_scale.setCurrentIndex(
            max(0, self.text_scale.findData(_pref("text_scale", "normal")))
        )
        self.text_scale.activated.connect(self._on_text_scale)
        layout.addWidget(_field(t("Розмір тексту"), self.text_scale, "", self._c))

        layout.addStretch(1)
        return page

    def _page_models(self) -> QWidget:
        page, layout = _page(t("Моделі"))

        self.groq_key = QLineEdit(self.cfg.groq_api_key)
        self.groq_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(
            _field(t("Ключ Groq"), self.groq_key, t("Потрібен для розпізнавання мовлення (Whisper)."), self._c)
        )

        self.anthropic_key = QLineEdit(self.cfg.anthropic_api_key)
        self.anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(
            _field(t("Ключ Anthropic"), self.anthropic_key, t("Потрібен для оформлення конспекту (Claude)."), self._c)
        )

        row = QHBoxLayout()
        row.setSpacing(SPACE_MD)

        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(_MODELS)
        self.model.setCurrentText(self.cfg.model)
        row.addWidget(_field(t("Модель Claude"), self.model, "", self._c), 2)

        self.effort = QComboBox()
        self.effort.addItems(_EFFORTS)
        self.effort.setCurrentText(self.cfg.effort)
        row.addWidget(
            _field(t("Зусилля"), self.effort, t("Нижче зусилля — швидша відповідь під час лекції."), self._c),
            1,
        )
        layout.addLayout(row)

        self.whisper_model = QLineEdit(self.cfg.whisper_model)
        layout.addWidget(_field(t("Модель Whisper"), self.whisper_model, "", self._c))

        self.preset = QComboBox()
        for key, label in PRESET_LABELS.items():
            self.preset.addItem(t(label), userData=key)
        self.preset.setCurrentIndex(max(0, self.preset.findData(self.cfg.preset)))
        layout.addWidget(_field(t("Пресет конспектування"), self.preset, "", self._c))

        layout.addStretch(1)
        return page

    def _page_about(self) -> QWidget:
        page, layout = _page("OmniScribe")
        from local_notes import default_db_path

        for label, value in (
            (t("Версія"), _VERSION),
            (t("База конспектів"), str(default_db_path())),
            (t("Шрифти"), "Inter · Jost · Playfair Display (SIL OFL)"),
        ):
            layout.addWidget(_field(label, _body(value, self._c), "", self._c))

        layout.addSpacing(SPACE_SM)
        layout.addWidget(
            _hint(
                t(
                    "Усі конспекти зберігаються локально. Жоден запис не залишає цей комп'ютер, "
                    "крім фрагментів аудіо й тексту, які йдуть у Groq і Anthropic для обробки."
                ),
                self._c,
            )
        )
        layout.addStretch(1)
        return page

    # ------------------------------------------------- миттєві зміни вигляду

    def _fill_tones(self) -> None:
        self.tone.clear()
        for key, spec in tones(self._theme_name).items():
            self.tone.addItem(t(spec["name"]), key)
        current = _pref(f"tone_{self._theme_name}", next(iter(tones(self._theme_name))))
        self.tone.setCurrentIndex(max(0, self.tone.findData(current)))

    def _on_language(self) -> None:
        _save_pref("language", self.language.currentData())
        i18n.set_language(self.language.currentData())
        self.appearanceChanged.emit()

    def _on_theme(self) -> None:
        self._theme_name = self.theme_choice.currentData()
        _save_pref("theme", self._theme_name)
        self._fill_tones()
        self.appearanceChanged.emit()

    def _on_tone(self) -> None:
        _save_pref(f"tone_{self._theme_name}", self.tone.currentData())
        self.appearanceChanged.emit()

    def _on_density(self) -> None:
        _save_pref("density", self.density.currentData())
        self.appearanceChanged.emit()

    def _on_text_scale(self) -> None:
        _save_pref("text_scale", self.text_scale.currentData())
        self.appearanceChanged.emit()

    def _on_live_panel(self, shown: bool) -> None:
        _save_pref("live_panel", "1" if shown else "0")
        self.appearanceChanged.emit()

    # ------------------------------------------------------------- збереження

    def _save(self) -> None:
        self.apply()
        self.accept()

    def apply(self) -> None:
        cfg = self.cfg
        cfg.groq_api_key = self.groq_key.text().strip()
        cfg.anthropic_api_key = self.anthropic_key.text().strip()
        cfg.model = self.model.currentText().strip()
        cfg.effort = self.effort.currentText().strip()
        cfg.whisper_model = self.whisper_model.text().strip()
        cfg.language = self.lecture_language.text().strip()
        cfg.preset = self.preset.currentData()

        update_env(
            ENV_PATH,
            {
                "GROQ_API_KEY": cfg.groq_api_key,
                "ANTHROPIC_API_KEY": cfg.anthropic_api_key,
                "CONSPEKT_MODEL": cfg.model,
                "CONSPEKT_EFFORT": cfg.effort,
                "CONSPEKT_WHISPER_MODEL": cfg.whisper_model,
                "CONSPEKT_LANGUAGE": cfg.language,
                "CONSPEKT_PRESET": cfg.preset,
            },
        )


# ------------------------------------------------------------------ дрібниці


def _pref(key: str, default: str) -> str:
    from gui.theme import preference

    return preference(key, default)


def _save_pref(key: str, value: str) -> None:
    from gui.theme import save_preference

    save_preference(key, value)


def _page(title: str) -> tuple[QWidget, QVBoxLayout]:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SPACE_MD)

    heading = QLabel(title)
    heading.setObjectName("CardTitle")
    layout.addWidget(heading)

    rule = QFrame()
    rule.setObjectName("Divider")
    rule.setFrameShape(QFrame.Shape.HLine)
    layout.addWidget(rule)
    return page, layout


def _field(label: str, widget: QWidget, hint: str, c: dict) -> QWidget:
    holder = QWidget()
    holder.setStyleSheet("background: transparent;")
    box = QVBoxLayout(holder)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(4)

    caption = QLabel(label)
    caption.setStyleSheet(f"color: {c['text_dim']}; font-size: 9.5pt;")
    box.addWidget(caption)
    box.addWidget(widget)
    if hint:
        box.addWidget(_hint(hint, c))
    return holder


def _switch_field(label: str, hint: str, switch: QWidget, c: dict) -> QWidget:
    """Рядок-перемикач: підпис ліворуч, стан праворуч — як у системних
    налаштуваннях, де око сканує лівий край, а керування тримається краю
    протилежного."""
    holder = QWidget()
    holder.setStyleSheet("background: transparent;")
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(SPACE_MD)

    texts = QVBoxLayout()
    texts.setSpacing(2)
    caption = QLabel(label)
    caption.setStyleSheet(f"color: {c['text']}; font-size: 10pt; background: transparent;")
    texts.addWidget(caption)
    texts.addWidget(_hint(hint, c))
    row.addLayout(texts, 1)
    row.addWidget(switch, 0, Qt.AlignmentFlag.AlignVCenter)
    return holder


def _hint(text: str, c: dict) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {c['text_faint']}; font-size: 9pt; background: transparent;")
    return label


def _body(text: str, c: dict) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {c['text']}; font-size: 10pt; background: transparent;")
    return label
