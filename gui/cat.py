"""Пасхалка «😺 котик»: три нажатия на ключ в главном окне (MainWindow._logo_clicked) — мурлыканье,
вместо ключа чёрный кот неоном с горящими глазами, кошачья палитра, кружки-буквы становятся
головами чёрных котов, а снизу из-за края окна выглядывает кот. Переход — открывается кошачий зрачок.

Палитра своя для тёмной темы («Полночь»: почти чёрный, глаза жёлто-зелёные и янтарные)
и для светлой («Лунный»: серебристо-белый, тёмно-зелёный и янтарь). Только на время сеанса.
"""

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from gui import theme

# Тёмная «Полночь». Ключи — те же, что у обычной тёмной палитры (theme._DARK_COLORS).
DARK_COLORS = {
    "BG": "#07080b", "SURF": "#0d0f14", "WELL": "#06070a", "LINE": "#1b1f28", "LINE2": "#2a2f3c",
    "TEXT": "#eef1f6", "MUTED": "#a3aabb", "FAINT": "#6b7385",
    "ACC": "#c6dc4a", "ACC_DEEP": "#6f8a1c", "ACC_LIGHT": "#eef7a8", "ACC_FILL": "#2a3210",
    "MAGENTA": "#f5b83d", "NEON": "#dcec62", "RAISED": "#151821", "TIP": "#12141b", "TIP_RIM": "#333949",
    "GLOW_1": "#1f2a14", "GLOW_2": "#11160f", "GLOW_3": "#0a0c0e", "TITLE_START": "#eef7a8",
    "LETTER_TOP": "#1d2029", "LETTER_BOTTOM": "#0b0c10", "LETTER_INK": "#d4e85a",
    "ON_ACCENT": "#0b0c10",  # на жёлто-зелёной главной кнопке белый не читается
}

# Светлая «Лунный»: кроме основных цветов — тени, перелив кромки и пятна света (как у «Перламутра»).
LIGHT_COLORS = {
    "OK": "#1e7d36", "WARN": "#b07400", "BAD": "#d0304a", "BAD_INK": "#c0263b", "RAISED": "#ffffff",
    "ON_ACCENT": "#ffffff",
    "BG": "#f2f3f6", "SURF": "#fafbfc", "WELL": "#e9ebf0", "LINE": "#e0e3ea", "LINE2": "#cfd4de",
    "TEXT": "#14161d", "MUTED": "#474d5c", "FAINT": "#646b7d",
    "ACC": "#4d7a12", "ACC_DEEP": "#3f6610", "ACC_LIGHT": "#355a08", "ACC_FILL": "#e6f1cf",
    "MAGENTA": "#8a5f00", "NEON": "#4d7a12", "TIP": "#fdfdfe", "TIP_RIM": "#d8dce4",
    "GLOW_1": "#e1e8d2", "GLOW_2": "#eceef0", "GLOW_3": "#f0f1f4", "TITLE_START": "#1c1f27",
    "LETTER_TOP": "#2a2e38", "LETTER_BOTTOM": "#101218", "LETTER_INK": "#dcef7a",
    "SHADOW": "#2a3040", "IRIS_1": "#a8c860", "IRIS_2": "#e8c060", "IRIS_3": "#a0b0c8",
    "LAVENDER": "#dfe8c8", "PINK": "#f3e3b8", "SKY": "#cfd8e8",
}

# сам кот: шерсть (верх, низ), внутри ушей, глаза, нос
FUR = ("#2a2d36", "#0b0c10")
EAR = "#3a3040"
EYES = "#d8ee4a"
NOSE = "#5a4a58"


# --- кот ---

def _head_path(r):
    """Голова кота с ушами в квадрате r (QRectF)."""
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    path = QPainterPath()
    path.addEllipse(QRectF(x + w * 0.06, y + h * 0.26, w * 0.88, h * 0.70))
    for side in (-1, 1):
        cx = x + w / 2
        ear = QPainterPath()
        base_in, base_out, tip = cx + side * w * 0.06, cx + side * w * 0.44, QPointF(cx + side * w * 0.38, y + h * 0.04)
        ear.moveTo(base_in, y + h * 0.36)
        ear.quadTo(QPointF(cx + side * w * 0.20, y + h * 0.20), tip)
        ear.quadTo(QPointF(cx + side * w * 0.46, y + h * 0.22), QPointF(base_out, y + h * 0.52))
        ear.closeSubpath()
        path = path.united(ear)
    return path


def draw_cat(painter, r):
    """Мордочка чёрного кота в квадрате r: неоновый контур, как у ключа, и горящие глаза-щёлочки."""
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    head = _head_path(r)
    for width, alpha in ((w * 0.10, 40), (w * 0.06, 70), (w * 0.03, 140)):  # неоновое свечение
        painter.setPen(QPen(theme._with_alpha(theme.ACC, alpha), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(head)
    fur = QLinearGradient(x, y, x, y + h)
    fur.setColorAt(0, QColor(FUR[0]))
    fur.setColorAt(1, QColor(FUR[1]))
    painter.setPen(QPen(QColor(FUR[1]).darker(135), max(0.6, w * 0.018)))
    painter.setBrush(fur)
    painter.drawPath(head)
    painter.setPen(Qt.NoPen)
    for side in (-1, 1):  # внутри ушей
        cx = x + w / 2
        ear = QPainterPath()
        ear.moveTo(cx + side * w * 0.14, y + h * 0.34)
        ear.lineTo(cx + side * w * 0.36, y + h * 0.13)
        ear.lineTo(cx + side * w * 0.39, y + h * 0.42)
        ear.closeSubpath()
        painter.setBrush(QColor(EAR))
        painter.drawPath(ear)
    for side in (-1, 1):  # глаза: свечение, радужка, зрачок-щёлочка
        ex, ey = x + w * (0.5 + side * 0.17), y + h * 0.56
        glow = QRadialGradient(QPointF(ex, ey), w * 0.13)
        glow.setColorAt(0, theme._with_alpha(EYES, 160))
        glow.setColorAt(1, theme._with_alpha(EYES, 0))
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(ex, ey), w * 0.13, w * 0.13)
        painter.setBrush(QColor(EYES))
        painter.drawEllipse(QPointF(ex, ey), w * 0.075, h * 0.07)
        painter.setBrush(QColor("#050505"))
        painter.drawEllipse(QPointF(ex, ey), w * 0.016, h * 0.060)
    nose = QPainterPath()
    nx, ny = x + w * 0.5, y + h * 0.68
    nose.moveTo(nx - w * 0.04, ny - h * 0.02)
    nose.lineTo(nx + w * 0.04, ny - h * 0.02)
    nose.lineTo(nx, ny + h * 0.025)
    nose.closeSubpath()
    painter.setBrush(QColor(NOSE))
    painter.drawPath(nose)
    line = QColor(EYES)  # рот и усы — цветом глаз: на чёрной шерсти иначе не видно
    painter.setPen(QPen(line, max(0.7, w * 0.022), Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush)
    mouth = QPainterPath()
    mouth.moveTo(nx - w * 0.08, ny + h * 0.05)
    mouth.quadTo(QPointF(nx - w * 0.04, ny + h * 0.09), QPointF(nx, ny + h * 0.03))
    mouth.quadTo(QPointF(nx + w * 0.04, ny + h * 0.09), QPointF(nx + w * 0.08, ny + h * 0.05))
    painter.drawPath(mouth)
    painter.setPen(QPen(theme._with_alpha(line.name(), 170), max(0.5, w * 0.012), Qt.SolidLine, Qt.RoundCap))
    for side in (-1, 1):
        for dy in (-0.03, 0.02, 0.07):
            painter.drawLine(QPointF(nx + side * w * 0.14, ny + h * dy * 0.4),
                             QPointF(nx + side * w * 0.44, ny + h * (dy * 1.6 - 0.01)))
    painter.restore()


def logo(height):
    """Кот вместо ключа. Нарисован, а не эмодзи: 🐈‍⬛ на Mac — маленький серый кот сбоку."""
    pixmap = QPixmap(height * theme._SCALE, height * theme._SCALE)
    pixmap.setDevicePixelRatio(theme._SCALE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    draw_cat(painter, QRectF(height * 0.04, height * 0.04, height * 0.92, height * 0.92))
    painter.end()
    return pixmap


# --- кружки-буквы записей ---

def monogram(text, size=24):
    """Буква записи — голова чёрного кота с ушами, буква цветом глаз."""
    pixmap = QPixmap(size * theme._SCALE, size * theme._SCALE)
    pixmap.setDevicePixelRatio(theme._SCALE)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    fill = QLinearGradient(0, 0, size * 0.35, size)
    fill.setColorAt(0, QColor(theme.LETTER_TOP))
    fill.setColorAt(1, QColor(theme.LETTER_BOTTOM))
    rim = QColor(theme.LETTER_BOTTOM).darker(118) if theme.LIGHT else QColor(theme.ACC)
    pen = QPen(rim, max(0.8, size / 30))
    top = size * 0.22
    for side in (-1, 1):  # уши
        cx = size / 2 + side * size * 0.27
        ear = QPainterPath()
        ear.moveTo(cx - size * 0.20, top + size * 0.14)
        ear.lineTo(cx + side * size * 0.03, 0.4)
        ear.lineTo(cx + size * 0.20, top + size * 0.14)
        ear.closeSubpath()
        p.setPen(pen)
        p.setBrush(fill)
        p.drawPath(ear)
    body = QRectF(0.5, top, size - 1, size - top - 0.5)
    p.setPen(pen)
    p.setBrush(fill)
    p.drawEllipse(body)
    font = QFont(theme.FONT_FAMILY)
    font.setPixelSize(int(size * 0.48))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor(theme.LETTER_INK))
    p.drawText(body, Qt.AlignCenter, (text.strip() or "?")[0].upper())
    p.end()
    return pixmap


# --- переход ---

class Reveal(QWidget):
    """В середине окна открывается кошачий глаз: узкий зрачок-щёлочка расширяется на всё окно.
    Снаружи зрачка — снимок окна в старых цветах, внутри — уже новые. Как и прежняя волна,
    отдаёт animation, DURATION и done (MainWindow._toggle_egg, _end_wave)."""
    done = Signal()
    DURATION = 1200

    def __init__(self, window, snapshot):
        super().__init__(window)
        self.snapshot = snapshot
        self.setGeometry(window.rect())
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.progress = 0.0
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(self.DURATION)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.valueChanged.connect(self._advance)
        self.animation.finished.connect(self._finish)
        self.show()
        self.raise_()
        self.animation.start()

    def _advance(self, value):
        self.progress = value
        self.update()

    def _finish(self):
        self.hide()
        self.done.emit()
        self.deleteLater()

    def _pupil(self):
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        big = math.hypot(w, h) * 0.56
        p = self.progress
        tall = big * min(1.0, p / 0.35)
        wide = 3 + (big - 3) * max(0.0, (p - 0.25) / 0.75) ** 1.6
        path = QPainterPath()  # миндалина: острая сверху и снизу, пока узкая
        path.moveTo(cx, cy - tall)
        path.cubicTo(cx + wide * 1.33, cy - tall * 0.55, cx + wide * 1.33, cy + tall * 0.55, cx, cy + tall)
        path.cubicTo(cx - wide * 1.33, cy + tall * 0.55, cx - wide * 1.33, cy - tall * 0.55, cx, cy - tall)
        return path

    def paintEvent(self, event):
        if self.progress >= 0.999:
            return  # зрачок раскрылся: старого снимка больше нет
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        whole = QPainterPath()
        whole.addRect(QRectF(self.rect()).adjusted(-2, -2, 2, 2))
        pupil = self._pupil()
        painter.setClipPath(whole.subtracted(pupil))
        painter.drawPixmap(0, 0, self.snapshot)
        painter.setClipping(False)
        painter.setBrush(Qt.NoBrush)
        for width, alpha in ((14, 40), (7, 90), (2.5, 255)):  # светящаяся кромка зрачка
            painter.setPen(QPen(theme._with_alpha(theme.NEON, alpha), width))
            painter.drawPath(pupil)
        painter.end()


# --- кот выглядывает снизу ---

class PeekingCat(QWidget):
    """Чёрный кот выглядывает из-под нижнего края окна: видны уши, глаза и лапки на краю."""

    def __init__(self, window):
        super().__init__(window)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.resize(76, 40)

    def place(self):
        window = self.parentWidget()
        self.move(window.width() - 240, window.height() - self.height())
        self.raise_()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        draw_cat(p, QRectF(12, 3, 52, 52))  # низ головы — за краем окна
        for side in (-1, 1):  # лапки на краю
            p.setPen(QPen(QColor(theme.ACC), 1.1))
            p.setBrush(QColor("#111318"))
            p.drawEllipse(QPointF(38 + side * 21, 38), 9, 5.5)
        p.end()


def decorate(window):
    """Показывает или прячет выглядывающего кота (MainWindow._recolor и resizeEvent)."""
    peek = getattr(window, "_peeking_cat", None)
    if theme.egg and peek is None:
        peek = window._peeking_cat = PeekingCat(window)
    if peek is not None:
        peek.setVisible(theme.egg)
        if theme.egg:
            peek.place()
            peek.update()
