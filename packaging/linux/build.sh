#!/usr/bin/env bash
# Збирає OmniScribe у .deb-пакет для Linux (PyInstaller --onedir + dpkg-deb).
#
# Запуск: packaging/linux/build.sh [версія]
# Результат: dist/OmniScribe-<версія>-linux-amd64.deb
set -euo pipefail
cd "$(dirname "$0")/../.."

VERSION="${1:-0.1.0}"
ARCH="amd64"
PKG_NAME="omniscribe"
STAGE="dist/deb-stage"
APP_DIR="/opt/omniscribe"

rm -rf "$STAGE" "dist/OmniScribe" build
mkdir -p "$STAGE$APP_DIR" "$STAGE/usr/share/applications" "$STAGE/usr/share/icons/hicolor/256x256/apps"

echo "==> PyInstaller"
.venv/bin/pyinstaller --noconfirm --clean --onedir \
    --name OmniScribe \
    --paths . \
    --add-data "assets:assets" \
    app.py

cp -r dist/OmniScribe/* "$STAGE$APP_DIR/"

if [ -f assets/logo.png ]; then
    cp assets/logo.png "$STAGE/usr/share/icons/hicolor/256x256/apps/omniscribe.png"
fi

cat > "$STAGE/usr/share/applications/omniscribe.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OmniScribe
Comment=Лектор -> конспект у реальному часі
Exec=$APP_DIR/OmniScribe
Icon=omniscribe
Terminal=false
Categories=Education;Audio;
EOF

mkdir -p "$STAGE/usr/bin"
ln -sf "$APP_DIR/OmniScribe" "$STAGE/usr/bin/omniscribe"

mkdir -p "$STAGE/DEBIAN"
SIZE_KB=$(du -sk "$STAGE$APP_DIR" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $VERSION
Section: education
Priority: optional
Architecture: $ARCH
Installed-Size: $SIZE_KB
Maintainer: OmniScribe <gorkusaartem700@gmail.com>
Description: OmniScribe — лектор у конспект у реальному часі.
 Розпізнає мовлення (Whisper), оформлює конспект (Claude) і показує
 результат живим у застосунку; зберігає локально, без зовнішніх плагінів.
EOF

OUT="dist/OmniScribe-${VERSION}-linux-${ARCH}.deb"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT"
echo "✅ Готово: $OUT"
