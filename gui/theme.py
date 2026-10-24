"""Оформление в стиле chat.eblo.id + неон: почти чёрный фон с фиолетовым
заревом, лавандовый акцент, светящиеся заголовок, рамки и кнопки, шрифт Inter.

Цвета взяты из CSS-переменных сайта (--bg, --surf, --acc и т.д.);
лавандовые оттенки сдвинуты на 15° к розовому (по просьбе).
Ступенчатые «пиксельные» углы сайт делает через clip-path браузера —
в Qt такого нет, поэтому углы прямые, с тонкой рамкой.
"""

from pathlib import Path

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QAbstractSpinBox, QGraphicsDropShadowEffect, QLineEdit

FONT_FILE = Path(__file__).parent / "fonts" / "InterVariable.ttf"  # лицензия OFL — fonts/LICENSE.txt
# в оформлении Qt путь пишется через «/» даже на Windows
CHECK_FILE = (Path(__file__).parent / "assets" / "check.svg").as_posix()
ICON_FILE = Path(__file__).parent / "assets" / "icon.png"

# --- цвета (имена — как переменные на сайте) ---
BG = "#0a0a0c"         # фон окна
SURF = "#0f0f12"       # панели
WELL = "#0b0b0d"       # «углубления»: поля ввода, шапка таблицы
LINE = "#1f1e24"       # тонкие линии
LINE2 = "#2c2b32"      # рамки панелей
LINE3 = "#5b5a66"      # рамка при наведении
TEXT = "#ecebf1"
MUTED = "#a29fae"
FAINT = "#6f6c7a"
ACC = "#caa7f0"        # лавандовый акцент
ACC_DEEP = "#936fc4"
ACC_LIGHT = "#e4cffd"
ACC_FILL = "#312442"   # заливка акцентных кнопок и выделения
ACC_HOVER = "#482f66"
NEON = "#ddaaf9"       # «неон» — цвет логотипа на сайте, для свечения
RAISED = "#1c1b21"     # обычные кнопки
RAISED_RIM = "#3d3c45"
TIP = "#1d1c22"        # меню и подсказки
TIP_RIM = "#4a4952"
OK = "#3fb950"
WARN = "#e0b64a"
BAD = "#f24d5c"
BAD_INK = "#ff8a95"
BAD_FILL = "#261a1d"
BAD_RIM = "#7d3d46"

STYLE = f"""
QWidget {{ color: {TEXT}; font-size: 13px; }}
/* фиолетовое зарево сверху окна — как неоновая подсветка */
QMainWindow, QDialog, QWidget[role="backdrop"] {{
    background: qradialgradient(cx:0.5, cy:-0.15, radius:1.1, fx:0.5, fy:-0.15,
                                stop:0 #381f52, stop:0.45 #170f20, stop:1 {BG}); }}
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: 28px; font-weight: 800; color: {NEON}; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="error"] {{ color: {BAD_INK}; }}
QLabel[role="accent"] {{ color: {ACC}; font-weight: 600; }}

QFrame[role="card"] {{ background: {SURF}; border: 1px solid {ACC_DEEP}; }}
QFrame[role="card"] QLabel, QFrame[role="card"] QCheckBox {{ background: transparent; }}

QLineEdit, QSpinBox {{
    background: {WELL}; border: 1px solid {LINE}; padding: 7px 10px;
    selection-background-color: {ACC_DEEP}; }}
QLineEdit:focus, QSpinBox:focus {{ border-color: {ACC}; }}

QPushButton {{
    background: {RAISED}; border: 1px solid {RAISED_RIM}; padding: 7px 16px;
    font-weight: 600; }}
QPushButton:hover {{ border-color: {LINE3}; }}
QPushButton:pressed {{ background: {WELL}; }}
QPushButton:disabled {{ color: {FAINT}; border-color: {LINE}; }}
QPushButton[kind="primary"] {{ background: {ACC_FILL}; border-color: {ACC}; color: {ACC_LIGHT}; }}
QPushButton[kind="primary"]:hover {{ background: {ACC_HOVER}; border-color: {NEON}; color: #ffffff; }}
QPushButton[kind="danger"] {{ background: {BAD_FILL}; border-color: {BAD_RIM}; color: {BAD_INK}; }}

QToolButton {{ background: {RAISED}; border: 1px solid {RAISED_RIM}; padding: 5px 8px; }}
QToolButton:hover {{ border-color: {LINE3}; }}
QToolButton:checked {{ background: {ACC_FILL}; border-color: {ACC_DEEP}; }}

QComboBox {{ background: {RAISED}; border: 1px solid {RAISED_RIM}; padding: 5px 10px; }}
QComboBox:hover {{ border-color: {LINE3}; }}
QComboBox QAbstractItemView {{
    background: {TIP}; border: 1px solid {TIP_RIM};
    selection-background-color: {ACC_FILL}; selection-color: {ACC_LIGHT}; }}

QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {RAISED_RIM}; background: {WELL}; }}
QCheckBox::indicator:hover {{ border-color: {ACC}; }}
/* отмечено — светящаяся галочка (assets/check.svg), а не залитый квадрат */
QCheckBox::indicator:checked {{ background: {ACC_FILL}; border-color: {ACC}; image: url("{CHECK_FILE}"); }}

QTableWidget {{
    background: {SURF}; border: none; gridline-color: {LINE};
    selection-background-color: {ACC_FILL}; selection-color: {TEXT}; outline: 0; }}
QTableWidget::item {{ padding: 6px 10px; }}
/* ровная подсветка: градиент в Qt рисуется заново в каждой ячейке — строка выглядела бы полосатой */
QTableWidget::item:selected {{ background: {ACC_HOVER}; color: #ffffff; }}
QHeaderView::section {{
    background: {WELL}; color: {MUTED}; border: none;
    border-bottom: 1px solid {ACC_DEEP}; border-right: 1px solid {LINE};
    padding: 8px 10px; font-size: 12px; font-weight: 600; }}

QMenu {{ background: {TIP}; border: 1px solid {ACC_DEEP}; padding: 4px; }}
QMenu::item {{ padding: 7px 22px 7px 14px; }}
QMenu::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACC_HOVER}, stop:1 {ACC_FILL});
    color: #ffffff; }}
QMenu::separator {{ height: 1px; background: {TIP_RIM}; margin: 4px 6px; }}

QStatusBar {{ background: transparent; color: {MUTED}; border-top: 1px solid {LINE}; }}
QToolTip {{ background: {TIP}; color: {TEXT}; border: 1px solid {TIP_RIM}; padding: 4px 6px; }}

QScrollBar:vertical {{ background: {SURF}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {RAISED_RIM}; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""


def apply(app):
    """Включает оформление для всего приложения."""
    families = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(FONT_FILE)))
    font = QFont(families[0] if families else "Inter Variable")
    font.setPointSize(13)
    app.setFont(font)
    # Fusion — простой стиль Qt, который послушно перекрашивается;
    # родной стиль macOS игнорирует часть настроек оформления
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in [(QPalette.Window, BG), (QPalette.Base, WELL), (QPalette.AlternateBase, SURF),
                        (QPalette.Text, TEXT), (QPalette.WindowText, TEXT), (QPalette.ButtonText, TEXT),
                        (QPalette.Button, RAISED), (QPalette.PlaceholderText, FAINT),
                        (QPalette.Highlight, ACC_FILL), (QPalette.HighlightedText, TEXT),
                        (QPalette.ToolTipBase, TIP), (QPalette.ToolTipText, TEXT), (QPalette.Mid, LINE2)]:
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)
    global _focus_glow
    _focus_glow = _FocusGlow()  # держим ссылку, иначе Python удалит фильтр
    app.installEventFilter(_focus_glow)


def glow(widget, color=ACC, radius=24, alpha=170):
    """Неоновое свечение вокруг элемента (размытая тень без смещения).

    В оформлении Qt (QSS) нет box-shadow, поэтому свечение — отдельный эффект.
    У одного элемента может быть только один такой эффект.
    """
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(radius)
    effect.setOffset(0, 0)
    light = QColor(color)
    light.setAlpha(alpha)
    effect.setColor(light)
    widget.setGraphicsEffect(effect)
    return widget


def neon_card(card):
    """Карточка с неоновым ореолом вокруг рамки."""
    return glow(card, ACC_DEEP, radius=48, alpha=150)


def neon_title(label):
    """Заголовок, светящийся как неоновая вывеска."""
    return glow(label, NEON, radius=22, alpha=210)


class _FocusGlow(QObject):
    """Поле ввода загорается, когда в нём курсор, и гаснет, когда курсор уходит."""

    def eventFilter(self, obj, event):
        if isinstance(obj, (QLineEdit, QAbstractSpinBox)):
            if event.type() == QEvent.FocusIn:
                glow(obj, ACC, radius=18, alpha=150)
            elif event.type() == QEvent.FocusOut:
                obj.setGraphicsEffect(None)
        return False  # событие идёт дальше как обычно


_focus_glow = None


def role(widget, name):
    """Помечает элемент для оформления: role(label, "muted") — серый текст и т.п."""
    widget.setProperty("role", name)
    return widget


def kind(button, name):
    """Вид кнопки: "primary" — лавандовая главная (светится), "danger" — красная."""
    button.setProperty("kind", name)
    if name == "primary":
        glow(button, ACC, radius=20, alpha=140)
    return button
