"""Готовит иконку приложения из картинки, сгенерированной ChatGPT (logo_source.png).

1. Находит на картинке скруглённую плитку (она чуть светлее чёрного фона).
2. Делает всё вокруг плитки прозрачным.
3. Ставит плитку по сетке иконок macOS: холст 1024×1024, плитка 824×824 по центру,
   стандартное скругление macOS.
4. Собирает WhoKey.icns со всеми размерами, которые нужны macOS (16…1024 px).

Запуск: ../../../.venv/bin/python make_icon.py  (из папки gui/assets)
"""

import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath

HERE = Path(__file__).parent
CANVAS, TILE = 1024, 824  # сетка иконок macOS
app = QGuiApplication(sys.argv)

src = QImage(str(HERE / "logo_source.png")).convertToFormat(QImage.Format_ARGB32)
background = QColor(src.pixel(5, 5))  # цвет угла — это фон вокруг плитки


def differs(x, y):
    c = QColor(src.pixel(x, y))
    # у краёв плитка почти как фон (#070511 против #05050a), поэтому порог маленький;
    # шум самого фона — до 4 единиц
    return abs(c.red() - background.red()) + abs(c.green() - background.green()) \
        + abs(c.blue() - background.blue()) > 6


# границы плитки: идём от краёв к центру по средней строке и среднему столбцу
w, h = src.width(), src.height()
left = next(x for x in range(w) if differs(x, h // 2))
right = next(x for x in range(w - 1, -1, -1) if differs(x, h // 2))
top = next(y for y in range(h) if differs(w // 2, y))
bottom = next(y for y in range(h - 1, -1, -1) if differs(w // 2, y))
tile = QRectF(left, top, right - left + 1, bottom - top + 1)
print(f"плитка на исходной картинке: x {left}–{right}, y {top}–{bottom}")
# плитка квадратная — если вышло не так, границы найдены неверно
assert abs(tile.width() - tile.height()) < tile.width() * 0.03, "плитка найдена неверно"


# скругление — стандартное для иконок macOS (Big Sur и новее): ~22,4% от плитки.
# У плитки на картинке скругление чуть меньше, так что срезаются только тёмные уголки.
RADIUS = 0.2237 * TILE

icon = QImage(CANVAS, CANVAS, QImage.Format_ARGB32)
icon.fill(Qt.transparent)
painter = QPainter(icon)
painter.setRenderHint(QPainter.Antialiasing)
painter.setRenderHint(QPainter.SmoothPixmapTransform)
target = QRectF((CANVAS - TILE) / 2, (CANVAS - TILE) / 2, TILE, TILE)
path = QPainterPath()
path.addRoundedRect(target, RADIUS, RADIUS)
painter.setClipPath(path)  # всё за пределами скруглённой плитки останется прозрачным
painter.drawImage(target, src, tile)
painter.end()
icon.save(str(HERE / "icon.png"))
print("icon.png готов")

# набор размеров для macOS и сборка .icns встроенной утилитой iconutil
iconset = HERE / "WhoKey.iconset"
shutil.rmtree(iconset, ignore_errors=True)
iconset.mkdir()
for size in (16, 32, 128, 256, 512):
    for factor, suffix in ((1, ""), (2, "@2x")):
        px = size * factor
        icon.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(
            str(iconset / f"icon_{size}x{size}{suffix}.png"))
subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "WhoKey.icns")], check=True)
shutil.rmtree(iconset)
print("WhoKey.icns готов")

# иконка для Windows: один .ico со всеми размерами, которые берёт Проводник
# (Pillow ставится вместе с matplotlib в окружении проекта)
from PIL import Image  # noqa: E402

Image.open(HERE / "icon.png").save(HERE / "WhoKey.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
print("WhoKey.ico готов")
