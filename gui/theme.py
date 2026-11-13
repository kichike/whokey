"""Оформление: почти чёрный фон с фиолетовым заревом, лавандовый неон и
«стекло» в духе Liquid Glass, моноширинный шрифт MesloLGS Nerd Font.

Цвета взяты из CSS-переменных chat.eblo.id (--bg, --surf, --acc и т.д.);
лавандовые оттенки сдвинуты на 15° к розовому (по просьбе).
Стекло: полупрозрачные панели, кнопки и поля со скруглёнными углами и светлой
кромкой сверху — сквозь них видно зарево фона. Настоящее Liquid Glass (с
размытием и преломлением того, что под ним) macOS рисует только для своих
родных элементов, в Qt его нет — поэтому стекло нарисовано прозрачностью.
На macOS под окном лежит настоящее размытие рабочего стола (gui/sysglass.py, SYSTEM),
а нарисованная «сцена» под кнопками и панелями не нужна: сквозь них видно его.
"""

import html
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (QColor, QCursor, QFont, QFontDatabase, QFontMetricsF, QGradient, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPalette, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QDialog, QFileDialog, QFrame, QGraphicsDropShadowEffect, QLabel,
                               QLineEdit, QMainWindow, QPushButton, QStyle, QToolButton, QWidget)
from shiboken6 import isValid  # жив ли ещё объект Qt за питоновской обёрткой

from gui import prefs, sysglass

SYSTEM = False  # системное стекло macOS под окнами (включает apply)

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


# Цвета только для рисования (не для QSS): тень и глубина, перелив кромки стекла, пятна света сцены,
# текст на акцентном переливе. В тёмной теме тень — чёрная, кромка — белая.
SHADOW = "#000000"
IRIS_1 = IRIS_2 = IRIS_3 = "#ffffff"
LAVENDER, PINK, SKY = "#c3b0ff", "#ffb3e6", "#9fd2ff"
ON_ACCENT = "#ffffff"
_EXTRA = ["OK", "WARN", "BAD", "BAD_INK", "SHADOW", "IRIS_1", "IRIS_2", "IRIS_3", "LAVENDER", "PINK", "SKY", "ON_ACCENT"]
_BASE = ["BG", "SURF", "WELL", "LINE", "LINE2", "TEXT", "MUTED", "FAINT", "ACC", "ACC_DEEP", "ACC_LIGHT", "ACC_FILL",
         "MAGENTA", "NEON", "RAISED", "TIP", "TIP_RIM", "GLOW_1", "GLOW_2", "GLOW_3", "TITLE_START",
         "LETTER_TOP", "LETTER_BOTTOM", "LETTER_INK"]
_DARK_COLORS = {name: globals()[name] for name in _BASE + _EXTRA}

# Светлая тема «Перламутр»: холодный белый с перламутровым отливом, пастельный свет по углам
# (лаванда, розовый, немного голубого), прозрачное матовое стекло с переливчатой кромкой.
# Роль ACC_LIGHT — «самый выразительный акцент для текста»: на тёмном это самый светлый
# лавандовый, на светлом — самый тёмный. Контраст текста по WCAG: TEXT 15:1, MUTED 7:1, FAINT ≥ 4.7:1,
# белый на переливе ACC → MAGENTA ≥ 4.8:1.
_LIGHT_COLORS = {
    "BG": "#f3f2fb", "SURF": "#faf9ff", "WELL": "#ecebf7", "LINE": "#e3e0f2", "LINE2": "#d4cfea",
    "TEXT": "#1b1846", "MUTED": "#4f4b7c", "FAINT": "#6a6694",
    "ACC": "#6a4bdc", "ACC_DEEP": "#5b3fd0", "ACC_LIGHT": "#4b2fb5", "ACC_FILL": "#e6defd",
    "MAGENTA": "#b739c4", "NEON": "#b02ab8", "RAISED": "#ffffff", "TIP": "#fdfcff", "TIP_RIM": "#ddd7f1",
    "GLOW_1": "#e2d8ff", "GLOW_2": "#ebe6fd", "GLOW_3": "#f1effb", "TITLE_START": "#6a4bdc",
    "LETTER_TOP": "#ece6ff", "LETTER_BOTTOM": "#f7d2f3", "LETTER_INK": "#3a2696",
    "OK": "#1e7d36", "WARN": "#b07400", "BAD": "#d0304a", "BAD_INK": "#c0263b",
    "SHADOW": "#3a2f8a", "IRIS_1": "#a58cf5", "IRIS_2": "#f08bd8", "IRIS_3": "#8cc8f5",
    "LAVENDER": "#c3b0ff", "PINK": "#ffb3e6", "SKY": "#9fd2ff", "ON_ACCENT": "#ffffff",
}

_ASSETS = Path(__file__).parent / "assets"
KEY_FILE = _ASSETS / "key.png"  # ключ с логотипа без плитки (make_key.py)
ABOUT_FILE = ICON_FILE          # картинка в «О программе»
_DARK_FILES = {"CHECK_FILE": CHECK_FILE, "ARROW_FILE": ARROW_FILE, "ARROW_UP_FILE": ARROW_UP_FILE,
               "EYE_FILE": EYE_FILE, "EYE_OFF_FILE": EYE_OFF_FILE, "KEY_FILE": KEY_FILE, "ABOUT_FILE": ABOUT_FILE}
# на светлом: стрелки и «глаз» тёмные, галочка белая (стоит на переливе), ключ глубже и насыщеннее,
# в «О программе» — перламутровая плитка вместо чёрной
_LIGHT_FILES = {"CHECK_FILE": (_ASSETS / "check_light.svg").as_posix(), "ARROW_FILE": (_ASSETS / "arrow_light.svg").as_posix(),
                "ARROW_UP_FILE": (_ASSETS / "arrow_up_light.svg").as_posix(), "EYE_FILE": str(_ASSETS / "eye_light.svg"),
                "EYE_OFF_FILE": str(_ASSETS / "eye_off_light.svg"), "KEY_FILE": _ASSETS / "key_light.png",
                "ABOUT_FILE": _ASSETS / "about_light.png"}

LIGHT = False        # сейчас светлая тема
_want_light = False  # светлую выбрал человек или система



def rgba(color, alpha):
    """Цвет с прозрачностью для оформления Qt: rgba("#caa7f0", 80). alpha — от 0 до 255."""
    color = color.lstrip("#")
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def solid(color, alpha, over=None):
    """Непрозрачный цвет, который выглядит как color с прозрачностью alpha поверх фона over.

    Для рамок: скруглённую рамку Qt рисует по кусочкам (стороны и дуги углов
    отдельно), и у полупрозрачной рамки на стыках кусочки накладываются —
    получаются светлые точки в углах. Непрозрачная рамка стыков не показывает.
    over — средний цвет фона окна под стеклом.
    """
    if over is None:  # средний цвет фона окна под стеклом
        over = BG if LIGHT else "#16123a"
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
    global HOLLOW_FLAT
    HOLLOW_FLAT = HOLLOW
    if LIGHT:
        GLASS = glass(rgba(WHITE, 235), rgba(WHITE, 190), rgba("#f1eefc", 200))
        GLASS_HOVER = glass(rgba(WHITE, 255), rgba(WHITE, 220), rgba("#f4f0ff", 230))
        GLASS_PANEL = glass(rgba(WHITE, 200), rgba(WHITE, 165), rgba(WHITE, 150))
        GLASS_ACC = glass(rgba(ACC, 235), rgba(ACC, 235), rgba(MAGENTA, 235))
        GLASS_ACC_HOVER = glass(rgba(ACC, 255), rgba(ACC, 255), rgba(MAGENTA, 255))
        GLASS_BAD = glass(rgba(WHITE, 230), rgba("#fff3f5", 220), rgba("#ffe6ea", 220))
        RIM = solid(SHADOW, 48)
        RIM_HOVER = solid(ACC, 110)
        RIM_ACC = solid(ACC_DEEP, 200)
        RIM_CARD = solid(IRIS_1, 150)
        # «углубление» поля: лёгкая холодная тень сверху, ниже — молочно-белое
        HOLLOW = (f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {rgba(SHADOW, 30)}, "
                  f"stop:0.28 {rgba(WHITE, 150)}, stop:1 {rgba(WHITE, 215)})")
        HOLLOW_FLAT = rgba(SHADOW, 22)  # дорожка полоски: перелив на 8 точках смотрелся бы грязно
    elif SYSTEM:  # под стеклом рабочий стол любого цвета: непрозрачная смесь видна серой полосой
        RIM = rgba(ACC_LIGHT, 70)
        HOLLOW = rgba("#05040f", 120)


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
QLabel[role="title"] {{ font-size: {FONT_SIZE * 2 + 2}px; font-weight: 800; color: {NEON}; }}
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
""" + (f"""
/* системное стекло: на светлом размытом рабочем столе бледные подписи пропадали */
QHeaderView::section {{ color: {ACC_LIGHT}; }}
QLabel[role="faint"] {{ color: {MUTED}; }}
""" if SYSTEM and not LIGHT else "") + (_light_style() if LIGHT else "")


def _light_style():
    """Светлая тема: всё, что в общих правилах выше написано белым или чёрным."""
    return f"""
QLabel[role="chip"] {{ color: {ACC_DEEP}; background: {rgba(ACC, 22)}; border: 1px solid {solid(ACC, 90)}; }}
QLabel[role="chip_off"] {{ color: {MUTED}; background: {rgba(SHADOW, 12)}; border: 1px solid {solid(SHADOW, 60)}; }}
QLineEdit, QSpinBox, QPlainTextEdit {{ selection-background-color: {ACC_FILL}; selection-color: {TEXT}; }}
QLineEdit:disabled {{ color: {FAINT}; }}
QPushButton:disabled {{ color: {FAINT}; background: {rgba(WHITE, 120)}; border-color: {solid(SHADOW, 30)}; }}
QPushButton[kind="primary"] {{ color: {ON_ACCENT}; }}
QPushButton[kind="danger"] {{ border-color: {solid(BAD, 120)}; color: {BAD_INK}; }}
QPushButton:pressed, QToolButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {rgba(SHADOW, 40)}, stop:1 {rgba(ACC, 30)}); }}
QPushButton[kind="danger"]:pressed {{ background: {rgba(BAD, 50)}; }}
QToolButton:checked {{ background: {rgba(ACC, 26)}; }}
QLineEdit QToolButton, QLineEdit QToolButton:checked {{ background: transparent; border: none; }}
QComboBox QAbstractItemView {{ border: 1px solid {solid(IRIS_1, 140, TIP)}; }}
QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {solid(ACC, 40, TIP)}, stop:1 {solid(MAGENTA, 34, TIP)});
    color: {ACC_LIGHT}; }}
QCheckBox::indicator {{ border: 1px solid {solid(SHADOW, 80)}; background: {HOLLOW}; }}
QCheckBox::indicator:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACC}, stop:1 {MAGENTA}); border-color: {ACC_DEEP}; }}
QCheckBox::indicator:disabled {{ background: {rgba(SHADOW, 14)}; border-color: {solid(SHADOW, 40)}; }}
QHeaderView::section {{ color: {MUTED}; border-bottom: 1px solid {rgba(ACC, 70)}; }}
QMenuBar::item:selected {{ background: {solid(ACC, 40, TIP)}; }}
QMenu {{ border: 1px solid {solid(IRIS_1, 140, TIP)}; }}
QMenu::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {solid(ACC, 40, TIP)}, stop:1 {solid(MAGENTA, 34, TIP)});
    color: {ACC_LIGHT}; }}
QToolTip {{ background: {TIP}; color: {TEXT}; border: 1px solid {solid(IRIS_1, 140, TIP)}; }}
QProgressBar {{ background: {HOLLOW_FLAT}; border: 1px solid {solid(SHADOW, 36)}; }}
QScrollBar::handle:vertical {{ background: {rgba(SHADOW, 60)}; }}
QScrollBar::handle:vertical:hover {{ background: {rgba(ACC, 140)}; }}
"""


STYLE = _style()


def apply(app):
    """Включает оформление для всего приложения."""
    global SYSTEM, _want_light
    SYSTEM = sysglass.available() and prefs.system_glass()  # без экрана macOS настройки не читаем
    _want_light = _wants_light(app, prefs.theme_mode())
    _set_palette()
    QFontDatabase.addApplicationFont(str(FONT_BOLD_FILE))
    families = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(FONT_FILE)))
    font = QFont(families[0] if families else FONT_FAMILY)
    font.setPixelSize(FONT_SIZE)
    app.setFont(font)
    # Fusion — простой стиль Qt, который послушно перекрашивается;
    # родной стиль macOS игнорирует часть настроек оформления
    app.setStyle("Fusion")
    _apply_colors(app)
    try:  # «как в системе»: система переключилась на тёмное или светлое — и WhoKey за ней
        app.styleHints().colorSchemeChanged.connect(_system_scheme_changed)
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
    if LIGHT:
        palette.setColor(QPalette.Light, QColor(WHITE))
        palette.setColor(QPalette.Dark, QColor(LINE2))
        palette.setColor(QPalette.Shadow, QColor(SHADOW))
    app.setPalette(palette)
    app.setStyleSheet(STYLE + (
        # на Mac кнопки окон в системном порядке: «Отмена» слева, главное действие справа
        "QDialogButtonBox { button-layout: 1; }" if sys.platform == "darwin" else
        # на Linux Qt добавляет на кнопки значки системной темы, которые не подходят к оформлению
        "QDialogButtonBox { dialogbuttonbox-buttons-have-icons: 0; }" if sys.platform.startswith("linux") else ""))


egg = False  # включена ли пасхалка

THEMES = ("system", "dark", "light")  # выбор в «Настройках»: как в системе, тёмная, светлая


def _wants_light(app, mode):
    """Нужна ли светлая тема. Заодно говорит системе, какую рамку окна рисовать: при выбранной
    теме — её, при «как в системе» — системную (тогда и рамка, и WhoKey следуют за системой)."""
    hints = app.styleHints() if app is not None else None
    try:
        if mode == "system":
            hints.unsetColorScheme()
            return hints.colorScheme() == Qt.ColorScheme.Light
        hints.setColorScheme(Qt.ColorScheme.Light if mode == "light" else Qt.ColorScheme.Dark)
    except AttributeError:  # Qt старше 6.8 или нет приложения: системную тему не узнать
        pass
    return mode == "light"


def _set_palette():
    """Цвета, картинки и оформление по выбранной теме (у котика-пасхалки — свои тёмная и светлая палитры)."""
    global LIGHT, STYLE
    LIGHT = _want_light
    globals().update(_LIGHT_COLORS if LIGHT else _DARK_COLORS)
    if egg:
        from gui import cat  # здесь, а не наверху: cat сам рисует через theme
        globals().update(cat.LIGHT_COLORS if LIGHT else cat.DARK_COLORS)
    globals().update(_LIGHT_FILES if LIGHT else _DARK_FILES)
    _derive_colors()
    STYLE = _style()
    _SCENES.clear()


def _refresh_app():
    """Перекрашивает открытые окна: оформление Qt — заново, свечения и заранее нарисованное — вручную."""
    app = QApplication.instance()
    if app is None:
        return
    _apply_colors(app)
    for widget in app.allWidgets():  # неоновые свечения заданы цветом заранее
        effect = widget.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            effect.setColor(_glow_color(widget, effect.color()))
        elif isinstance(widget, Halo):
            widget.recolor()
    for window in app.topLevelWidgets():
        if SYSTEM:
            sysglass.set_light(window, LIGHT)  # материал под окном — под стать теме
        recolor = getattr(window, "_recolor", None)
        if callable(recolor):
            recolor()  # логотип, значки, буквы-кружки (MainWindow._recolor)
        window.update()


def set_theme(mode):
    """Тема из «Настроек»: "system", "dark" или "light". Открытые окна перекрашиваются сразу."""
    global _want_light
    prefs.set_value("theme", mode)
    _want_light = _wants_light(QApplication.instance(), mode)
    if _want_light != LIGHT:
        _set_palette()
        _refresh_app()


def _system_scheme_changed(*_):
    global _want_light
    if prefs.theme_mode() != "system":
        return  # тему выбрал человек — система ему не указ
    light = _wants_light(QApplication.instance(), "system")
    if light != _want_light:
        _want_light = light
        _set_palette()
        _refresh_app()


def set_egg(on):
    """Включает или выключает палитру пасхалки во всём приложении. Открытые окна перекрашиваются сами;
    то, что нарисовано заранее (значки, логотип), главное окно обновляет в MainWindow._recolor."""
    global egg
    if on == egg:
        return
    egg = on
    _set_palette()
    _refresh_app()


_LIGHT_GLOW = 0.42  # неон на светлом «грязнится» — там то же свечение, но мягче


def glow(widget, color=None, radius=24, alpha=170):
    """Неоновое свечение вокруг элемента (размытая тень без смещения).

    В оформлении Qt (QSS) нет box-shadow, поэтому свечение — отдельный эффект.
    У одного элемента может быть только один такой эффект.
    """
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(radius)
    effect.setOffset(0, 0)
    widget.setProperty("glow_alpha", alpha)  # сила в тёмной теме: при смене темы пересчитываем от неё
    light = QColor(color or ACC)
    light.setAlpha(int(alpha * _LIGHT_GLOW) if LIGHT else alpha)
    effect.setColor(light)
    widget.setGraphicsEffect(effect)
    return widget


def neon_card(card):
    """Карточка с неоновым ореолом вокруг рамки (слой Halo, см. _FocusGlow)."""
    card.setProperty("neon", True)
    return card


def neon_title(label):
    """Заголовок, светящийся как неоновая вывеска (на светлом — мягкий розовый ореол)."""
    return glow(label, IRIS_2 if LIGHT else NEON, radius=22, alpha=210)


def _glow_color(widget, old):
    """Цвет свечения элемента в текущей теме (см. glow, kind, neon_title)."""
    if widget.property("role") == "title":
        color = QColor(IRIS_2 if LIGHT else NEON)
    elif widget.property("kind") == "primary":
        color = QColor(ACC)
    else:
        color = QColor(NEON)
    base = widget.property("glow_alpha")
    base = int(base) if base is not None else old.alpha()
    color.setAlpha(int(base * _LIGHT_GLOW) if LIGHT else base)
    return color


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
        if LIGHT and target.property("neon"):  # карточка на светлом: мягкая лавандовая тень, а не неон
            color, alpha = IRIS_1, 120
        elif LIGHT and alpha >= 150:  # вспышка нажатия
            alpha = int(alpha * 0.8)
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
            if self.target.property("neon"):
                self.color, self.alpha = (QColor(IRIS_1), 120) if LIGHT else (QColor(ACC_DEEP), 110)
            else:
                self.color = QColor(ACC)
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
            if SYSTEM and event.type() == QEvent.MouseButtonPress and _drag_window(obj, event):
                return True  # окно поехало за мышью — нажатие больше никому не нужно
            self._handle(obj, event)
        except Exception:
            traceback.print_exc()
        return False  # событие идёт дальше как обычно; при ошибке рисования — обычный вид из STYLE

    def _handle(self, obj, event):
        kind = event.type()
        if SYSTEM and kind in (QEvent.Polish, QEvent.Show) and sysglass.is_window(obj) \
                and not isinstance(obj, QFileDialog):  # окно выбора файла — системное, у него своё оформление
            if kind == QEvent.Polish:
                sysglass.prepare(obj)
            else:
                sysglass.prepare(obj)
                sysglass.attach(obj, LIGHT)
                if isinstance(obj, QDialog):
                    QTimer.singleShot(0, lambda: sysglass.fit_height(obj) if isValid(obj) else None)
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


def _drag_window(obj, event):
    """Системное стекло: полосу заголовка закрывает содержимое окна, и macOS не может тянуть окно сама.
    Поэтому окно тянется за любое пустое место — фон, контейнеры, обычные подписи. Кнопки, поля, таблица,
    ссылки и ключ-логотип (пасхалка) получают нажатие как обычно."""
    if event.button() != Qt.LeftButton or not isinstance(obj, QWidget):
        return False
    window = obj.window()
    if not sysglass.is_window(window) or isinstance(window, QFileDialog):
        return False
    # нажатие, которое элемент не взял (ссылка, поле), Qt передаёт родителю — такое окно не тянет
    target = window.childAt(window.mapFromGlobal(event.globalPosition().toPoint())) or window
    if obj is not target:
        return False
    if obj is not window and type(obj) not in (QWidget, QFrame, QLabel) and obj.metaObject().className() != "QStatusBar":
        return False
    if isinstance(obj, QLabel) and ("<a " in obj.text() or obj.textInteractionFlags() & Qt.TextSelectableByMouse):
        return False
    handle = window.windowHandle()
    return handle is not None and handle.startSystemMove()


def badge(symbol, color=None, size=56):
    """Значок для окошек-вопросов: «?» или «!» в неоне на стеклянном круге.

    Стандартный значок Qt на тёмном фоне почти не виден.
    """
    color = color or NEON
    if LIGHT:
        return _pearl_badge(symbol, color, size)
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


def _pearl_badge(symbol, color, size):
    """Светлая тема: знак на перламутровой бусине с переливчатой кромкой и мягкой тенью."""
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    circle = QRectF(5, 4, size - 10, size - 10)
    p.setPen(Qt.NoPen)
    for i in range(5, 0, -1):  # мягкая холодная тень под бусиной
        p.setBrush(_with_alpha(SHADOW, 7))
        p.drawEllipse(circle.adjusted(-i * 0.6, -i * 0.3 + 1.5, i * 0.6, i * 0.6 + 1.5))
    fill = QRadialGradient(circle.center() - QPointF(circle.width() * 0.18, circle.height() * 0.22), circle.width() * 0.75)
    fill.setColorAt(0, QColor(WHITE))
    fill.setColorAt(0.6, QColor("#f6f2ff"))
    fill.setColorAt(1, QColor("#ece3fb"))
    p.setBrush(fill)
    p.setPen(QPen(_iris(circle), 1.4))
    p.drawEllipse(circle)
    font = QFont(QApplication.font().family())
    font.setPixelSize(int(size * 0.5))
    font.setWeight(QFont.ExtraBold)
    shape = QPainterPath()
    shape.addText(0, 0, font, symbol)
    shape = shape.translated(circle.center() - shape.boundingRect().center())
    if QColor(color) == QColor(NEON):  # неоновый знак — переливом ключа
        ink = QLinearGradient(circle.topLeft(), circle.bottomLeft())
        ink.setColorAt(0.2, QColor(ACC))
        ink.setColorAt(0.8, QColor(MAGENTA))
    else:
        ink = QColor(color)
    p.setPen(Qt.NoPen)
    p.fillPath(shape, ink)
    p.end()
    return pixmap


def _iris(rect, alpha=255):
    """Переливчатая кромка светлой темы: лаванда → розовый → голубой по диагонали."""
    rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
    rim.setColorAt(0, _with_alpha(IRIS_1, alpha))
    rim.setColorAt(0.5, _with_alpha(IRIS_2, alpha))
    rim.setColorAt(1, _with_alpha(IRIS_3, alpha))
    return rim


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


def glyph_pixmap(name, color=None, px=14, box=None):
    box = box or px + 4
    color = color or ACC
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


def glyph_icon(name, color=None, px=14):
    return QIcon(glyph_pixmap(name, color, px))


def logo_pixmap(height):
    """Пиксельный неоновый ключ с логотипа высотой height точек."""
    if egg:
        from gui import cat
        return cat.logo(height)
    source = QPixmap(str(KEY_FILE))
    if source.isNull():
        return QPixmap()
    pixmap = source.scaledToHeight(height * _SCALE, Qt.SmoothTransformation)
    pixmap.setDevicePixelRatio(_SCALE)
    return pixmap


def monogram(text, size=24):
    """Кружок-буква записи (скруглённый квадрат), как в меню расширения: «G» для github.com."""
    if egg:
        from gui import cat
        return cat.monogram(text, size)
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
    if LIGHT:  # пастельная плашка: переливчатая кромка и блик сверху, иначе сливается с белым
        r = QRectF(0.5, 0.5, size - 1, size - 1)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(_iris(r, 230), max(0.8, size / 30)))
        painter.drawRoundedRect(r, size * 0.29, size * 0.29)
        sheen = QLinearGradient(0, 0, 0, size * 0.5)
        sheen.setColorAt(0, _with_alpha(WHITE, 200))
        sheen.setColorAt(1, _with_alpha(WHITE, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(sheen)
        painter.drawRoundedRect(r.adjusted(1.2, 1.2, -1.2, -size * 0.45), size * 0.24, size * 0.24)
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
    if LIGHT:  # дневной свет по углам: лаванда, розовый, голубой
        return ((0.10, 0.02, 0.46, LAVENDER, 150), (0.88, 0.00, 0.40, PINK, 125),
                (0.96, 0.86, 0.42, SKY, 110), (0.04, 0.96, 0.36, PINK, 80))
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
            if LIGHT:  # гаснет в тот же оттенок: через прозрачный чёрный на светлом шла бы серая кайма
                light.setColorAt(0.5, _with_alpha(color, alpha // 3))
                light.setColorAt(1, _with_alpha(color, 0))
            else:
                light.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setBrush(light)
            painter.drawEllipse(center, radius * reach, radius * reach)
        if LIGHT:  # перламутровый отлив: едва заметная белая полоса по диагонали
            band = QLinearGradient(0, 0, width, height)
            band.setColorAt(0.35, _with_alpha(WHITE, 0))
            band.setColorAt(0.5, _with_alpha(WHITE, 70))
            band.setColorAt(0.65, _with_alpha(WHITE, 0))
            painter.fillRect(sharp.rect(), band)
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


def _see_through():
    """Под окном настоящее размытие рабочего стола (системное стекло macOS)."""
    return SYSTEM


def _draw_glass(painter, widget, rect, radius, tint, dark, sheen, rim_top, rim_bottom, spot=None,
                iris=True, depth_alpha=26):
    """Один кусок стекла. tint — оттенок (цвет или перелив), dark — затемнение основы
    (чтобы текст читался на ярком пятне; в светлой теме — сила белой «изморози»),
    sheen — сила блика, rim_* — яркость кромки вверху и внизу, spot — пятно света под курсором.
    iris и depth_alpha — только для светлой темы: переливчатая кромка и сила холодной тени снизу."""
    if LIGHT:
        _draw_pearl_glass(painter, widget, rect, radius, tint, dark, sheen, rim_top, rim_bottom, spot, iris, depth_alpha)
        return
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.save()
    painter.setClipPath(path)
    # 1. то, что под стеклом: размыто и чуть увеличено, как через линзу
    #    (при системном стекле под ним уже настоящее размытие — рисовать нечего)
    if not _see_through():
        window = widget.window()
        small = _scene(window.width(), window.height())[1]
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


def _draw_pearl_glass(painter, widget, rect, radius, tint, frost, sheen, rim_top, rim_bottom, spot, iris, depth_alpha):
    """Светлое стекло: размытая сцена → белая изморозь → оттенок → яркий блик сверху →
    холодная тень снизу → переливчатая кромка и тонкая белая линия внутри неё («мокрый» край)."""
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    painter.save()
    painter.setClipPath(path)
    if not _see_through():  # при системном стекле под ним уже настоящее размытие
        window = widget.window()
        small = _scene(window.width(), window.height())[1]
        corner = widget.mapTo(window, QPoint(0, 0))
        width, height = rect.width() * _LENS, rect.height() * _LENS
        source = QRectF(corner.x() + rect.center().x() - width / 2, corner.y() + rect.center().y() - height / 2, width, height)
        scale_x, scale_y = small.width() / max(window.width(), 1), small.height() / max(window.height(), 1)
        painter.drawPixmap(rect, small, QRectF(source.x() * scale_x, source.y() * scale_y, width * scale_x, height * scale_y))
    painter.fillPath(path, _with_alpha(WHITE, frost))
    painter.fillPath(path, tint)
    gloss = QLinearGradient(rect.topLeft(), QPointF(rect.x(), rect.y() + rect.height() * 0.55))
    gloss.setColorAt(0, _with_alpha(WHITE, sheen))
    gloss.setColorAt(1, _with_alpha(WHITE, 0))
    painter.fillPath(path, gloss)
    depth = QLinearGradient(QPointF(rect.x(), rect.bottom() - rect.height() * 0.45), rect.bottomLeft())
    depth.setColorAt(0, _with_alpha(SHADOW, 0))
    depth.setColorAt(1, _with_alpha(SHADOW, depth_alpha))
    painter.fillPath(path, depth)
    if spot is not None:
        light = QRadialGradient(spot, rect.height() * 1.6)
        light.setColorAt(0, _with_alpha(WHITE, 120))
        light.setColorAt(1, _with_alpha(WHITE, 0))
        painter.fillPath(path, light)
    painter.restore()
    painter.setBrush(Qt.NoBrush)
    rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
    if iris:
        rim.setColorAt(0, _with_alpha(IRIS_1, rim_top))
        rim.setColorAt(0.45, _with_alpha(IRIS_2, int(rim_top * 0.55)))
        rim.setColorAt(1, _with_alpha(IRIS_3, rim_bottom))
    else:
        rim.setColorAt(0, _with_alpha(WHITE, rim_top))
        rim.setColorAt(1, _with_alpha(WHITE, rim_bottom))
    painter.setPen(QPen(rim, 1.1))
    painter.drawRoundedRect(rect.adjusted(0.55, 0.55, -0.55, -0.55), radius, radius)
    inner = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    inner.setColorAt(0, _with_alpha(WHITE, 255))
    inner.setColorAt(0.5, _with_alpha(WHITE, 40))
    inner.setColorAt(1, _with_alpha(WHITE, 0))
    painter.setPen(QPen(inner, 1.2))
    inner_radius = max(0.0, radius - 1.4)
    painter.drawRoundedRect(rect.adjusted(1.7, 1.7, -1.7, -1.7), inner_radius, inner_radius)


def _paint_button(button):
    painter = QPainter(button)
    try:
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        enabled = button.isEnabled()
        painter.setOpacity(1 if enabled else (0.55 if LIGHT else 0.45))
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
            tint, ink = QLinearGradient(rect.topLeft(), rect.bottomLeft()), QColor(ON_ACCENT)
            strength = 230 if pressed else 205 if hover else 175
            tint.setColorAt(0, _with_alpha(ACC, strength))
            tint.setColorAt(1, _with_alpha(MAGENTA, strength))
        elif look == "danger":
            tint, ink = _with_alpha(BAD, 120 if pressed else 70), QColor(BAD_INK)
        elif pressed or (button.isCheckable() and button.isChecked()):
            tint = _with_alpha(ACC, 70)
        if LIGHT:
            tint, ink, iris, sheen, frost = _pearl_button_look(look, rect, hover, pressed, button)
        if not enabled:
            ink = QColor(FAINT)
        spot = QPointF(button.mapFromGlobal(QCursor.pos())) if hover else None
        radius = _glass_radius(button)
        if LIGHT:
            _draw_glass(painter, button, rect, radius, tint, dark=frost, sheen=sheen,
                        rim_top=255 if hover else 220, rim_bottom=120 if look == "primary" else 200,
                        spot=spot, iris=iris)
            if look == "primary":  # тонкая тёмная кромка — у «капли» на белом виден край
                painter.setPen(QPen(_with_alpha(SHADOW, 60), 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        else:
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


def _pearl_button_look(look, rect, hover, pressed, button):
    """Светлая тема: (оттенок, цвет текста, переливчатая кромка, блик, изморозь) кнопки."""
    if look == "primary":
        tint = QLinearGradient(rect.topLeft(), rect.bottomRight())
        tint.setColorAt(0, QColor(ACC))
        tint.setColorAt(1, QColor(MAGENTA))
        return tint, QColor(ON_ACCENT), False, (15 if pressed else 55), 0
    sheen = 40 if pressed else 150
    if look == "danger":
        return _with_alpha(BAD, 60 if pressed else 22), QColor(BAD_INK), True, sheen, 150
    if pressed or (button.isCheckable() and button.isChecked()):
        return _with_alpha(ACC, 40), QColor(TEXT), True, sheen, 150
    return _with_alpha(WHITE, 70 if hover else 30), QColor(TEXT), True, sheen, 150


def _paint_card(card):
    painter = QPainter(card)
    try:
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        rect = QRectF(card.rect())
        if LIGHT:  # перламутровая панель: переливчатая кромка вместо отдельной рамки
            _draw_glass(painter, card, rect, CARD_RADIUS, _with_alpha(WHITE, 30), dark=175, sheen=90,
                        rim_top=230, rim_bottom=200, depth_alpha=8)
            return
        if SYSTEM:
            # сквозь панель видно размытый рабочий стол; кромка — неон от лаванды к фуксии
            _draw_glass(painter, card, rect, CARD_RADIUS, _with_alpha(WHITE, 6), dark=70, sheen=20, rim_top=120, rim_bottom=60)
            neon = QLinearGradient(rect.topLeft(), rect.bottomRight())
            neon.setColorAt(0, _with_alpha(ACC, 200))
            neon.setColorAt(1, _with_alpha(MAGENTA, 200))
            painter.setPen(QPen(neon, 1.2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0.6, 0.6, -0.6, -0.6), CARD_RADIUS, CARD_RADIUS)
            return
        # большая панель темнее кнопок: на ней читают таблицу
        _draw_glass(painter, card, rect, CARD_RADIUS, _with_alpha(WHITE, 8), dark=135, sheen=22, rim_top=150, rim_bottom=90)
        painter.setPen(QPen(QColor(RIM_CARD), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), CARD_RADIUS, CARD_RADIUS)
    finally:
        painter.end()


def _paint_window(window):
    if _see_through() and window.isWindow():
        _paint_wash(window)
        return
    painter = QPainter(window)
    try:
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        sharp = _scene(window.width(), window.height())[0]
        painter.drawPixmap(window.rect(), sharp, sharp.rect())
    finally:
        painter.end()


def _paint_wash(window):
    """Фон окна поверх системного стекла: вуаль сверху вниз и те же пятна света, что в _scene,
    но полупрозрачные — цвета рабочего стола проступают. В тёмной теме — индиго-вуаль и неон
    лавандой и фуксией, в светлой — перламутровая дымка и пастель."""
    painter = QPainter(window)
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(window.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        width, height = window.width(), window.height()
        wash = QLinearGradient(0, 0, 0, height)
        if LIGHT:  # под ней светлая изморозь macOS: дымка лишь выравнивает тон, чтобы текст читался
            wash.setColorAt(0, _with_alpha(GLOW_1, 120))
            wash.setColorAt(0.5, _with_alpha(BG, 140))
            wash.setColorAt(1, _with_alpha(BG, 165))
        else:
            wash.setColorAt(0, _with_alpha(GLOW_2, 100))
            wash.setColorAt(0.5, _with_alpha(GLOW_3, 132))
            wash.setColorAt(1, _with_alpha(BG, 165))
        painter.fillRect(window.rect(), wash)
        painter.setPen(Qt.NoPen)
        reach = max(width, height)
        for x, y, radius, color, alpha in _lights():
            center = QPointF(x * width, y * height)
            light = QRadialGradient(center, radius * reach)
            light.setColorAt(0, _with_alpha(color, min(255, int(alpha * 1.15))))
            light.setColorAt(0.55, _with_alpha(color, int(alpha * 0.4)))
            light.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setBrush(light)
            painter.drawEllipse(center, radius * reach, radius * reach)
    finally:
        painter.end()


def _paint_title(label):
    """Заголовок «WhoKey» переливом, как ключ на логотипе. Через QSS не выйдет: перелив в color
    Qt для текста не рисует, и заголовок был просто фуксиевым."""
    painter = QPainter(label)
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        font = label.font()
        metrics = QFontMetricsF(font)
        text = label.text()
        size = QSize(int(metrics.horizontalAdvance(text)) + 1, int(metrics.height()))
        box = QStyle.alignedRect(label.layoutDirection(), label.alignment(), size, label.contentsRect())
        path = QPainterPath()
        path.addText(box.left(), 0, font, text)
        # по высоте — по самим буквам, а не по строке шрифта: иначе в низкой подписи хвост «y» обрезался
        area = QRectF(label.contentsRect())
        need = int(path.boundingRect().height()) + 4
        if area.height() < need:  # подпись ниже самих букв — просим место, перерисуется уже целиком
            label.setMinimumHeight(need + label.height() - int(area.height()))
        path.translate(0, area.center().y() - path.boundingRect().center().y())
        bounds = path.boundingRect()
        ink = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        ink.setColorAt(0, QColor(TITLE_START))
        ink.setColorAt(1, QColor(NEON))
        painter.fillPath(path, ink)
    finally:
        painter.end()


def _paint_glass(obj):
    """Рисует элемент жидким стеклом. True — нарисовано, False — пусть рисует сам Qt."""
    if isinstance(obj, QLabel) and obj.property("role") == "title" and not obj.textFormat() == Qt.RichText:
        _paint_title(obj)
    elif _is_glass_button(obj):
        _paint_button(obj)
    elif isinstance(obj, QFrame) and obj.property("role") == "card":
        _paint_card(obj)
    elif isinstance(obj, (QMainWindow, QDialog)) or (isinstance(obj, QWidget) and obj.property("role") == "backdrop"):
        _paint_window(obj)
    else:
        return False
    return True
