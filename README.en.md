<div align="center">

# OmniScribe

**It listens to the lecture and hands you the notes.**

[![Українська](https://img.shields.io/badge/Українська-f1f1f1?style=for-the-badge&labelColor=f1f1f1&color=f1f1f1)](README.md)
[![English](https://img.shields.io/badge/English-000000?style=for-the-badge)](README.en.md)

</div>

![OmniScribe](docs/screenshot.png)

---

OmniScribe listens to your microphone during a lecture and turns speech into
structured notes in real time: headings, key points, highlighted terms, tables
and simple diagrams. You can edit the notes right in the app and export them to
Markdown or Word.

Notes are stored locally. The app never uploads them — only audio fragments go
to Groq for transcription and text to Anthropic for formatting.

## What it does

- **Live transcription** — Whisper large-v3 via Groq, split on natural pauses
- **Notes, not a transcript** — Claude strips filler words, builds a hierarchy
  and highlights terms, dates and definitions with colour markers
- **Tables and diagrams** — when the lecturer compares things or describes a process
- **Editor** — formatting, highlighters, lists, tables, find (Ctrl+F)
- **Command palette** — Ctrl+K, every action from the keyboard
- **Two interface languages** — Ukrainian and English, switched live
- **Themes** — dark and light, three base tones, density and text size

## Install

Ready-made installers live in [Releases](../../releases).

### Windows

1. Download `OmniScribe-Setup-x.y.z.exe`
2. Run it. SmartScreen will say "unknown publisher" — the app is unsigned:
   click **More info → Run anyway**
3. The app appears in the Start menu

### macOS

1. Download `OmniScribe-x.y.z-macos.dmg`, open it, drag the app to Applications
2. First launch: right-click the app → **Open** (Gatekeeper blocks unsigned apps
   on a normal double-click)

   If macOS still refuses:
   ```bash
   xattr -dr com.apple.quarantine /Applications/OmniScribe.app
   ```

### Linux (Debian, Ubuntu)

```bash
sudo dpkg -i OmniScribe-x.y.z-linux-amd64.deb
```

Launch from the applications menu or run `omniscribe`.

## First run

You need two API keys (both have a free tier):

| Key | Where to get it | What for |
|---|---|---|
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) | speech recognition |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/settings/keys) | turning speech into notes |

Paste them into **⚙ Settings → Models**. The app stores them in
`~/.omniscribe/.env` — they never leave your computer.

Then pick a microphone at the top and press **Record**.

## Run from source

```bash
git clone https://github.com/Yozik-ux/Conspekt-AI-startup.git
cd Conspekt-AI-startup
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then paste your keys
.venv/bin/python app.py
```

Needs Python 3.11+. On Linux you may also need `portaudio19-dev` for audio.

## Build an installer yourself

PyInstaller cannot cross-compile, so each platform builds on itself:

```bash
packaging/linux/build.sh 0.1.0      # .deb
packaging/macos/build.sh 0.1.0      # .app + .dmg
packaging\windows\build.bat 0.1.0   # .exe (needs NSIS)
```

Or just push a tag — GitHub Actions builds all three and attaches them to a release:

```bash
git tag v0.1.0 && git push origin v0.1.0
```

## How it works

```
microphone → sounddevice → VAD (split on pauses) → Whisper → Claude
                                                                ↓
                editor ← SQLite ← note blocks (headings, points, markers)
                  ↓
           Markdown / Word
```

Transcription and formatting run in separate threads: while Claude is writing up
one fragment, Whisper is already decoding the next one, so nothing is lost in the queue.

| File | Purpose |
|---|---|
| `audio_io.py` | audio capture, resampling to 16 kHz |
| `vad.py` | splitting the stream into utterances on pauses |
| `notes_ai.py` | Whisper + Claude, prompt and presets |
| `mdlite.py` | parsing Claude's markup into blocks |
| `local_notes.py` | SQLite: sessions, blocks, manual edits |
| `export.py` | rendering to Markdown, Word and HTML |
| `gui/` | PySide6 interface |

## Font licences

Inter, Jost and Playfair Display are under the SIL Open Font License 1.1;
the licence texts are in `assets/fonts/`.
