<div align="center">

# OmniScribe

**Слухає лекцію — віддає готовий конспект.**

[![Українська](https://img.shields.io/badge/Українська-000000?style=for-the-badge)](README.md)
[![English](https://img.shields.io/badge/English-f1f1f1?style=for-the-badge&labelColor=f1f1f1&color=f1f1f1)](README.en.md)

</div>

![OmniScribe](docs/screenshot.png)

---

OmniScribe слухає мікрофон під час пари й у реальному часі перетворює мовлення
на структурований конспект: заголовки, тези, виділені терміни, таблиці та прості
схеми. Конспект можна правити просто в застосунку й експортувати в Markdown або Word.

Конспекти зберігаються локально. Застосунок нікуди їх не надсилає — назовні
йдуть лише фрагменти аудіо до Groq (розпізнавання) і тексту до Anthropic
(оформлення).

## Що він робить

- **Розпізнає мовлення наживо** — Whisper large-v3 через Groq, з нарізкою по паузах
- **Пише конспект, а не стенограму** — Claude прибирає слова-паразити, будує
  ієрархію, виділяє терміни, дати й означення кольоровими маркерами
- **Таблиці та схеми** — коли лектор порівнює речі або описує процес
- **Редактор** — форматування, маркери, списки, таблиці, пошук (Ctrl+F)
- **Командна палітра** — Ctrl+K, усе керування з клавіатури
- **Дві мови інтерфейсу** — українська та англійська, перемикаються наживо
- **Теми** — темна й світла, три відтінки, щільність і розмір тексту

## Встановлення

Готові інсталятори лежать у [Releases](../../releases).

### Windows

1. Завантажити `OmniScribe-Setup-x.y.z.exe`
2. Запустити. SmartScreen скаже «невідомий видавець» — застосунок не підписаний:
   натиснути **Докладніше → Виконати в будь-якому разі**
3. Застосунок з'явиться в меню «Пуск»

### macOS

1. Завантажити `OmniScribe-x.y.z-macos.dmg`, відкрити, перетягнути в Applications
2. Перший запуск: правий клік по застосунку → **Відкрити** (Gatekeeper блокує
   непідписані застосунки при звичайному подвійному кліку)

   Якщо macOS усе одно відмовляє:
   ```bash
   xattr -dr com.apple.quarantine /Applications/OmniScribe.app
   ```

### Linux (Debian, Ubuntu)

```bash
sudo dpkg -i OmniScribe-x.y.z-linux-amd64.deb
```

Запуск — з меню застосунків або командою `omniscribe`.

## Перший запуск

Потрібні два ключі (обидва мають безкоштовний тариф):

| Ключ | Де взяти | Навіщо |
|---|---|---|
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) | розпізнавання мовлення |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/settings/keys) | оформлення конспекту |

Вставити їх у **⚙ Налаштування → Моделі**. Застосунок збереже їх у
`~/.omniscribe/.env` — вони не залишають комп'ютер.

Далі: обрати мікрофон угорі, натиснути **Записати**.

## Запуск з вихідників

```bash
git clone https://github.com/Yozik-ux/Conspekt-AI-startup.git
cd Conspekt-AI-startup
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # і вставити свої ключі
.venv/bin/python app.py
```

Потрібен Python 3.11+. На Linux для звуку може знадобитись `portaudio19-dev`.

## Зібрати інсталятор самому

PyInstaller не вміє крос-компіляцію — кожна система збирається на собі:

```bash
packaging/linux/build.sh 0.1.0      # .deb
packaging/macos/build.sh 0.1.0      # .app + .dmg
packaging\windows\build.bat 0.1.0   # .exe (потрібен NSIS)
```

Або просто створити тег — GitHub Actions збере всі три й покладе в Releases:

```bash
git tag v0.1.0 && git push origin v0.1.0
```

## Як це влаштовано

```
мікрофон → sounddevice → VAD (нарізка по паузах) → Whisper → Claude
                                                                ↓
             редактор ← SQLite ← блоки конспекту (заголовки, тези, маркери)
                ↓
         Markdown / Word
```

Розпізнавання й оформлення живуть в окремих потоках: поки Claude дописує
фрагмент, Whisper уже розбирає наступний, тож мовлення не губиться в черзі.

| Файл | Призначення |
|---|---|
| `audio_io.py` | захоплення звуку, ресемплінг до 16 кГц |
| `vad.py` | нарізка потоку на репліки по паузах |
| `notes_ai.py` | Whisper + Claude, промпт і пресети |
| `mdlite.py` | розбір розмітки Claude у блоки |
| `local_notes.py` | SQLite: сесії, блоки, ручні правки |
| `export.py` | рендер у Markdown, Word і HTML |
| `gui/` | інтерфейс на PySide6 |

## Ліцензії шрифтів

Inter, Jost і Playfair Display — SIL Open Font License 1.1, тексти лежать
в `assets/fonts/`.
