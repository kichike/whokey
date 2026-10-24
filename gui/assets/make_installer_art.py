"""Рисует картинки для установщика Windows (Inno Setup, installer.iss) в стиле приложения.

- back*.png  — фон всех страниц: почти чёрный с фиолетовым заревом сверху, как окна
               WhoKey (соотношение сторон 497:360 — так требует Inno Setup);
- side*.png  — левая панель первой и последней страниц: иконка и неоновое «WhoKey»
               на прозрачном фоне (под ней виден фон);
- small*.png — логотип в углу остальных страниц.
Каждая картинка в нескольких размерах: Inno Setup сам берёт подходящую под масштаб экрана.

Запуск: ../../../.venv/bin/python make_installer_art.py   (из папки gui/assets)
"""

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QGuiApplication, QImage, QPainter,
                           QPainterPath, QRadialGradient)

HERE = Path(__file__).parent
OUT = HERE / "installer"
sys.path.insert(0, str(HERE.parent.parent))
from gui import theme  # noqa: E402  — цвета и шрифт приложения

app = QGuiApplication(sys.argv)
family = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(theme.FONT_FILE)))[0]
ICON = QImage(str(HERE / "icon.png"))
TILE = ICON.copy(100, 100, 824, 824)  # плитка без полей macOS (см. make_icon.py)
OUT.mkdir(exist_ok=True)


def canvas(width, height, fill=None):
    img = QImage(width, height, QImage.Format_ARGB32)
    img.fill(QColor(fill) if fill else Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    return img, p


def neon_text(p, text, rect, size, color, scale):
    """Текст по центру с мягким свечением — как заголовок в приложении."""
    p.setFont(QFont(family, size, QFont.Black))
    light = QColor(color)
    for radius in (2 * scale, scale):  # сдвиг 1–2 px на экране: сильнее — буквы расплываются
        light.setAlpha(60 // (radius // scale))
        p.setPen(light)
        for dx, dy in ((-radius, 0), (radius, 0), (0, -radius), (0, radius)):
            p.drawText(rect.translated(dx, dy), Qt.AlignCenter, text)
    p.setPen(QColor(color))
    p.drawText(rect, Qt.AlignCenter, text)


def back(scale):
    w, h = 596 * scale, 432 * scale
    img, p = canvas(w, h, theme.BG)
    glow = QRadialGradient(QPointF(w / 2, -0.15 * h), 1.1 * w)  # то же зарево, что в theme.STYLE
    glow.setColorAt(0, QColor("#3f2160"))
    glow.setColorAt(0.45, QColor("#1a1024"))
    glow.setColorAt(1, QColor(theme.BG))
    p.fillRect(QRectF(0, 0, w, h), glow)
    p.end()
    img.save(str(OUT / f"back{scale}x.png"))


def side(scale):
    w, h = 164 * scale, 314 * scale
    img, p = canvas(w, h)
    size = 104 * scale
    tile = QRectF((w - size) / 2, 70 * scale, size, size)
    # мягкое фиолетовое свечение под иконкой — гаснет внутри панели, иначе на её
    # краю видна ровная вертикальная граница
    halo = QRadialGradient(tile.center(), w * 0.5)
    halo.setColorAt(0, QColor(147, 111, 196, 110))
    halo.setColorAt(1, QColor(147, 111, 196, 0))
    p.fillRect(QRectF(0, 0, w, h), halo)
    p.drawImage(tile, TILE)
    neon_text(p, "WhoKey", QRectF(0, tile.bottom() + 18 * scale, w, 40 * scale), 25 * scale, theme.NEON, scale)
    p.setFont(QFont(family, 11 * scale))
    p.setPen(QColor(theme.MUTED))
    p.drawText(QRectF(0, tile.bottom() + 58 * scale, w, 20 * scale), Qt.AlignCenter, "password manager")
    p.end()
    img.save(str(OUT / f"side{scale}x.png"))


def small(px):
    img, p = canvas(px, px)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, px, px), px * 0.2237, px * 0.2237)
    p.setClipPath(clip)
    p.drawImage(QRectF(0, 0, px, px), TILE)
    p.end()
    img.save(str(OUT / f"small{px}.png"))


for scale in (1, 2, 3):
    back(scale)
    side(scale)
for px in (55, 83, 110, 165):  # 100%, 150%, 200%, 300% масштаба экрана
    small(px)
print("картинки установщика готовы:", OUT)
