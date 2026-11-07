"""Оформление: почти чёрный фон с фиолетовым заревом, лавандовый неон и
«стекло» в духе Liquid Glass, моноширинный шрифт MesloLGS Nerd Font.

Цвета взяты из CSS-переменных chat.eblo.id (--bg, --surf, --acc и т.д.);
лавандовые оттенки сдвинуты на 15° к розовому (по просьбе).
Стекло: полупрозрачные панели, кнопки и поля со скруглёнными углами и светлой
кромкой сверху — сквозь них видно зарево фона. Настоящее Liquid Glass (с
размытием и преломлением того, что под ним) macOS рисует только для своих
родных элементов, в Qt его нет — поэтому стекло нарисовано прозрачностью.
"""

import html
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QCursor, QFont, QFontDatabase, QGradient, QIcon, QLinearGradient, QPainter, QPainterPath,
                           QPalette, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QDialog, QFrame, QGraphicsDropShadowEffect, QLabel, QLineEdit,
                               QMainWindow, QPushButton, QToolButton, QWidget)
from shiboken6 import isValid  # жив ли ещё объект Qt за питоновской обёрткой

# лицензия Apache 2.0 — fonts/LICENSE.txt; обычное начертание и жирное (для кнопок и заголовков)
FONT_FILE = Path(__file__).parent / "fonts" / "MesloLGSNerdFont-Regular.ttf"
FONT_BOLD_FILE = Path(__file__).parent / "fonts" / "MesloLGSNerdFont-Bold.ttf"
# у Mac экран Retina (на точку шрифта — 4 пикселя), на обычном экране Windows
# тот же размер выглядит мельче — поэтому там на единицу крупнее
FONT_SIZE = 14 if sys.platform == "win32" else 13
FONT_FAMILY = "MesloLGS Nerd Font"
# в оформлении Qt путь пишется через «/» даже на Windows
CHECK_FILE = (Path(__file__).parent / "assets" / "check.svg").as_posix()
ARROW_FILE = (Path(__file__).parent / "assets" / "arrow.svg").as_posix()
ARROW_UP_FILE = (Path(__file__).parent / "assets" / "arrow_up.svg").as_posix()
EYE_FILE = str(Path(__file__).parent / "assets" / "eye.svg")
EYE_OFF_FILE = str(Path(__file__).parent / "assets" / "eye_off.svg")
# иконка окна: на Windows — .ico без полей macOS (с полями на панели задач она мельче соседних)
ICON_FILE = Path(__file__).parent / "assets" / ("WhoKey.ico" if sys.platform == "win32" else "icon.png")

# --- цвета: палитра логотипа (пиксельный неоновый ключ на тёмно-синей плитке) ---
# Ключ переливается от голубовато-лавандового (верх) к фуксии (низ) — это ACC и MAGENTA;
# фон — тёмный индиго, как плитка иконки. Те же цвета — в расширении (extension/*.css)
BG = "#07061a"         # фон окна — тёмный индиго
SURF = "#0c0a22"       # панели
WELL = "#08071a"       # «углубления»: поля ввода, шапка таблицы
LINE = "#1d1a3c"       # тонкие линии
LINE2 = "#2b2752"      # рамки панелей
TEXT = "#eeeaff"
MUTED = "#a4a0c8"
FAINT = "#6c6896"
ACC = "#a890f0"        # голубовато-лавандовый — верх ключа
ACC_DEEP = "#6f55d8"
ACC_LIGHT = "#d9ccff"
ACC_FILL = "#261d5c"   # заливка акцентных кнопок и выделения
MAGENTA = "#f048f0"    # фуксия — низ ключа
NEON = "#f05cf0"       # «неон»: заголовок, свечение
RAISED = "#17153a"     # обычные кнопки
TIP = "#16143a"        # меню и подсказки
TIP_RIM = "#3e3a6e"
OK = "#3fb950"
WARN = "#e0b64a"
BAD = "#f24d5c"
BAD_INK = "#ff8a95"
GLOW_1, GLOW_2, GLOW_3 = "#3a1a9a", "#2a0f5a", "#120a30"  # зарево сверху окна
TITLE_START = "#c9b8ff"  # начало перелива в заголовке
LETTER_TOP, LETTER_BOTTOM, LETTER_INK = "#e6dcff", "#c38cf2", "#1a1036"  # кружки-буквы записей

# Пасхалка: три нажатия на ключ в главном окне (см. MainWindow._logo_clicked).
# Коричневый фон, жёлтый неон и оранжевый оттенок вместо фуксии. Только на время сеанса.
_EGG_COLORS = {
    "BG": "#140a03", "SURF": "#1e1006", "WELL": "#120903", "LINE": "#33200f", "LINE2": "#4a2f16",
    "TEXT": "#fff6d6", "MUTED": "#c9b27a", "FAINT": "#8f7a4c",
    "ACC": "#ffe600", "ACC_DEEP": "#a86a00", "ACC_LIGHT": "#fff59a", "ACC_FILL": "#4a3800",
    "MAGENTA": "#ff9a00", "NEON": "#ffea00", "RAISED": "#2a1809", "TIP": "#24140a", "TIP_RIM": "#5a3c1c",
    "GLOW_1": "#6b3a12", "GLOW_2": "#4a2509", "GLOW_3": "#241206", "TITLE_START": "#fff59a",
    "LETTER_TOP": "#fff3a0", "LETTER_BOTTOM": "#ffb52e", "LETTER_INK": "#2a1605",
}
_USUAL_COLORS = {name: globals()[name] for name in _EGG_COLORS}



def rgba(color, alpha):
    """Цвет с прозрачностью для оформления Qt: rgba("#caa7f0", 80). alpha — от 0 до 255."""
    color = color.lstrip("#")
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def solid(color, alpha, over="#16123a"):
    """Непрозрачный цвет, который выглядит как color с прозрачностью alpha поверх фона over.

    Для рамок: скруглённую рамку Qt рисует по кусочкам (стороны и дуги углов
    отдельно), и у полупрозрачной рамки на стыках кусочки накладываются —
    получаются светлые точки в углах. Непрозрачная рамка стыков не показывает.
    over — средний цвет фона окна под стеклом.
    """
    color, over = color.lstrip("#"), over.lstrip("#")
    mix = [round(int(over[i:i + 2], 16) + (int(color[i:i + 2], 16) - int(over[i:i + 2], 16)) * alpha / 255)
           for i in (0, 2, 4)]
    return "#" + "".join(f"{c:02x}" for c in mix)


WHITE = "#ffffff"
# --- стекло ---
CARD_RADIUS = 22    # большие панели
BUTTON_RADIUS = 12  # кнопки
FIELD_RADIUS = 10   # поля ввода


def glass(top, middle, bottom):
    """Заливка стекла: светлее сверху (блик, как от света сверху) и плавно темнее вниз.

    Блик — внутри заливки, а не отдельной светлой кромкой: кромка другого цвета
    стыковалась бы с боковыми по диагонали в углах — резкий переход.
    """
    return (f"qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            f"stop:0 {top}, stop:0.45 {middle}, stop:1 {bottom})")


def _derive_colors():
    global GLASS, GLASS_HOVER, GLASS_PANEL, GLASS_ACC, GLASS_ACC_HOVER, GLASS_BAD, RIM, RIM_HOVER, RIM_ACC, RIM_CARD, HOLLOW
    GLASS = glass(rgba(WHITE, 52), rgba(WHITE, 24), rgba(WHITE, 12))
    GLASS_HOVER = glass(rgba(WHITE, 72), rgba(WHITE, 36), rgba(WHITE, 20))
    GLASS_PANEL = glass(rgba(WHITE, 24), rgba(WHITE, 10), rgba(WHITE, 4))
    # главные кнопки переливаются как ключ: лавандовый сверху, фуксия снизу
    GLASS_ACC = glass(rgba(ACC_LIGHT, 150), rgba(ACC, 120), rgba(MAGENTA, 120))
    GLASS_ACC_HOVER = glass(rgba(ACC_LIGHT, 190), rgba(ACC, 160), rgba(MAGENTA, 160))
    GLASS_BAD = glass(rgba(BAD, 90), rgba(BAD, 50), rgba(BAD, 28))
    RIM = solid(WHITE, 40)       # кромка стекла
    RIM_HOVER = solid(WHITE, 75)
    RIM_ACC = solid(ACC_LIGHT, 150)
    RIM_CARD = solid(MAGENTA, 130)  # рамка больших панелей — в цвет фуксии
    HOLLOW = rgba("#000000", 95) # «углубление» поля ввода


_derive_colors()


def _style():
    return f"""
/* шрифт — здесь, а не только через app.setFont: на macOS Qt ставит кнопкам, подписям
   и таблице системный шрифт отдельно, и общий шрифт приложения до них не доходил */
QWidget {{ color: {TEXT}; font-family: "{FONT_FAMILY}"; font-size: {FONT_SIZE}px; }}
/* фиолетовое зарево сверху окна — как неоновая подсветка; его видно сквозь стекло */
QMainWindow, QDialog, QWidget[role="backdrop"] {{
    background: qradialgradient(cx:0.5, cy:-0.15, radius:1.1, fx:0.5, fy:-0.15,
                                stop:0 {GLOW_1}, stop:0.30 {GLOW_2}, stop:0.6 {GLOW_3}, stop:1 {BG}); }}
QLabel {{ background: transparent; }}
/* заголовок «WhoKey» — переливом, как ключ на логотипе */
QLabel[role="title"] {{ font-size: {FONT_SIZE * 2 + 2}px; font-weight: 800;
    color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {TITLE_START}, stop:1 {NEON}); }}
QLabel[role="heading"] {{ font-size: {FONT_SIZE + 3}px; font-weight: 800; color: {ACC_LIGHT}; }}
QLabel[role="faint"] {{ color: {FAINT}; font-size: {FONT_SIZE - 1}px; }}
/* плашка: имя файла хранилища, «Подключено» */
QLabel[role="chip"] {{ color: {ACC}; background: {rgba(ACC, 40)}; border: 1px solid {solid(ACC, 110)};
    border-radius: 9px; padding: 2px 9px; font-size: {FONT_SIZE - 1}px; font-weight: 600; }}
QLabel[role="chip_off"] {{ color: {MUTED}; background: {rgba(WHITE, 14)}; border: 1px solid {solid(WHITE, 50)};
    border-radius: 9px; padding: 2px 9px; font-size: {FONT_SIZE - 1}px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="error"] {{ color: {BAD_INK}; }}
QLabel[role="accent"] {{ color: {ACC}; font-weight: 600; }}

QFrame[role="card"] {{
    background: {GLASS_PANEL}; border: 1px solid {RIM_CARD}; border-radius: {CARD_RADIUS}px; }}
QFrame[role="card"] QLabel, QFrame[role="card"] QCheckBox {{ background: transparent; }}

QLineEdit, QSpinBox, QPlainTextEdit {{
    background: {HOLLOW}; border: 1px solid {RIM}; border-radius: {FIELD_RADIUS}px;
    padding: 7px 10px; selection-background-color: {ACC_DEEP}; }}
QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {ACC}; }}
/* поле с ошибкой (mark_invalid) — красная рамка, чтобы было видно, что исправить */
QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"] {{ border-color: {BAD_INK}; }}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; background: transparent; width: 18px; }}
QSpinBox::up-arrow {{ image: url("{ARROW_UP_FILE}"); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url("{ARROW_FILE}"); width: 10px; height: 10px; }}

QPushButton {{
    background: {GLASS}; border: 1px solid {RIM};
    border-radius: {BUTTON_RADIUS}px; padding: 7px 16px; font-weight: 600; }}
QPushButton:hover {{ background: {GLASS_HOVER}; border-color: {RIM_HOVER}; }}
QPushButton:disabled {{ color: {FAINT}; background: {rgba(WHITE, 8)}; border-color: {solid(WHITE, 20)}; }}
QPushButton[kind="primary"] {{
    background: {GLASS_ACC}; border-color: {RIM_ACC}; color: {WHITE}; }}
QPushButton[kind="primary"]:hover {{ background: {GLASS_ACC_HOVER}; border-color: {NEON}; }}
QPushButton[kind="danger"] {{ background: {GLASS_BAD}; border-color: {solid(BAD_INK, 110)}; color: {BAD_INK}; }}
/* на чём стоит фокус с клавиатуры (Tab) — видно по лавандовой рамке */
QPushButton:focus, QToolButton:focus, QComboBox:focus {{ border: 2px solid {ACC}; }}
QLineEdit QToolButton:focus {{ border: none; }}
/* нажатие: кнопка «проминается» — стекло становится впадиной, загорается рамка,
   текст опускается на точку. Правила — после фокуса, чтобы при нажатии побеждали они */
QPushButton:pressed, QToolButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {rgba("#000000", 120)}, stop:1 {rgba(ACC, 45)});
    border-color: {ACC}; padding-top: 8px; padding-bottom: 6px; }}
QPushButton[kind="primary"]:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {rgba(MAGENTA, 170)}, stop:1 {rgba(ACC_DEEP, 150)});
    border-color: {NEON}; }}
QPushButton[kind="danger"]:pressed {{ background: {rgba(BAD, 110)}; border-color: {BAD_INK}; }}

QToolButton {{
    background: {GLASS}; border: 1px solid {RIM};
    border-radius: {BUTTON_RADIUS}px; padding: 5px 8px; }}
QToolButton:hover {{ background: {GLASS_HOVER}; border-color: {RIM_HOVER}; }}
/* нажатый «глаз»: лёгкая лавандовая подложка — на яркой неоновый значок не читался бы */
QToolButton:checked {{ background: {rgba(ACC, 40)}; border-color: {RIM_ACC}; }}
/* крестик «очистить» внутри поля поиска — тоже QToolButton; без этого стекло
   с отступами сжимало его значок до нуля и крестик пропадал */
QLineEdit QToolButton {{ background: transparent; border: none; padding: 0; }}

QComboBox {{
    background: {GLASS}; border: 1px solid {RIM};
    border-radius: {BUTTON_RADIUS}px; padding: 5px 10px; }}
QComboBox:hover {{ background: {GLASS_HOVER}; border-color: {RIM_HOVER}; }}
/* без этого плашка под стрелкой остаётся квадратной и вылезает за скругление */
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url("{ARROW_FILE}"); width: 12px; height: 12px; }}
/* выпадающий список — как меню правого клика (окно скругляет rounded_popup) */
QComboBoxPrivateContainer {{ background: transparent; border: none; }}
QComboBox QAbstractItemView {{
    background: {TIP}; border: 1px solid {solid(ACC, 130, TIP)}; border-radius: 12px;
    padding: 6px; outline: 0; }}
QComboBox QAbstractItemView::item {{ padding: 7px 14px; border-radius: 8px; min-height: 18px; }}
QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover {{
    background: {solid(ACC, 80, TIP)}; color: {WHITE}; }}

QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border: 1px solid {solid(WHITE, 60)}; border-radius: 5px; background: {HOLLOW}; }}
QCheckBox::indicator:hover {{ border-color: {ACC}; }}
QCheckBox:focus {{ color: {ACC_LIGHT}; }}
QCheckBox::indicator:focus {{ border: 2px solid {ACC}; }}
/* отмечено — светящаяся галочка (assets/check.svg), а не залитый квадрат */
QCheckBox::indicator:checked {{ background: {rgba(ACC, 70)}; border-color: {ACC}; image: url("{CHECK_FILE}"); }}

/* таблица прозрачная — лежит прямо на стеклянной карточке */
QTableWidget {{
    background: transparent; border: none; gridline-color: {LINE};
    selection-background-color: transparent; selection-color: {TEXT}; outline: 0; }}
QTableWidget::item {{ padding: 6px 10px; }}
/* выделенную строку рисует widgets.RoundedRowDelegate — одной скруглённой плашкой */
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: transparent; color: {MUTED}; border: none;
    border-bottom: 1px solid {rgba(ACC, 90)};
    padding: 8px 10px; font-size: {FONT_SIZE - 1}px; font-weight: 600; }}

/* меню скруглено (см. rounded_menu) и непрозрачно: размытия под ним нет,
   и сквозь прозрачное меню читался бы текст таблицы */
/* строка меню (на Windows — внутри окна): прозрачная, пункты — скруглённой плашкой */
QMenuBar {{ background: transparent; }}
QMenuBar::item {{ background: transparent; padding: 4px 10px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: {solid(ACC, 80, TIP)}; }}
QMenu {{ background: {TIP}; border: 1px solid {solid(ACC, 130, TIP)}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px 7px 14px; border-radius: 8px; }}
QMenu::item:selected {{ background: {solid(ACC, 80, TIP)}; color: {WHITE}; }}
QMenu::item:disabled {{ color: {FAINT}; }}
QMenu::separator {{ height: 1px; background: {TIP_RIM}; margin: 4px 6px; }}

QStatusBar {{ background: transparent; color: {MUTED}; }}
QStatusBar::item {{ border: none; }}
QToolTip {{ background: {TIP}; color: {TEXT}; border: 1px solid {TIP_RIM}; padding: 4px 6px; }}

QProgressBar {{ background: {HOLLOW}; border: 1px solid {RIM}; border-radius: 4px; }}
QProgressBar::chunk {{ border-radius: 3px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {rgba(WHITE, 50)}; min-height: 24px; border-radius: 3px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""


STYLE = _style()


def apply(app):
    """Включает оформление для всего приложения."""
    QFontDatabase.addApplicationFont(str(FONT_BOLD_FILE))
    families = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(FONT_FILE)))
    font = QFont(families[0] if families else FONT_FAMILY)
    font.setPixelSize(FONT_SIZE)
    app.setFont(font)
    # Fusion — простой стиль Qt, который послушно перекрашивается;
    # родной стиль macOS игнорирует часть настроек оформления
    app.setStyle("Fusion")
    _apply_colors(app)
    # тёмная рамка окна и на Windows в светлой теме (иначе белая полоса над тёмным окном)
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    except AttributeError:  # Qt старше 6.8
        pass
    global _focus_glow
    _focus_glow = _FocusGlow()  # держим ссылку, иначе Python удалит фильтр
    app.installEventFilter(_focus_glow)


def _apply_colors(app):
    palette = QPalette()
    for role, color in [(QPalette.Window, BG), (QPalette.Base, WELL), (QPalette.AlternateBase, SURF),
                        (QPalette.Text, TEXT), (QPalette.WindowText, TEXT), (QPalette.ButtonText, TEXT),
                        (QPalette.Button, RAISED), (QPalette.PlaceholderText, FAINT),
                        (QPalette.Highlight, ACC_FILL), (QPalette.HighlightedText, TEXT),
                        (QPalette.ToolTipBase, TIP), (QPalette.ToolTipText, TEXT), (QPalette.Mid, LINE2),
                        # ссылки — неоновые, а не стандартные синие
                        (QPalette.Link, NEON), (QPalette.LinkVisited, NEON)]:
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(STYLE + (
        # на Mac кнопки окон в системном порядке: «Отмена» слева, главное действие справа
        "QDialogButtonBox { button-layout: 1; }" if sys.platform == "darwin" else
        # на Linux Qt добавляет на кнопки значки системной темы, которые не подходят к оформлению
        "QDialogButtonBox { dialogbuttonbox-buttons-have-icons: 0; }" if sys.platform.startswith("linux") else ""))


egg = False  # включена ли пасхалка


def set_egg(on):
    """Включает или выключает палитру пасхалки во всём приложении. Открытые окна перекрашиваются сами;
    то, что нарисовано заранее (значки, логотип), главное окно обновляет в MainWindow._recolor."""
    global egg, STYLE
    if on == egg:
        return
    egg = on
    globals().update(_EGG_COLORS if on else _USUAL_COLORS)
    _derive_colors()
    STYLE = _style()
    _SCENES.clear()
    app = QApplication.instance()
    if app is None:
        return
    _apply_colors(app)
    for widget in app.allWidgets():  # неоновые свечения заданы цветом заранее
        effect = widget.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            light = QColor(ACC if widget.property("kind") == "primary" else NEON)  # см. kind() и neon_title()
            light.setAlpha(effect.color().alpha())
            effect.setColor(light)
        elif isinstance(widget, Halo):
            widget.recolor()


def _has_color(pixmap):
    """Есть ли на картинке цвет. Без цветного шрифта вместо эмодзи рисуется чёрный значок или пустой квадрат."""
    image = pixmap.toImage()
    step = max(1, image.width() // 40)
    for y in range(0, image.height(), step):
        for x in range(0, image.width(), step):
            color = image.pixelColor(x, y)
            if color.alpha() > 128 and color.hsvSaturation() > 80:
                return True
    return False


def _drawn_poop(height):
    """Какашка своими силами — если в системе нет цветного шрифта эмодзи."""
    pixmap = QPixmap(height * _SCALE, height * _SCALE)
    pixmap.setDevicePixelRatio(_SCALE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    h = height
    fill = QLinearGradient(0, 0, 0, h)
    fill.setColorAt(0, QColor("#a8703a"))
    fill.setColorAt(1, QColor("#6b4120"))
    painter.setBrush(fill)
    painter.drawEllipse(QRectF(h * 0.40, h * 0.04, h * 0.22, h * 0.22))  # кончик
    painter.drawRoundedRect(QRectF(h * 0.28, h * 0.17, h * 0.44, h * 0.24), h * 0.12, h * 0.12)
    painter.drawRoundedRect(QRectF(h * 0.16, h * 0.36, h * 0.68, h * 0.28), h * 0.14, h * 0.14)
    painter.drawRoundedRect(QRectF(h * 0.04, h * 0.60, h * 0.92, h * 0.34), h * 0.17, h * 0.17)
    painter.setBrush(QColor(WHITE))
    for x in (0.31, 0.53):
        painter.drawEllipse(QRectF(h * x, h * 0.40, h * 0.16, h * 0.18))
    painter.setBrush(QColor("#1c1008"))
    for x in (0.36, 0.58):
        painter.drawEllipse(QRectF(h * x, h * 0.45, h * 0.07, h * 0.08))
    painter.setPen(QPen(QColor("#1c1008"), max(1.0, h * 0.04), Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush)
    painter.drawArc(QRectF(h * 0.32, h * 0.60, h * 0.36, h * 0.20), 200 * 16, 140 * 16)  # улыбка
    painter.end()
    return pixmap


def _poop_pixmap(height):
    """Эмодзи вместо ключа. Цветной шрифт эмодзи есть почти в каждой системе, картинка в программу не встроена."""
    side = height * _SCALE
    pixmap = QPixmap(side, side)
    pixmap.setDevicePixelRatio(_SCALE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    font = QFont()
    font.setFamilies(["Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji"])
    font.setPixelSize(int(height * 0.85))
    painter.setFont(font)
    painter.drawText(QRectF(0, 0, height, height), Qt.AlignCenter, "\U0001F4A9")
    painter.end()
    return pixmap if _has_color(pixmap) else _drawn_poop(height)


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
    """Карточка с неоновым ореолом вокруг рамки (слой Halo, см. _FocusGlow)."""
    card.setProperty("neon", True)
    return card


def neon_title(label):
    """Заголовок, светящийся как неоновая вывеска."""
    return glow(label, NEON, radius=22, alpha=210)


class Halo(QWidget):
    """Неоновое свечение вокруг элемента — отдельный прозрачный слой, а не эффект Qt.

    Почему не glow(): с эффектом Qt перестаёт рисовать мигающий курсор — и в
    самом поле, и во всех полях внутри элемента с эффектом (так пропал курсор
    в поле мастер-пароля внутри карточки). А карточка с эффектом при частичной
    перерисовке (выделили строку таблицы) рисовала свечение кусками.

    Рисуются только кольца снаружи элемента: элементы полупрозрачные, и
    свечение под ними просвечивало бы. on_top=False — слой под элементом,
    среди его соседей (для карточек); on_top=True — слой поверх всего окна,
    чтобы свечение поля не обрезалось рамками контейнера, где лежит поле.
    """

    def __init__(self, target, color, width, radius, alpha, on_top=False):
        super().__init__(target.window() if on_top else target.parentWidget())
        self.target, self.color, self.width = target, QColor(color), width
        self.radius, self.alpha = radius, alpha
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        _halos.add(self)
        target.destroyed.connect(self._drop)
        # слой могут удалить вместе с окном раньше, чем элемент (так было при
        # закрытии окна входа) — тогда он должен сам уйти из списка, иначе
        # обращение к удалённому слою роняло приложение
        self.destroyed.connect(lambda: _halos.discard(self))
        self.follow()
        if on_top:
            self.raise_()
        else:
            self.stackUnder(target)

    def _drop(self):
        _halos.discard(self)
        if isValid(self):
            self.hide()  # сразу, не дожидаясь удаления
            self.deleteLater()

    def recolor(self):
        """Палитра сменилась: у карточек один цвет свечения, у полей ввода другой (см. _FocusGlow)."""
        if isValid(self.target):
            self.color = QColor(ACC_DEEP if self.target.property("neon") else ACC)
            self.update()

    def remove(self):
        if isValid(self.target):
            self.target.destroyed.disconnect(self._drop)
        self._drop()

    def follow(self):
        """Встаёт вокруг элемента — вызывается, когда что-то в окне сдвинулось."""
        corner = self.target.mapTo(self.parentWidget(), QPoint(0, 0))
        w = self.width
        self.setGeometry(QRect(corner, self.target.size()).adjusted(-w, -w, w, w))
        self.setVisible(self.target.isVisibleTo(self.parentWidget()))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(self.color)
        for i in range(self.width):  # кольца от внешнего края к элементу — всё ярче
            color.setAlpha(int(self.alpha * ((i + 1) / self.width) ** 2.2))
            p.setPen(QPen(color, 1))
            inset = i + 0.5
            radius = self.radius + self.width - inset
            p.drawRoundedRect(QRectF(self.rect()).adjusted(inset, inset, -inset, -inset), radius, radius)


_halos = set()  # все слои свечения — чтобы двигать их вслед за элементами


class _FocusGlow(QObject):
    """Поле ввода загорается, когда в нём курсор, и гаснет, когда курсор уходит.
    Заодно двигает все слои свечения вслед за их элементами и включает свечение
    карточек, когда карточка появилась на экране."""

    def eventFilter(self, obj, event):
        # Фильтр видит каждое событие приложения. Ошибка здесь шла бы в окошко
        # «непредвиденная ошибка», окошко снова вызывало бы фильтр — ошибка в
        # ошибке, и приложение вылетало. Поэтому свечение может только не
        # нарисоваться: ошибку печатаем и работаем дальше.
        try:
            if event.type() == QEvent.Paint and _paint_glass(obj):
                return True  # нарисовано здесь (см. «жидкое стекло» ниже)
            self._handle(obj, event)
        except Exception:
            traceback.print_exc()
        return False  # событие идёт дальше как обычно; при ошибке рисования — обычный вид из STYLE

    def _handle(self, obj, event):
        kind = event.type()
        if kind == QEvent.HoverMove and _is_glass_button(obj):
            obj.update()  # пятно света идёт за курсором
        if kind in (QEvent.Move, QEvent.Resize, QEvent.Show, QEvent.Hide) \
                and _halos and not isinstance(obj, Halo):
            for halo in list(_halos):
                if isValid(halo) and isValid(halo.target):
                    halo.follow()
                else:  # на всякий случай: удалённый слой просто забываем
                    _halos.discard(halo)
        if kind == QEvent.Show and obj.property("neon") and getattr(obj, "_halo", None) is None:
            # у карточки при создании ещё нет родителя — свечение заводим при показе
            obj._halo = Halo(obj, ACC_DEEP, 16, CARD_RADIUS, 110)
        # нажали кнопку — вокруг неё загорается неон, отпустили — гаснет: нажатие видно сразу
        if isinstance(obj, (QPushButton, QToolButton)) and not isinstance(obj.parentWidget(), QLineEdit):
            pressed = obj.isEnabled() and (kind == QEvent.MouseButtonPress
                                           or (kind == QEvent.KeyPress and event.key() == Qt.Key_Space))
            released = kind in (QEvent.MouseButtonRelease, QEvent.Leave, QEvent.Hide, QEvent.EnabledChange) \
                or (kind == QEvent.KeyRelease and event.key() == Qt.Key_Space)
            flash = getattr(obj, "_press_halo", None)
            if pressed and flash is None:
                obj._press_halo = Halo(obj, NEON, 9, _glass_radius(obj), 170, on_top=True)
            elif released and flash is not None:
                obj._press_halo = None
                QTimer.singleShot(90, lambda: flash.remove() if isValid(flash) else None)  # гаснет не мгновенно
        if kind in (QEvent.FocusIn, QEvent.FocusOut) \
                and isinstance(obj, (QLineEdit, QAbstractSpinBox)) \
                and not isinstance(obj.parentWidget(), QAbstractSpinBox):  # строка внутри поля-числа
            halo = getattr(obj, "_halo", None)
            if halo is not None and not isValid(halo):
                halo = obj._halo = None
            if kind == QEvent.FocusIn and halo is None:
                obj._halo = Halo(obj, ACC, 8, FIELD_RADIUS, 120, on_top=True)
            elif kind == QEvent.FocusOut and halo is not None:
                halo.remove()
                obj._halo = None


def badge(symbol, color=NEON, size=56):
    """Значок для окошек-вопросов: «?» или «!» в неоне на стеклянном круге.

    Стандартный значок Qt на тёмном фоне почти не виден.
    """
    scale = 2  # рисуем вдвое крупнее — на экране Retina края гладкие
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    circle = QRectF(4, 4, size - 8, size - 8)
    fill = QLinearGradient(0, circle.top(), 0, circle.bottom())
    fill.setColorAt(0, QColor(255, 255, 255, 40))
    fill.setColorAt(1, QColor(255, 255, 255, 8))
    p.setBrush(fill)
    p.setPen(QPen(QColor(solid(color, 150)), 1.2))
    p.drawEllipse(circle)
    font = QFont(QApplication.font().family())
    font.setPixelSize(int(size * 0.5))
    font.setWeight(QFont.ExtraBold)
    p.setFont(font)
    light = QColor(color)
    for radius in (3, 2, 1):  # свечение — несколько полупрозрачных копий со сдвигом
        light.setAlpha(70 // radius)
        p.setPen(light)
        for dx, dy in ((-radius, 0), (radius, 0), (0, -radius), (0, radius)):
            p.drawText(circle.translated(dx, dy), Qt.AlignCenter, symbol)
    p.setPen(QColor(color))
    p.drawText(circle, Qt.AlignCenter, symbol)
    p.end()
    return pixmap


_focus_glow = None


def rounded_menu(menu):
    """Меню со скруглёнными углами: без прозрачного окна под ним углы остались бы квадратными."""
    menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WA_TranslucentBackground)
    return menu


def rounded_popup(combo):
    """То же для выпадающего списка: его окошко (контейнер списка) делаем прозрачным."""
    combo.setStyleSheet("QComboBox { combobox-popup: 0; }")  # список под полем, а не поверх него
    popup = combo.view().window()
    popup.setWindowFlags(popup.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    popup.setAttribute(Qt.WA_TranslucentBackground)
    return combo


def plain_tip(text):
    """Всплывающая подсказка с данными записи. Qt сам решает, не HTML ли подсказка, и «<img width=…>»
    из CSV рисовал бы картинкой (как с надписями, см. role) — поэтому текст экранируем."""
    if not text:
        return ""  # у пустой ячейки подсказки нет, а «<qt></qt>» показал бы пустой пузырь
    return "<qt>" + html.escape(text[:500]).replace("\n", "<br>") + "</qt>"


def role(widget, name):
    """Помечает элемент для оформления: role(label, "muted") — серый текст и т.п.

    Надпись заодно становится простым текстом. Иначе Qt сам решает, не HTML ли это,
    и название записи вроде «<img width=60000 …>» (например, из CSV) рисовалось бы
    картинкой — окно раздувалось до гигантских размеров и WhoKey падал (ревью 1.6).
    HTML (ссылки) включают явно: label.setTextFormat(Qt.RichText)."""
    widget.setProperty("role", name)
    if isinstance(widget, QLabel):
        widget.setTextFormat(Qt.PlainText)
    return widget


def kind(button, name):
    """Вид кнопки: "primary" — лавандовая главная (светится), "danger" — красная."""
    button.setProperty("kind", name)
    if name == "primary":
        glow(button, ACC, radius=20, alpha=140)
    return button


def mark_invalid(widget, invalid=True):
    """Красная рамка у поля с ошибкой (и обратно)."""
    widget.setProperty("invalid", invalid)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


# --- значки из шрифта и логотип ---
# В MesloLGS Nerd Font уже есть значки Font Awesome — рисуем их как картинки:
# одинаково на Mac и Windows (в отличие от эмодзи) и без лишних файлов
GLYPHS = {"lock": "\uf023", "search": "\uf002", "cog": "\uf013", "puzzle": "\uf12e", "magic": "\uf0d0",
          "plus": "\uf067", "import": "\uf093", "shield": "\uf132", "clock": "\uf017"}
_SCALE = 3  # рисуем крупнее и уменьшаем — чётко и на Retina


def glyph_pixmap(name, color=ACC, px=14, box=None):
    box = box or px + 4
    pixmap = QPixmap(box * _SCALE, box * _SCALE)
    pixmap.setDevicePixelRatio(_SCALE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    font = QFont(FONT_FAMILY)
    font.setPixelSize(px)
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(QRectF(0, 0, box, box), Qt.AlignCenter, GLYPHS[name])
    painter.end()
    return pixmap


def glyph_icon(name, color=ACC, px=14):
    return QIcon(glyph_pixmap(name, color, px))


KEY_FILE = Path(__file__).parent / "assets" / "key.png"  # ключ с логотипа без плитки (make_key.py)


def logo_pixmap(height):
    """Пиксельный неоновый ключ с логотипа высотой height точек."""
    if egg:
        return _poop_pixmap(height)
    source = QPixmap(str(KEY_FILE))
    if source.isNull():
        return QPixmap()
    pixmap = source.scaledToHeight(height * _SCALE, Qt.SmoothTransformation)
    pixmap.setDevicePixelRatio(_SCALE)
    return pixmap


def monogram(text, size=24):
    """Кружок-буква записи (скруглённый квадрат), как в меню расширения: «G» для github.com."""
    pixmap = QPixmap(size * _SCALE, size * _SCALE)
    pixmap.setDevicePixelRatio(_SCALE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    gradient = QLinearGradient(0, 0, size * 0.35, size)  # цвета ключа: светлый верх, фуксия к низу
    gradient.setColorAt(0, QColor(LETTER_TOP))
    gradient.setColorAt(1, QColor(LETTER_BOTTOM))
    painter.setBrush(gradient)
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.29, size * 0.29)
    font = QFont(FONT_FAMILY)
    font.setPixelSize(int(size * 0.55))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(LETTER_INK))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, (text.strip() or "?")[0].upper())
    painter.end()
    return pixmap


# --- жидкое стекло ---
# Настоящего размытия того, что под элементом, Qt не умеет, а снимок окна при каждой
# перерисовке был бы медленным. Но под кнопками и карточками лежит только фон окна — его
# мы рисуем сами. Поэтому фон с пятнами света считаем один раз на размер окна, храним его
# размытую копию, и каждый стеклянный элемент рисует свой кусочек этой копии, чуть
# увеличенный, как через линзу. Сверху — блик, затемнение снизу и яркая кромка.
_SCENES = {}          # (ширина, высота) -> (фон, размытый фон)
_SCENE_LIMIT = 6      # при растягивании окна размеров много — старые забываем
_BLUR_SCALE = 0.08    # чем меньше копия, тем сильнее размытие при растягивании
_SCENE_MAX = 2048     # длинная сторона картинки фона: в ней только плавные переливы, растяжение незаметно
_LENS = 0.90          # какая доля картинки под стеклом видна: остальное — «увеличение»
# пятна света: x, y, радиус (доли окна), цвет, яркость
def _lights():
    return ((0.14, 0.04, 0.42, ACC_DEEP, 150), (0.84, 0.02, 0.36, MAGENTA, 120),
            (0.92, 0.82, 0.38, ACC_DEEP, 70), (0.06, 0.92, 0.34, MAGENTA, 50))


def _scene(width, height):
    fit = min(1, _SCENE_MAX / max(width, height, 1))
    width, height = max(1, round(width * fit)), max(1, round(height * fit))
    key = (width, height)
    if key not in _SCENES:
        if len(_SCENES) >= _SCENE_LIMIT:
            _SCENES.clear()
        sharp = QPixmap(width, height)
        painter = QPainter(sharp)
        painter.setRenderHint(QPainter.Antialiasing)
        glow_top = QRadialGradient(0.5, -0.15, 1.1)  # то же зарево сверху, что в STYLE
        glow_top.setCoordinateMode(QGradient.ObjectBoundingMode)
        for stop, color in ((0, GLOW_1), (0.30, GLOW_2), (0.6, GLOW_3), (1, BG)):
            glow_top.setColorAt(stop, QColor(color))
        painter.fillRect(sharp.rect(), glow_top)
        painter.setPen(Qt.NoPen)
        reach = max(width, height)
        for x, y, radius, color, alpha in _lights():
            center = QPointF(x * width, y * height)
            light = QRadialGradient(center, radius * reach)
            bright = QColor(color)
            bright.setAlpha(alpha)
            light.setColorAt(0, bright)
            light.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setBrush(light)
            painter.drawEllipse(center, radius * reach, radius * reach)
        painter.end()
        small = sharp.scaled(max(1, int(width * _BLUR_SCALE)), max(1, int(height * _BLUR_SCALE)),
                             Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        _SCENES[key] = (sharp, small)
    return _SCENES[key]


def _with_alpha(color, alpha):
    result = QColor(color)
    result.setAlpha(alpha)
    return result


def _is_glass_button(obj):
    # крестик «очистить» внутри поля — не кнопка окна, его не трогаем
    if isinstance(obj.parentWidget() if isinstance(obj, QWidget) else None, QLineEdit):
        return False
    # стекло рисует только надпись или (у «глаза») значок: кнопку со значком и надписью,
    # стрелкой или меню рисует сам Qt — иначе человек не увидел бы, что он нажимает
    if isinstance(obj, QPushButton):
        return obj.icon().isNull() and obj.menu() is None
    if isinstance(obj, QToolButton):
        return not obj.text() and obj.arrowType() == Qt.NoArrow and obj.menu() is None
    return False


def _glass_radius(button):
    """Кнопки — почти капсулы: это и даёт ощущение капли."""
    return min(button.height() / 2, 17)


def _draw_glass(painter, widget, rect, radius, tint, dark, sheen, rim_top, rim_bottom, spot=None):
    """Один кусок стекла. tint — оттенок (цвет или перелив), dark — затемнение основы
    (чтобы текст читался на ярком пятне),
    sheen — сила блика, rim_* — яркость кромки вверху и внизу, spot — пятно света под курсором."""
    window = widget.window()
    small = _scene(window.width(), window.height())[1]
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.save()
    painter.setClipPath(path)
    # 1. то, что под стеклом: размыто и чуть увеличено, как через линзу
    corner = widget.mapTo(window, QPoint(0, 0))
    width, height = rect.width() * _LENS, rect.height() * _LENS
    source = QRectF(corner.x() + rect.center().x() - width / 2, corner.y() + rect.center().y() - height / 2, width, height)
    scale_x, scale_y = small.width() / max(window.width(), 1), small.height() / max(window.height(), 1)
    painter.drawPixmap(rect, small, QRectF(source.x() * scale_x, source.y() * scale_y, width * scale_x, height * scale_y))
    painter.fillPath(path, _with_alpha(BG, dark))
    # 2. оттенок стекла
    painter.fillPath(path, tint)
    # 3. блик сверху — поверхность кажется выпуклой
    gloss = QLinearGradient(rect.topLeft(), QPointF(rect.x(), rect.y() + rect.height() * 0.55))
    gloss.setColorAt(0, QColor(255, 255, 255, sheen))
    gloss.setColorAt(1, QColor(255, 255, 255, 0))
    painter.fillPath(path, gloss)
    # 4. затемнение снизу — толщина стекла
    depth = QLinearGradient(QPointF(rect.x(), rect.bottom() - rect.height() * 0.4), rect.bottomLeft())
    depth.setColorAt(0, QColor(0, 0, 0, 0))
    depth.setColorAt(1, QColor(0, 0, 0, 55))
    painter.fillPath(path, depth)
    # 5. пятно света под курсором
    if spot is not None:
        light = QRadialGradient(spot, rect.height() * 1.6)
        light.setColorAt(0, QColor(255, 255, 255, 62))
        light.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillPath(path, light)
    painter.restore()
    # 6. кромка: свет преломляется на краях — ярко сверху слева и снизу справа, бока тусклые
    rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
    rim.setColorAt(0, QColor(255, 255, 255, rim_top))
    rim.setColorAt(0.35, QColor(255, 255, 255, 34))
    rim.setColorAt(0.65, QColor(255, 255, 255, 26))
    rim.setColorAt(1, QColor(255, 255, 255, rim_bottom))
    painter.setPen(QPen(rim, 1.2))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(rect.adjusted(0.6, 0.6, -0.6, -0.6), radius, radius)


def _paint_button(button):
    painter = QPainter(button)
    try:
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        enabled = button.isEnabled()
        painter.setOpacity(1 if enabled else 0.45)
        pressed, hover = button.isDown(), enabled and button.underMouse()
        rect = QRectF(button.rect())
        if pressed:  # нажатая капля чуть сжимается
            center = rect.center()
            painter.translate(center)
            painter.scale(0.97, 0.97)
            painter.translate(-center)
        look = button.property("kind")
        tint, ink = _with_alpha(WHITE, 42 if hover else 26), QColor(TEXT)
        if look == "primary":  # главная кнопка переливается как ключ: лавандовый сверху, фуксия снизу
            tint, ink = QLinearGradient(rect.topLeft(), rect.bottomLeft()), QColor(LETTER_INK if egg else WHITE)
            strength = 230 if pressed else 205 if hover else 175
            tint.setColorAt(0, _with_alpha(ACC, strength))
            tint.setColorAt(1, _with_alpha(MAGENTA, strength))
        elif look == "danger":
            tint, ink = _with_alpha(BAD, 120 if pressed else 70), QColor(BAD_INK)
        elif pressed or (button.isCheckable() and button.isChecked()):
            tint = _with_alpha(ACC, 70)
        if not enabled:
            ink = QColor(FAINT)
        spot = QPointF(button.mapFromGlobal(QCursor.pos())) if hover else None
        radius = _glass_radius(button)
        _draw_glass(painter, button, rect, radius, tint, dark=50 if look else 88,
                    sheen=30 if pressed else 62, rim_top=255 if hover else 215, rim_bottom=165, spot=spot)
        if button.hasFocus():  # фокус с клавиатуры виден, как раньше
            painter.setPen(QPen(QColor(ACC), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)
        painter.setOpacity(1)  # затемнено только стекло: FAINT на нём ещё читается, а вдвойне — уже нет
        icon = button.icon()
        if isinstance(button, QToolButton) and not icon.isNull():
            size = button.iconSize()
            place = QRect(QPoint(0, 0), size)
            place.moveCenter(button.rect().center())
            icon.paint(painter, place, Qt.AlignCenter, QIcon.Normal if enabled else QIcon.Disabled,
                       QIcon.On if button.isChecked() else QIcon.Off)
        else:
            text = button.text()
            if len(text) == 1:
                # один значок: по центру ставим сам рисунок, а не его ячейку в шрифте —
                # внутри ячейки он лежит не посередине, и на Windows это заметно (замок съезжал вправо)
                shape = QPainterPath()
                shape.addText(0, 0, button.font(), text)
                painter.fillPath(shape.translated(rect.center() - shape.boundingRect().center()), ink)
            else:
                painter.setFont(button.font())
                painter.setPen(ink)
                painter.drawText(rect, Qt.AlignCenter | Qt.TextHideMnemonic, text)
    finally:
        painter.end()


def _paint_card(card):
    painter = QPainter(card)
    try:
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        # большая панель темнее кнопок: на ней читают таблицу
        _draw_glass(painter, card, QRectF(card.rect()), CARD_RADIUS, _with_alpha(WHITE, 8), dark=135, sheen=22, rim_top=150, rim_bottom=90)
        painter.setPen(QPen(QColor(RIM_CARD), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(card.rect()).adjusted(0.5, 0.5, -0.5, -0.5), CARD_RADIUS, CARD_RADIUS)
    finally:
        painter.end()


def _paint_window(window):
    painter = QPainter(window)
    try:
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        sharp = _scene(window.width(), window.height())[0]
        painter.drawPixmap(window.rect(), sharp, sharp.rect())
    finally:
        painter.end()


def _paint_glass(obj):
    """Рисует элемент жидким стеклом. True — нарисовано, False — пусть рисует сам Qt."""
    if _is_glass_button(obj):
        _paint_button(obj)
    elif isinstance(obj, QFrame) and obj.property("role") == "card":
        _paint_card(obj)
    elif isinstance(obj, (QMainWindow, QDialog)) or (isinstance(obj, QWidget) and obj.property("role") == "backdrop"):
        _paint_window(obj)
    else:
        return False
    return True
