"""Собирает WhoKey для Linux: dist/WhoKey-linux-x86_64.tar.gz.

Запускать на Linux (это делает GitHub Actions, см. .github/workflows/linux.yml):
    python build_linux.py
В архиве — программа и install.sh, который ставит её без прав администратора.
"""

import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import PyInstaller.__main__

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "gui" / "assets"
DIST = HERE / "dist"
ARCHIVE = DIST / "WhoKey-linux-x86_64.tar.gz"


def data(source, dest):
    return ["--add-data", f"{source}:{dest}"]


# переводы окон: translations/*.ts -> *.qm (Qt Linguist)
subprocess.run([sys.executable, str(HERE / "translations" / "build.py")], check=True)

PyInstaller.__main__.run([
    "--noconfirm", "--windowed", "--log-level", "WARN", "--name", "WhoKey",
    *data(HERE / "gui" / "fonts", "gui/fonts"),
    *data(HERE / "public_suffix_list.dat", "."),  # список зон для sites.py
    *[arg for svg in sorted(ASSETS.glob("*.svg")) for arg in data(svg, "gui/assets")],
    *data(ASSETS / "icon.png", "gui/assets"),
    *data(ASSETS / "key.png", "gui/assets"),
    *data(ASSETS / "key_light.png", "gui/assets"),  # то же для светлой темы
    *data(ASSETS / "about_light.png", "gui/assets"),
    *data(ASSETS / "purr.wav", "gui/assets"),
    *[arg for qm in sorted((HERE / "translations").glob("*.qm")) for arg in data(qm, "translations")],
    "--paths", str(HERE),
    "--exclude-module", "tkinter", "--exclude-module", "matplotlib",
    "--exclude-module", "pandas", "--exclude-module", "numpy",
    "--exclude-module", "PySide6.QtQml",
    "--exclude-module", "PySide6.QtQuick", "--exclude-module", "PySide6.QtPdf",
    "--exclude-module", "PySide6.QtVirtualKeyboard",
    "--distpath", str(DIST), "--workpath", str(HERE / "build"), "--specpath", str(HERE / "build"),
    str(HERE / "app.py"),
])

# Лишние части Qt. Без оформления GTK вместе с ним уходит вся библиотека GTK:
# окна WhoKey рисует сам, а чужая GTK из архива могла бы конфликтовать с системой.
internal = DIST / "WhoKey" / "_internal"
PLUGINS = internal / "PySide6" / "Qt" / "plugins"
for pattern in ("platformthemes/libqgtk3.so", "platforminputcontexts/libqtvirtualkeyboardplugin.so",
                "imageformats/libqpdf.so", "generic/*", "egldeviceintegrations/*", "platforms/libqeglfs.so",
                "platforms/libqlinuxfb.so", "platforms/libqminimal*.so", "platforms/libqvkkhrdisplay.so",
                "platforms/libqvnc.so"):
    for path in PLUGINS.glob(pattern):
        path.unlink()


def needed(path):
    """Какие библиотеки файлу нужны при запуске (по его заголовку)."""
    out = subprocess.run(["readelf", "-d", str(path)], capture_output=True, text=True).stdout
    return re.findall(r"\(NEEDED\).*\[(.+)\]", out)


def is_library(path):
    return path.is_file() and (path.suffix == ".so" or ".so." in path.name or path.name.startswith("libpython"))


# Эти есть в любой системе. Своя старая копия мешала бы видеодрайверу, которому нужна новая.
for name in ("libstdc++.so.6", "libgcc_s.so.1"):
    (internal / name).unlink(missing_ok=True)

# Оставляем только те библиотеки, до которых можно дойти от Python, его модулей, Qt и плагинов.
# Удалять можно только обычные библиотеки в двух общих папках; модули Python («_cffi_backend…») — нет.
SHARED = (internal, PLUGINS.parent / "lib")


def removable(path):
    return path.parent in SHARED and path.name.startswith("lib") and not path.name.startswith("libpython")


libraries = [path for path in internal.rglob("*") if is_library(path)]
wanted = set()
queue = [path for path in libraries if not removable(path)]
while queue:
    for name in needed(queue.pop()):
        if name not in wanted:
            wanted.add(name)
            queue.extend(path for path in libraries if path.name == name)
for path in libraries:
    if removable(path) and path.name not in wanted:
        path.unlink()

# рядом с программой — то, что нужно установщику
for name in ("install.sh", "uninstall.sh", "whokey.desktop"):
    shutil.copy(HERE / "linux" / name, DIST / "WhoKey" / name)
shutil.copy(ASSETS / "icon.png", DIST / "WhoKey" / "whokey.png")

with tarfile.open(ARCHIVE, "w:gz") as tar:
    tar.add(DIST / "WhoKey", arcname="WhoKey")
print("Готово:", ARCHIVE)
