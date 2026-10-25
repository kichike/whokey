"""Собирает WhoKey для Windows: папка dist/WhoKey с WhoKey.exe.

Запускать на Windows (это делает GitHub Actions, см. .github/workflows/windows.yml):
    python build_windows.py
Установщик из этой папки собирает Inno Setup по installer.iss.

Сборка на Python, а не скриптом оболочки: разделитель в --add-data у PyInstaller
зависит от системы (os.pathsep — «;» на Windows, «:» на Mac).
"""

import os
from pathlib import Path

import PyInstaller.__main__

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "gui" / "assets"


def data(source, dest):
    return ["--add-data", f"{source}{os.pathsep}{dest}"]


args = [
    "--noconfirm", "--windowed", "--log-level", "WARN",
    "--name", "WhoKey", "--icon", str(ASSETS / "WhoKey.ico"),
    *data(HERE / "gui" / "fonts", "gui/fonts"),
    # картинки, которые нужны окнам: галочка, стрелки, «глаз», иконка окна
    *[arg for svg in sorted(ASSETS.glob("*.svg")) for arg in data(svg, "gui/assets")],
    *data(ASSETS / "icon.png", "gui/assets"),
    *data(ASSETS / "WhoKey.ico", "gui/assets"),  # иконка окна на панели задач
    "--paths", str(HERE),
    "--exclude-module", "tkinter", "--exclude-module", "matplotlib",
    "--exclude-module", "pandas", "--exclude-module", "numpy",
    "--exclude-module", "PySide6.QtQml",
    "--exclude-module", "PySide6.QtQuick", "--exclude-module", "PySide6.QtPdf",
    "--exclude-module", "PySide6.QtVirtualKeyboard",
    "--distpath", str(HERE / "dist"), "--workpath", str(HERE / "build"), "--specpath", str(HERE / "build"),
    str(HERE / "app.py"),
]
PyInstaller.__main__.run(args)
print("Готово:", HERE / "dist" / "WhoKey" / "WhoKey.exe")
