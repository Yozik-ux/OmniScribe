"""OmniScribe — один застосунок: мікрофон, живий конспект, локальне
зберігання. Запуск: python app.py.

Усе всередині одного процесу (PySide6 GUI + потоки конвеєра, gui/workers.py)
— на відміну від попередньої версії, де tkinter-вікно лише запускало
server.py й C++ audio_capture як окремі процеси і показувало їхній stdout.
"""

import sys

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

import i18n
from config import Config
from gui.main_window import MainWindow
from gui.theme import apply_density, preference
from paths import base_dir

FONTS_DIR = base_dir() / "assets" / "fonts"


def _load_fonts() -> None:
    # Системи рідко мають Inter/Jost/Playfair Display встановленими — без
    # цього QSS "font-family" тихо відкочується на дефолтний шрифт ОС і весь
    # підібраний типографічний стиль губиться. Вантажимо прямо з assets/,
    # щоб вигляд не залежав від того, що стоїть на машині користувача.
    if not FONTS_DIR.exists():
        return
    for font_file in FONTS_DIR.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font_file))


def main() -> int:
    cfg = Config()
    app = QApplication(sys.argv)
    app.setApplicationName("OmniScribe")
    _load_fonts()

    # Мова й щільність мають стояти ДО побудови вікна: обидві вшиваються у
    # віджети при створенні, тож пізніше їх можна змінити лише перебудовою.
    i18n.set_language(preference("language", i18n.DEFAULT))
    apply_density(preference("density", "comfortable"))

    window = MainWindow(cfg)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
