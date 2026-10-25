"""Собирает переводы окон WhoKey: whokey_<язык>.ts -> whokey_<язык>.qm

    python3 translations/build.py           — только собрать .qm (так делают сборки)
    python3 translations/build.py --update  — сперва найти в коде новые надписи
                                              и дописать их в .ts (перевод — в Qt Linguist)

Переводить: pyside6-linguist translations/whokey_ru.ts
В whokey_en.ts переведены только надписи с числом («1 entry» / «5 entries»):
остальные английские надписи и так написаны в коде.
"""

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LANGUAGES = {"ru": "ru_RU", "en": "en_US"}


def tool(name):
    """pyside6-lupdate / pyside6-lrelease — рядом с Python, где стоит PySide6."""
    folder = Path(sys.executable).parent
    for candidate in (folder / name, folder / f"{name}.exe", folder / "Scripts" / f"{name}.exe"):
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if not found:
        sys.exit(f"Не найден {name} — он ставится вместе с PySide6 (pip install PySide6)")
    return found


def sources():
    return [str(path.relative_to(ROOT)) for path in [ROOT / "app.py", *sorted((ROOT / "gui").glob("*.py"))]]


def update():
    for lang, locale in LANGUAGES.items():
        subprocess.run([tool("pyside6-lupdate"), *sources(), "-no-obsolete", "-locations", "none",
                        "-target-language", locale, "-ts", f"translations/whokey_{lang}.ts"],
                       cwd=ROOT, check=True)


def release():
    for lang in LANGUAGES:
        subprocess.run([tool("pyside6-lrelease"), f"translations/whokey_{lang}.ts",
                        "-qm", f"translations/whokey_{lang}.qm"], cwd=ROOT, check=True)


if __name__ == "__main__":
    if "--update" in sys.argv:
        update()
    release()
