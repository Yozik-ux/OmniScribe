#!/usr/bin/env bash
# Збирає OmniScribe.app і .dmg для macOS.
#
# Запуск на самому Mac (PyInstaller не вміє крос-компіляцію):
#   packaging/macos/build.sh [версія]
# Результат: dist/OmniScribe-<версія>-macos.dmg
#
# Застосунок не підписаний: при першому запуску macOS покаже
# "не вдалося перевірити розробника" — відкрити через ПКМ → Відкрити,
# або зняти карантин: xattr -dr com.apple.quarantine /Applications/OmniScribe.app
set -euo pipefail
cd "$(dirname "$0")/../.."

VERSION="${1:-0.1.0}"
APP="dist/OmniScribe.app"

rm -rf build dist/OmniScribe dist/OmniScribe.app dist/*.dmg

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt pyinstaller

# .icns збирається тут, а не лежить у репозиторії: багаторозмірний ICNS
# коректно робить лише macOS-ний iconutil, а ImageMagick на Linux пише
# всередину один 16-піксельний PNG — іконка виходить мильною.
echo "==> Іконка"
ICON_ARG=()
if command -v iconutil >/dev/null && [ -f assets/logo.png ]; then
    ICONSET="$(mktemp -d)/omniscribe.iconset"
    mkdir -p "$ICONSET"
    for size in 16 32 128 256 512; do
        sips -z $size $size assets/logo.png --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
        sips -z $((size * 2)) $((size * 2)) assets/logo.png \
            --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
    done
    iconutil -c icns "$ICONSET" -o dist/logo.icns
    ICON_ARG=(--icon dist/logo.icns)
fi

echo "==> PyInstaller"

.venv/bin/pyinstaller --noconfirm --clean --windowed \
    --name OmniScribe \
    --paths . \
    --add-data "assets:assets" \
    --osx-bundle-identifier com.omniscribe.app \
    "${ICON_ARG[@]}" \
    app.py

echo "==> DMG"
OUT="dist/OmniScribe-${VERSION}-macos.dmg"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "OmniScribe" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
rm -rf "$STAGE"

echo "✅ Готово: $OUT"
