"""Точковий апдейт .env: оновлює/додає задані ключі, лишаючи решту рядків
(і коментарі) без змін — Settings-діалог не повинен переписувати весь файл.
"""

from pathlib import Path


def update_env(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    out: list[str] = []

    for raw in lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(raw)

    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")

    path.write_text("\n".join(out) + "\n", encoding="utf-8")
