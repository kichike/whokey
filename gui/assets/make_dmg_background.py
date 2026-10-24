"""Рисует фон окна установщика (.dmg) в стиле приложения: тёмный фон с фиолетовым
заревом, неоновое «WhoKey», стрелка «перетащите сюда» и подсказка на двух языках.

Иконки WhoKey и «Программы» Finder рисует сам поверх фона — в точках APP_POS и
APPS_POS (их же использует build_dmg.sh).

Запуск: ../../../.venv/bin/python make_dmg_background.py путь/к/фону.png
"""

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QGuiApplication, QImage, QPainter,
                           QPainterPath, QPen, QRadialGradient)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from gui import theme  # noqa: E402  — цвета и шрифт приложения

WIDTH, HEIGHT = 660, 420
APP_POS = (170, 220)   # центр иконки WhoKey
APPS_POS = (490, 220)  # центр иконки «Программы»

app = QGuiApplication(sys.argv)
family = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(theme.FONT_FILE)))[0]

SCALE = 2  # рисуем в 2 раза крупнее и уменьшаем — так края получаются гладкими
img = QImage(WIDTH * SCALE, HEIGHT * SCALE, QImage.Format_ARGB32)
img.fill(QColor(theme.BG))
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
p.scale(SCALE, SCALE)

# фиолетовое зарево сверху — как в окнах приложения
glow = QRadialGradient(QPointF(WIDTH / 2, -60), 420)
glow.setColorAt(0, QColor("#381f52"))
glow.setColorAt(0.5, QColor("#170f20"))
glow.setColorAt(1, QColor(theme.BG))
p.fillRect(QRectF(0, 0, WIDTH, HEIGHT), glow)


def neon_text(text, size, y, color, weight=QFont.Bold, glow_alpha=90):
    """Текст по центру с мягким свечением (несколько полупрозрачных слоёв со сдвигом)."""
    font = QFont(family, size, weight)
    p.setFont(font)
    rect = QRectF(0, y, WIDTH, size * 2)
    light = QColor(color)
    for radius in (3, 2, 1):
        light.setAlpha(glow_alpha // radius)
        p.setPen(light)
        for dx, dy in ((-radius, 0), (radius, 0), (0, -radius), (0, radius)):
            p.drawText(rect.translated(dx, dy), Qt.AlignHCenter | Qt.AlignTop, text)
    p.setPen(QColor(color))
    p.drawText(rect, Qt.AlignHCenter | Qt.AlignTop, text)


neon_text("WhoKey", 40, 26, theme.NEON)

# неоновая стрелка между иконками: «тащи отсюда — туда»
arrow = QPainterPath()
x1, x2, y = APP_POS[0] + 85, APPS_POS[0] - 85, APP_POS[1] - 10
arrow.moveTo(x1, y)
arrow.lineTo(x2, y)
arrow.moveTo(x2 - 16, y - 12)
arrow.lineTo(x2, y)
arrow.lineTo(x2 - 16, y + 12)
for width, alpha in ((10, 40), (6, 80), (3, 255)):  # свечение = несколько линий потолще и прозрачнее
    color = QColor(theme.ACC)
    color.setAlpha(alpha)
    p.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(arrow)

hint = QFont(family, 17, QFont.DemiBold)
p.setFont(hint)
p.setPen(QColor(theme.TEXT))
p.drawText(QRectF(0, 322, WIDTH, 28), Qt.AlignHCenter, "Перетащите WhoKey в папку «Программы»")
p.setFont(QFont(family, 14))
p.setPen(QColor(theme.MUTED))
p.drawText(QRectF(0, 354, WIDTH, 24), Qt.AlignHCenter, "Drag WhoKey to the Applications folder")
p.end()

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dmg_background.png")
img.scaled(WIDTH, HEIGHT, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(str(out))
print(f"фон готов: {out}")
