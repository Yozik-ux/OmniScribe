#!/usr/bin/env bash
# Збірка клієнта захоплення звуку.
set -euo pipefail
cd "$(dirname "$0")"

g++ -O2 -std=c++17 -Wall -Wextra \
    server.cpp \
    $(pkg-config --cflags --libs portaudio-2.0) \
    -lpthread \
    -o audio_capture

echo "✅ Готово: ./audio_capture"
