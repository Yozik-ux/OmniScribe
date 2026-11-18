"""Шлях до застосунку, однаковий і при `python app.py`, і у зібраному
PyInstaller-бінарнику.

У зібраному вигляді `__file__` вказує не на реальне дерево проєкту, а
PyInstaller розпаковує додані через --add-data файли в sys._MEIPASS — без
цього assets/ (шрифти, логотип) просто не знаходяться в .deb/.exe.
"""

import sys
from pathlib import Path


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # noqa: SLF001 — офіційний спосіб PyInstaller
    return Path(__file__).resolve().parent
