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
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import (QBrush, QColor, QCursor, QFont, QFontDatabase, QFontMetricsF, QGradient, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPalette, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QAbstractScrollArea, QAbstractSpinBox, QApplication, QComboBox, QDialog, QFileDialog, QFrame,
                               QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPlainTextEdit,
                               QPushButton, QStyle, QToolButton, QWidget)
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
        if SYSTEM:  # подложку панели Qt рисует ещё до _paint_card: плотная — и рабочий стол не проступает
            GLASS_PANEL = glass(rgba(WHITE, 30), rgba(WHITE, 15), rgba(WHITE, 10))
    elif SYSTEM:  # под стеклом рабочий стол любого цвета: непрозрачная смесь видна серой полосой
        RIM = rgba(ACC_LIGHT, 70)
        HOLLOW = rgba("#05040f", 120)


_derive_colors()


# --- жидкое стекло B (Liquid Glass, оттенок цветами WhoKey) ---
# Каждый кусок стекла рисуется ОДИН раз в готовую картинку — «пластину»: преломлённый фон окна,
# вуаль, оттенок, свечение и тень внутри, блик на кромке. Дальше перерисовка — одно drawPixmap.
# Пластина зависит от места в окне (какой кусок фона под ней), размера, скругления, плотности
# экрана (Retina), темы, вида и состояния — всё это в ключе кэша. Тему сменили — пластины забываем.
# Преломление: у края толстое стекло «поджимает» фон внутрь. Рисуем кольцами: от края к центру
# вложенные скруглённые кольца, в каждом фон растянут чуть сильнее. Фон под стеклом размыт
# (уменьшенная копия), поэтому ступенек между кольцами не видно. numpy не нужен.
# Тень снаружи стекла рисует не сам элемент (он рисует только внутри себя), а тот, на ком он
# лежит: окно, карточка или группа кнопок (_paint_shadows).
# Все числа вида — в одной таблице STYLE_B (её же берёт родное стекло macOS).
LIQUID = True        # False — стекло как раньше (_draw_glass), без пластин
_LENS_SOFT = 0.10    # фон для линзы — копия в 1/10: размытие ~6 px, кольца не видны
_SHADOW_MARGIN = 14  # поле вокруг стекла под тень: 10 px размытия + сдвиг 3
_PLATES = OrderedDict()           # ключ -> пластина (QPixmap)
_PLATE_BYTES = 0
_PLATE_BUDGET = 48 * 1024 * 1024  # памяти на пластины; карточка таблицы на Retina — около 7 МБ
_SHADOWS = OrderedDict()          # ключ -> тень (QPixmap с полями)
_LENS_SOURCES = {}                # (ширина, высота окна) -> размытый фон для линзы
_STYLE_B = {}                     # светлая? -> таблица


def _forget_plates():
    global _PLATE_BYTES
    _PLATES.clear()
    _SHADOWS.clear()
    global _SHADOW_BYTES
    _SHADOW_BYTES = 0
    _LENS_SOURCES.clear()
    _STYLE_B.clear()
    _PLATE_BYTES = 0


# оптика: edge — ширина преломляющего края, lens — сдвиг у самого края (доля edge),
# power — как быстро сдвиг гаснет к центру, zoom — увеличение всего, что под стеклом
_LENS_BIG = dict(edge=14, lens=0.55, power=2.4, zoom=1.00)    # карточка и поля
_LENS_PILL = dict(edge=16, lens=1.45, power=1.8, zoom=1.03)   # кнопки, замок, плашки
# перелив оттенка (по 0.7·x + 0.3·y) и главная кнопка (слева направо)
# Все цвета стекла — из текущей палитры (ACC, MAGENTA…): котик и любая тема перекрашивают и его.
def _mix(first, second, amount):
    """Цвет между first и second: amount=0 — first, 1 — second."""
    a, b = QColor(first), QColor(second)
    return QColor(round(a.red() + (b.red() - a.red()) * amount), round(a.green() + (b.green() - a.green()) * amount),
                  round(a.blue() + (b.blue() - a.blue()) * amount)).name()


def _grad_b(light):
    """Перелив оттенка стекла: три цвета ключа (в светлой теме — пастельнее)."""
    if light:
        return _mix(ACC, WHITE, 0.25), _mix(ACC, WHITE, 0.5), _mix(MAGENTA, WHITE, 0.4)
    return _mix(ACC_DEEP, ACC, 0.2), ACC, MAGENTA


def _accent_b(light):
    """Главная кнопка («+ Добавить», «Сохранить»): слева направо."""
    if light:
        return ACC_DEEP, MAGENTA
    return _mix(ACC_DEEP, ACC, 0.1), _mix(MAGENTA, ACC_DEEP, 0.2)


def _veil_ink(light):
    """Нейтральная вуаль под стеклом: почти фон окна (тёмный) или почти белый (светлый)."""
    return _mix(BG, WHITE, 0.6) if light else _mix(BG, "#000000", 0.15)


def _el(light, lens, base, base_a, tint_a, rim_w=1.4, rim_base=0.10, rim_tl=0.85, rim_br=0.35, glow=0.10,
        inner=0.10, inset=False, sheen=0.04, shadow=10, shadow_dy=3, shadow_a=0.28, hairline=0.0, accent_a=0.0, **extra):
    look = dict(lens, base=base, base_a=base_a, tint_a=tint_a, rim_w=rim_w, rim_base=rim_base, rim_tl=rim_tl,
                rim_br=rim_br, glow=glow, inner=inner, inset=inset, sheen=sheen, shadow=shadow, shadow_dy=shadow_dy,
                shadow_a=shadow_a, hairline=hairline, accent_a=accent_a, **extra)
    if light:  # светлое стекло: ярче кромка, больше свечения, мягче тень, тонкая тёмная линия снаружи
        look.update(rim_base=max(rim_base, 0.22), rim_tl=1.0, glow=glow * 1.6, inner=inner * 0.5,
                    shadow_a=shadow_a * 0.45, hairline=hairline or 0.10)
    return look


def style_b(light=None):
    """Таблица вида стекла B (числа — из макета агента «Look», make_style)."""
    light = LIGHT if light is None else light
    if light in _STYLE_B:
        return _STYLE_B[light]
    dark = not light
    ink = _veil_ink(light)  # нейтральная вуаль
    table = {
        "card": _el(light, _LENS_BIG, ink, 0.22 if dark else 0.30, 0.08 if dark else 0.07, rim_w=1.2, rim_tl=0.60,
                    rim_br=0.25, glow=0.06, inner=0.06, shadow=14, shadow_dy=4, shadow_a=0.22),
        "group": _el(light, _LENS_PILL, ink, 0.22 if dark else 0.30, 0.20 if dark else 0.14),
        # пилюля внутри группы — только при наведении, нажатии и фокусе: «выбранной» кнопки нет
        "group_pill": _el(light, dict(_LENS_PILL, edge=10), "#ffffff", 0.10 if dark else 0.62, 0.18 if dark else 0.12,
                          shadow=4, shadow_dy=1, shadow_a=0.22, glow=0.12),
        "lock": _el(light, _LENS_PILL, ink, 0.16 if dark else 0.30, 0.22 if dark else 0.14),
        "secondary": _el(light, _LENS_PILL, ink, 0.16 if dark else 0.30, 0.20 if dark else 0.14),
        "danger": _el(light, _LENS_PILL, ink, 0.16 if dark else 0.30, 0.0, tint=BAD, tint_solid=0.26 if dark else 0.16),
        "primary": _el(light, _LENS_PILL, ink, 0.0, 0.0, accent_a=0.80 if dark else 0.90, rim_tl=0.80, glow=0.14),
        "search": _el(light, _LENS_BIG, _mix(BG, "#000000", 0.5) if dark else WHITE, 0.30 if dark else 0.52, 0.10 if dark else 0.08,
                      inset=True, inner=0.18, rim_tl=0.45, rim_br=0.55, shadow=0, shadow_a=0.0),
        "field": _el(light, dict(_LENS_BIG, lens=0.6), _mix(BG, "#000000", 0.5) if dark else WHITE, 0.32 if dark else 0.58, 0.06,
                     inset=True, inner=0.18, rim_tl=0.40, rim_br=0.50, shadow=0, shadow_a=0.0),
        "status": _el(light, _LENS_PILL, ink, 0.20 if dark else 0.36, 0.16 if dark else 0.12),
        "row_sel": _el(light, _LENS_BIG, ink, 0.06 if dark else 0.30, 0.30 if dark else 0.20, shadow=0, shadow_a=0.0),
        "group_sep": dict(w=1.0, h=18, a=0.16 if dark else 0.14),
        "hover": dict(tint_da=0.06, rim_k=1.25, glow_k=1.6, accent_da=0.08),
        "pressed": dict(tint_da=0.10, base_da=0.08 if dark else 0.10, rim_k=1.45, glow_k=2.2, touch_a=0.16 if dark else 0.30),
        "disabled": dict(opacity=0.45),
        "focus": dict(ring_w=2.0, ring=(_mix(ACC, WHITE, 0.3), NEON) if dark else (ACC, MAGENTA), ring_a=0.90),
    }
    _STYLE_B[light] = table
    return table


def _state_look(look, state):
    """Вид стекла в состоянии "normal" / "hover" / "pressed" / "disabled"."""
    table = style_b()
    look = dict(look)
    if state == "hover":
        change = table["hover"]
        look.update(tint_a=look["tint_a"] + change["tint_da"], rim_tl=look["rim_tl"] * change["rim_k"],
                    glow=look["glow"] * change["glow_k"])
        if look["accent_a"]:
            look["accent_a"] = min(0.95, look["accent_a"] + change["accent_da"])
    elif state == "pressed":
        change = table["pressed"]
        look.update(tint_a=look["tint_a"] + change["tint_da"], rim_tl=look["rim_tl"] * change["rim_k"],
                    glow=look["glow"] * change["glow_k"], lift=change["base_da"],
                    touch=change["touch_a"] * (0.5 if look["accent_a"] else 1.0))
    elif state == "disabled":
        look.update(lens=0.0, zoom=1.0, shadow_a=look["shadow_a"] * 0.3)
    return look


# --- что стекло и какой формы ---

def _glass_container(widget):
    """На ком лежит стекло (кто рисует его тень): окно, карточка или группа кнопок."""
    parent = widget.parentWidget()
    while parent is not None:
        if parent.isWindow() or parent.property("role") in ("card", "group"):
            return parent
        parent = parent.parentWidget()
    return None


def _state(widget):
    if not widget.isEnabled():
        return "disabled"
    if isinstance(widget, (QPushButton, QToolButton)) and widget.isDown():
        return "pressed"
    if widget.underMouse() and isinstance(widget, (QPushButton, QToolButton, QComboBox)):
        return "hover"
    return "normal"


def _glass_shape(widget):
    """(вид из STYLE_B, состояние, прямоугольник в координатах элемента, скругление) или None — не стекло."""
    table = style_b()
    rect = QRectF(widget.rect())
    state = _state(widget)
    name = widget.property("role")
    if isinstance(widget, QFrame) and name == "card":
        return table["card"], "normal", rect, CARD_RADIUS
    if isinstance(widget, QFrame) and name == "group":
        return table["group"], "normal", rect, rect.height() / 2
    if isinstance(widget, QLabel) and name == "status":
        return table["status"], "normal", rect, rect.height() / 2
    if isinstance(widget, (QPushButton, QToolButton)) and _is_glass_button(widget):
        look = widget.property("kind")
        if look == "segment":  # кнопка в группе: пилюлю рисует сама кнопка, плавно (_paint_segment_pill)
            return None
        if look in ("primary", "danger"):
            return table[look], state, rect, rect.height() / 2
        round_ = isinstance(widget, QToolButton) or len(widget.text()) == 1
        return table["lock" if round_ else "secondary"], state, rect, rect.height() / 2
    if isinstance(widget, (QLineEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox)) and _glass_field(widget):
        if isinstance(widget, QComboBox):
            return table["secondary"], state, rect, rect.height() / 2
        if name == "search":
            return table["search"], "disabled" if state == "disabled" else "normal", rect, rect.height() / 2
        return table["field"], "disabled" if state == "disabled" else "normal", rect, 12
    return None


def _glass_field(widget):
    """Поле ввода, под которым рисуем стекло (строка внутри поля-числа или списка — нет)."""
    parent = widget.parentWidget()
    return not isinstance(parent, (QAbstractSpinBox, QComboBox))


# --- линза и пластина ---

def _lens_source(window):
    """Что видно сквозь стекло: (размытый фон окна, его пикселей в логическом пикселе) или None.
    При системном стекле macOS под окном рабочий стол — его не прочитать, преломлять нечего."""
    if _see_through():
        return None
    width, height = max(1, window.width()), max(1, window.height())
    key = (width, height)
    if key not in _LENS_SOURCES:
        if len(_LENS_SOURCES) >= _SCENE_LIMIT:
            _LENS_SOURCES.clear()
        sharp = _scene(width, height)[0]
        _LENS_SOURCES[key] = sharp.scaled(max(1, round(width * _LENS_SOFT)), max(1, round(height * _LENS_SOFT)),
                                          Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    source = _LENS_SOURCES[key]
    return source, source.width() / width


def _lens_rings(width, height, radius, look, rings=10):
    """(отступ от края, на сколько там поджат фон) для каждого кольца — логические пиксели."""
    edge = min(look["edge"], radius, height / 2, width / 2)
    steps = [(edge * k / rings, look["lens"] * edge * (1 - (k + 0.5) / rings) ** look["power"]) for k in range(rings)]
    return steps + [(edge, 0.0)]


def _rounded(rect, radius, inset=0.0):
    path = QPainterPath()
    path.addRoundedRect(rect.adjusted(inset, inset, -inset, -inset), max(0.0, radius - inset), max(0.0, radius - inset))
    return path


def _paint_lens(painter, under, area, rect, radius, look):
    """Преломлённый фон: area — где стекло в окне, rect — куда рисовать (логические пиксели)."""
    source, scale = under
    width, height = area.width() / look["zoom"], area.height() / look["zoom"]
    base = QRectF(area.center().x() - width / 2, area.center().y() - height / 2, width, height)
    for inset, shift in _lens_rings(rect.width(), rect.height(), radius, look):
        grab = base.adjusted(shift, shift, -shift, -shift)  # кусок фона меньше — у края он растянут
        if grab.width() <= 1 or grab.height() <= 1:
            continue
        painter.save()
        painter.setClipPath(_rounded(rect, radius, inset), Qt.IntersectClip)
        painter.drawPixmap(rect, source, QRectF(grab.x() * scale, grab.y() * scale, grab.width() * scale, grab.height() * scale))
        painter.restore()


def _bands(painter, rect, radius, depth, strength, start, end, color, bands=6):
    """Свечение или тень у края внутри стекла: полосы вглубь на depth, сила по strength(доля глубины),
    по направлению — линейный перелив от start (полная сила) к end (сила 0.35·…)."""
    for k in range(bands):
        alpha = strength((k + 0.5) / bands)
        if alpha <= 0.002:
            continue
        band = _rounded(rect, radius, depth * k / bands).subtracted(_rounded(rect, radius, depth * (k + 1) / bands))
        light = QLinearGradient(start, end)
        light.setColorAt(0, _with_alpha(color, int(255 * min(1.0, alpha))))
        light.setColorAt(1, _with_alpha(color, int(255 * min(1.0, alpha * 0.35))))
        painter.fillPath(band, light)


def _paint_b(painter, rect, radius, look):
    """Всё, что над преломлённым фоном: вуаль, акцент, оттенок, свечение, тень внутри, блик на кромке."""
    shape = _rounded(rect, radius)
    painter.fillPath(shape, _with_alpha(look["base"], int(255 * look["base_a"])))
    if look["accent_a"]:  # главная кнопка: индиго → фуксия слева направо
        accent = QLinearGradient(rect.topLeft(), rect.topRight())
        first, last = _accent_b(LIGHT)
        accent.setColorAt(0, _with_alpha(first, int(255 * look["accent_a"])))
        accent.setColorAt(1, _with_alpha(last, int(255 * look["accent_a"])))
        painter.fillPath(shape, accent)
    if look.get("tint_solid"):
        painter.fillPath(shape, _with_alpha(look["tint"], int(255 * look["tint_solid"])))
    if look["tint_a"] > 0:  # оттенок B: три цвета ключа по диагонали 0.7·x + 0.3·y
        gx, gy = 0.7 / max(rect.width(), 1), 0.3 / max(rect.height(), 1)
        norm = gx * gx + gy * gy
        tint = QLinearGradient(rect.topLeft(), rect.topLeft() + QPointF(gx / norm, gy / norm))
        for stop, color in zip((0, 0.5, 1), _grad_b(LIGHT)):
            tint.setColorAt(stop, _with_alpha(color, int(255 * min(1.0, look["tint_a"]))))
        painter.fillPath(shape, tint)
    if look.get("lift"):
        painter.fillPath(shape, _with_alpha(WHITE, int(255 * look["lift"])))
    top_left, bottom_right = rect.topLeft(), rect.topLeft() + QPointF(min(rect.width(), rect.height() * 3), rect.height())
    edge = min(look["edge"], radius, rect.height() / 2)
    if look["sheen"]:
        sheen = QLinearGradient(rect.topLeft(), QPointF(rect.x(), rect.y() + rect.height() / 2))
        sheen.setColorAt(0, _with_alpha(WHITE, int(255 * look["sheen"])))
        sheen.setColorAt(1, _with_alpha(WHITE, 0))
        painter.fillPath(shape, sheen)
    if look["glow"]:  # свет внутри у края, сильнее сверху слева
        _bands(painter, rect, radius, edge, lambda u: look["glow"] * (1 - u) ** 3, top_left, bottom_right, WHITE)
    if look["inner"]:  # выпуклая кнопка темнее снизу справа, поле (впадина) — сверху слева
        depth = edge * (0.6 if look["inset"] else 1.0)
        start, end = (top_left, bottom_right) if look["inset"] else (rect.bottomRight(), rect.topLeft())
        _bands(painter, rect, radius, depth, lambda u: look["inner"] * (1 - u) ** 2, start, end, "#000000", bands=4)
    if look.get("touch"):  # нажатие — пятно света под пальцем
        touch = QRadialGradient(QPointF(rect.x() + rect.width() * 0.38, rect.center().y()), rect.height() * 0.9)
        touch.setColorAt(0, _with_alpha(WHITE, int(255 * look["touch"])))
        touch.setColorAt(1, _with_alpha(WHITE, 0))
        painter.fillPath(shape, touch)
    # блик на кромке: верх ярко, низ слабее, левый бок чуть светлее правого
    rim = lambda value: _with_alpha(WHITE, int(255 * min(1.0, value)))  # noqa: E731
    soft = 0.6  # блик гаснет поперёк кромки: в среднем ~60 % от яркости у самого края
    base, top, bottom = look["rim_base"] * soft, look["rim_tl"] * 0.67 * soft, look["rim_br"] * 0.61 * soft
    vertical = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    vertical.setColorAt(0, rim(base + top))
    vertical.setColorAt(0.5, rim(base))
    vertical.setColorAt(1, rim(base + bottom))
    width = look["rim_w"]
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(vertical, width))
    painter.drawPath(_rounded(rect, radius, width / 2))
    side = QLinearGradient(rect.topLeft(), QPointF(rect.x() + min(rect.width() * 0.3, 60), rect.y()))
    side.setColorAt(0, rim(look["rim_tl"] * 0.3 * soft))
    side.setColorAt(1, rim(0))
    painter.setPen(QPen(side, width))
    painter.drawPath(_rounded(rect, radius, width / 2))


def _plate(widget, rect, radius, dpr, look, state):
    """Пластина стекла из кэша или новая (координаты rect — элемента)."""
    global _PLATE_BYTES
    window = widget.window()
    corner = widget.mapTo(window, QPoint(0, 0))
    key = (LIGHT, SYSTEM, window.width(), window.height(), corner.x(), corner.y(), rect.x(), rect.y(),
           rect.width(), rect.height(), radius, dpr, state, tuple(sorted((k, str(v)) for k, v in look.items())))
    plate = _PLATES.get(key)
    if plate is not None:
        _PLATES.move_to_end(key)
        return plate
    width, height = max(1, round(rect.width() * dpr)), max(1, round(rect.height() * dpr))
    local = QRectF(0, 0, rect.width(), rect.height())
    plate = QPixmap(width, height)
    plate.setDevicePixelRatio(dpr)
    plate.fill(Qt.transparent)
    painter = QPainter(plate)
    try:
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        under = _lens_source(window)
        if under is not None:
            # фон рисуем в отдельный слой, а слой кладём по форме стекла: так край сглажен
            layer = QPixmap(width, height)
            layer.setDevicePixelRatio(dpr)
            layer.fill(Qt.transparent)
            lens = QPainter(layer)
            try:
                lens.setRenderHint(QPainter.SmoothPixmapTransform)
                area = QRectF(corner.x() + rect.x(), corner.y() + rect.y(), rect.width(), rect.height())
                _paint_lens(lens, under, area, local, radius, look)
            finally:
                lens.end()
            painter.fillPath(_rounded(local, radius), QBrush(layer))  # слой той же плотности — пиксель в пиксель
        _paint_b(painter, local, radius, look)
    finally:
        painter.end()
    _PLATES[key] = plate
    _PLATE_BYTES += width * height * 4
    while _PLATE_BYTES > _PLATE_BUDGET and len(_PLATES) > 1:
        dropped = _PLATES.popitem(last=False)[1]
        _PLATE_BYTES -= dropped.width() * dropped.height() * 4
    return plate


def _shadow(width, height, radius, look, dpr):
    """Мягкая тень под стеклом (и тонкая тёмная линия у светлого) — картинка с полями _SHADOW_MARGIN."""
    key = (round(width, 2), round(height, 2), round(radius, 2), look["shadow"], look["shadow_dy"],
           round(look["shadow_a"], 3), look["hairline"], dpr)
    found = _SHADOWS.get(key)
    if found is not None:
        return found
    margin = _SHADOW_MARGIN
    full = QRectF(0, 0, width + 2 * margin, height + 2 * margin)
    shape = QRectF(margin, margin, width, height)
    # размытие: рисуем в мелкой картинке и растягиваем плавно
    blur = max(1.0, look["shadow"] / 2.5)
    small = QPixmap(max(1, round(full.width() / blur)), max(1, round(full.height() / blur)))
    small.fill(Qt.transparent)
    painter = QPainter(small)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(1 / blur, 1 / blur)
    painter.fillPath(_rounded(shape.translated(0, look["shadow_dy"]), radius), _with_alpha("#000000", int(255 * look["shadow_a"])))
    painter.end()
    shadow = QPixmap(round(full.width() * dpr), round(full.height() * dpr))
    shadow.setDevicePixelRatio(dpr)
    shadow.fill(Qt.transparent)
    painter = QPainter(shadow)
    painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    outside = QPainterPath()
    outside.addRect(full)
    outside = outside.subtracted(_rounded(shape, radius))
    painter.setClipPath(outside)  # под стеклом тени нет: при системном стекле её было бы видно сквозь него
    painter.drawPixmap(full, small, QRectF(small.rect()))
    if look["hairline"]:
        painter.setPen(QPen(_with_alpha("#000000", int(255 * look["hairline"] * 0.9)), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(_rounded(shape, radius, -0.75))
    painter.end()
    _remember_shadow(key, shadow)
    return shadow


_SHADOW_BUDGET = 16 * 1024 * 1024  # тени и плашки строк: при растягивании окна копились бы новые размеры
_SHADOW_BYTES = 0


def _remember_shadow(key, pixmap):
    global _SHADOW_BYTES
    _SHADOWS[key] = pixmap
    _SHADOW_BYTES += pixmap.width() * pixmap.height() * 4
    while _SHADOW_BYTES > _SHADOW_BUDGET and len(_SHADOWS) > 1:
        _, old = _SHADOWS.popitem(last=False)
        _SHADOW_BYTES -= old.width() * old.height() * 4


def paint_row_glass(painter, row, clip):
    """Выделенная строка таблицы — стеклянной плашкой (row — вся строка, clip — ячейка, которую рисуют)."""
    device = painter.device()
    dpr = device.devicePixelRatio() if device is not None else 1.0
    radius = row.height() / 2
    key = ("row", LIGHT, round(row.width(), 1), round(row.height(), 1), dpr)
    plate = _SHADOWS.get(key)
    if plate is None:
        plate = QPixmap(max(1, round(row.width() * dpr)), max(1, round(row.height() * dpr)))
        plate.setDevicePixelRatio(dpr)
        plate.fill(Qt.transparent)
        p = QPainter(plate)
        p.setRenderHint(QPainter.Antialiasing)
        _paint_b(p, QRectF(0, 0, row.width(), row.height()), radius, style_b()["row_sel"])
        p.end()
        _remember_shadow(key, plate)
    painter.save()
    painter.setClipRect(clip)
    painter.drawPixmap(row.topLeft(), plate)
    painter.restore()


def _paint_shadows(painter, container):
    """Тени стёкол, лежащих на container (окне, карточке, группе), — до самих стёкол."""
    device = painter.device()
    dpr = device.devicePixelRatio() if device is not None else 1.0
    for child in container.findChildren(QWidget):
        if not child.isVisible() or child.isWindow() or _glass_container(child) is not container:
            continue
        shape = _glass_shape(child)
        if shape is None:
            continue
        look, state, rect, radius = shape
        look = _state_look(look, state)
        if look["shadow_a"] <= 0 and not look["hairline"]:
            continue
        corner = child.mapTo(container, QPoint(0, 0))
        place = rect.translated(corner.x() - _SHADOW_MARGIN, corner.y() - _SHADOW_MARGIN)
        painter.drawPixmap(place.topLeft(), _shadow(rect.width(), rect.height(), radius, look, dpr))


def _glass_b(painter, widget, shape=None):
    """Рисует стекло элемента пластиной (и рамку фокуса). False — элемент не стекло."""
    shape = shape or _glass_shape(widget)
    if shape is None:
        return False
    look, state, rect, radius = shape
    device = painter.device()
    dpr = device.devicePixelRatio() if device is not None else 1.0
    plate = _plate(widget, rect, radius, dpr, _state_look(look, state), state)
    painter.save()
    if state == "disabled":
        painter.setOpacity(style_b()["disabled"]["opacity"])
    painter.drawPixmap(rect.topLeft(), plate)
    painter.restore()
    focus = widget.hasFocus() and widget.focusPolicy() != Qt.NoFocus
    invalid = widget.property("invalid") is True
    if focus or invalid:
        ring = style_b()["focus"]
        pen = QLinearGradient(rect.topLeft(), rect.topRight())
        first, last = (BAD_INK, BAD_INK) if invalid else ring["ring"]
        pen.setColorAt(0, _with_alpha(first, int(255 * ring["ring_a"])))
        pen.setColorAt(1, _with_alpha(last, int(255 * ring["ring_a"])))
        painter.setPen(QPen(pen, ring["ring_w"]))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(_rounded(rect, radius, ring["ring_w"] / 2))
    return True


PILL_MS = 220          # пилюля в группе кнопок: появляется и гаснет за столько мс
PILL_INSET = 2         # пилюля почти во всю высоту группы: тонкий зазор до кромки капсулы
ANIMATE = True         # False — сразу конечное состояние (снимки в тестах)


def pill_progress(button):
    """Насколько видна пилюля кнопки в группе: 0..1, плавно к цели (наведение, нажатие, фокус)."""
    target = 1.0 if _segment_active(button) else 0.0
    if not ANIMATE:
        button._pill = target
        return target
    current = getattr(button, "_pill", 0.0)
    if getattr(button, "_pill_target", None) != target:
        button._pill_target = target
        animation = getattr(button, "_pill_anim", None)
        if animation is None:
            animation = QVariantAnimation(button)
            animation.setEasingCurve(QEasingCurve.OutCubic)

            def step(value, button=button):
                button._pill = float(value)
                button.update()
                if button.parentWidget() is not None:
                    button.parentWidget().update()  # разделители гаснут вместе с ней
            animation.valueChanged.connect(step)
            button._pill_anim = animation
        animation.stop()
        animation.setStartValue(current)
        animation.setEndValue(target)
        animation.setDuration(max(1, int(PILL_MS * abs(target - current))))
        animation.start()
    return current


def _paint_segment_pill(painter, button):
    """Пилюля внутри группы: проступает и чуть подрастает (92 % → 100 %), гаснет так же мягко."""
    progress = pill_progress(button)
    if progress <= 0.001 or not button.isEnabled():
        return
    state = _state(button)
    state = state if state in ("hover", "pressed") else "hover"
    inner = QRectF(button.rect()).adjusted(PILL_INSET, PILL_INSET, -PILL_INSET, -PILL_INSET)
    painter.save()
    painter.setOpacity(progress)
    center = inner.center()
    scale = 0.92 + 0.08 * progress
    painter.translate(center)
    painter.scale(scale, scale)
    painter.translate(-center)
    _glass_b(painter, button, (style_b()["group_pill"], state, inner, inner.height() / 2))
    painter.restore()


def _paint_button_b(button):
    painter = QPainter(button)
    try:
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        if button.property("kind") == "segment":
            _paint_segment_pill(painter, button)
        else:
            _glass_b(painter, button)
        look = button.property("kind")
        ink = QColor(ON_ACCENT if look == "primary" else BAD_INK if look == "danger" else TEXT)
        if not button.isEnabled():
            ink = QColor(FAINT)
        _button_label(painter, button, QRectF(button.rect()), ink)
    finally:
        painter.end()


def _paint_card_b(card):
    painter = QPainter(card)
    try:
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        _glass_b(painter, card)
        _paint_shadows(painter, card)
    finally:
        painter.end()


def _segment_active(button):
    return button.isEnabled() and (button.isDown() or button.underMouse() or button.hasFocus())


def _paint_group_b(group):
    """Группа кнопок — одна капсула; между кнопками — разделители, рядом с пилюлей они прячутся."""
    painter = QPainter(group)
    try:
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        _glass_b(painter, group)
        buttons = sorted((child for child in group.findChildren(QPushButton) if child.isVisible()), key=lambda b: b.x())
        sep = style_b()["group_sep"]
        color = _with_alpha(SHADOW if LIGHT else WHITE, int(255 * sep["a"]))
        for left, right in zip(buttons, buttons[1:]):
            near = max(getattr(left, "_pill", 0.0), getattr(right, "_pill", 0.0))
            if near >= 0.999:
                continue
            x = (left.geometry().right() + 1 + right.x()) / 2
            painter.save()
            painter.setOpacity(1 - near)  # разделитель гаснет, пока рядом проступает пилюля
            painter.fillRect(QRectF(x - sep["w"] / 2, (group.height() - sep["h"]) / 2, sep["w"], sep["h"]), color)
            painter.restore()
        _paint_shadows(painter, group)
    finally:
        painter.end()


def _paint_window_b(window):
    if _see_through() and window.isWindow():
        _paint_wash(window)
    else:
        painter = QPainter(window)
        try:
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            sharp = _scene(window.width(), window.height())[0]
            painter.drawPixmap(window.rect(), sharp, sharp.rect())
        finally:
            painter.end()
    painter = QPainter(window)
    try:
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        _paint_shadows(painter, window)
    finally:
        painter.end()


def _paint_under(widget):
    """Поле ввода, список, плашка: стекло под ними, а текст и курсор Qt рисует сам (False)."""
    painter = QPainter(widget)
    try:
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        _glass_b(painter, widget)
    finally:
        painter.end()
    return False


def button_group(buttons):
    """Кнопки одной капсулой (шапка окна): равной ширины, пилюля при наведении."""
    group = role(QFrame(), "group")
    row = QHBoxLayout(group)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    width = max(button.sizeHint().width() for button in buttons) + 40  # пилюле есть место по бокам
    for button in buttons:
        kind(button, "segment")
        # фокус — только с клавиатуры (Tab): после щелчка пилюля не должна оставаться гореть
        button.setFocusPolicy(Qt.TabFocus)
        button.setMinimumWidth(width)
        row.addWidget(button)
    return group


def _paint_liquid(obj):
    """Жидкое стекло B: True — нарисовано, False — пусть рисует Qt (поверх уже лежит стекло), None — не наше."""
    if not LIQUID:
        return None
    if isinstance(obj, QLabel) and obj.property("role") == "title" and not obj.textFormat() == Qt.RichText:
        _paint_title(obj)
        return True
    if _is_glass_button(obj):
        _paint_button_b(obj)
        return True
    if isinstance(obj, QFrame) and obj.property("role") == "card":
        _paint_card_b(obj)
        return True
    if isinstance(obj, QFrame) and obj.property("role") == "group":
        _paint_group_b(obj)
        return True
    if isinstance(obj, (QMainWindow, QDialog)) or (isinstance(obj, QWidget) and obj.property("role") == "backdrop"):
        _paint_window_b(obj)
        return True
    if (isinstance(obj, QLabel) and obj.property("role") == "status") or (
            isinstance(obj, (QLineEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox)) and _glass_field(obj)):
        return _paint_under(obj)
    return None


POPUP_RADIUS = 14  # скругление меню и выпадающих списков


def _popup_style():
    """Меню правого клика и выпадающие списки — стеклом B. На Mac под ними настоящее размытие
    (sysglass), поэтому заливка тоньше; на Windows/Linux размытия нет — заливка плотнее, чтобы читалось."""
    # тонкая заливка — только когда под меню действительно легло размытие macOS (glassAttached);
    # иначе почти сплошная: сквозь меню не должен читаться текст таблицы
    if LIGHT:
        fill, thin = rgba(_veil_ink(True), 235), rgba(_veil_ink(True), 150)
        rim, line = rgba(WHITE, 230), rgba(SHADOW, 30)
        pick = f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {rgba(ACC, 46)}, stop:1 {rgba(MAGENTA, 38)})"
        pick_rim, pick_ink = rgba(WHITE, 240), TEXT
    else:
        fill, thin = rgba(_veil_ink(False), 232), rgba(_veil_ink(False), 120)
        rim, line = rgba(WHITE, 46), rgba(WHITE, 26)
        pick = f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {rgba(ACC, 95)}, stop:1 {rgba(MAGENTA, 80)})"
        pick_rim, pick_ink = rgba(WHITE, 60), WHITE
    return f"""
QMenu, QComboBox QAbstractItemView {{
    background: {fill}; border: 1px solid {rim}; border-radius: {POPUP_RADIUS}px; padding: 6px; }}
QMenu[glassAttached="true"], QComboBoxPrivateContainer[glassAttached="true"] QAbstractItemView {{ background: {thin}; }}
QMenu::item, QComboBox QAbstractItemView::item {{
    padding: 7px 22px 7px 14px; border-radius: 9px; border: 1px solid transparent; background: transparent; }}
QMenu::item:selected, QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover {{
    background: {pick}; border: 1px solid {pick_rim}; color: {pick_ink}; }}
QMenu::separator {{ height: 1px; background: {line}; margin: 5px 10px; }}
"""


def _liquid_style():
    """Правила QSS для жидкого стекла: фон и рамки рисует стекло, Qt — только текст."""
    return _popup_style() + f"""
QPushButton, QToolButton, QPushButton:hover, QToolButton:hover, QPushButton:pressed, QToolButton:pressed,
QPushButton:focus, QToolButton:focus, QPushButton:disabled, QToolButton:checked,
QPushButton[kind="primary"], QPushButton[kind="primary"]:hover, QPushButton[kind="primary"]:pressed,
QPushButton[kind="danger"], QPushButton[kind="danger"]:pressed {{ background: transparent; border: none; }}
QPushButton {{ padding: 8px 18px; }}
QPushButton#lock, QPushButton#lock:pressed {{ padding: 0; }}
QPushButton:pressed {{ padding: 8px 18px; }}
QLineEdit, QSpinBox, QPlainTextEdit, QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus,
QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"] {{ background: transparent; border: none; }}
QLineEdit, QSpinBox {{ padding: 8px 12px; }}
QLineEdit[role="search"] {{ padding: 10px 16px; }}
QAbstractSpinBox QLineEdit, QComboBox QLineEdit {{ padding: 0; }}
QComboBox, QComboBox:hover, QComboBox:focus {{ background: transparent; border: none; padding: 6px 14px; }}
QFrame[role="card"], QFrame[role="group"] {{ background: transparent; border: none; }}
QLabel[role="status"] {{ color: {MUTED}; padding: 5px 14px; }}
"""


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

/* меню скруглено (см. rounded_menu). Почти непрозрачно, пока под ним нет размытия macOS
   (жидкое стекло: _popup_style, glassAttached) — иначе сквозь меню читался бы текст таблицы */
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
""" if SYSTEM and not LIGHT else "") + (_light_style() if LIGHT else "") + (_liquid_style() if LIQUID else "")


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
    _SCENES.clear()
    _forget_plates()  # пластины стекла нарисованы цветами старой темы
    STYLE = _style()


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
    if not LIQUID:  # жидкое стекло не светится
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
        if LIQUID and isinstance(obj, QPushButton) and obj.property("kind") == "segment" and kind in (
                QEvent.Enter, QEvent.Leave, QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.FocusIn,
                QEvent.FocusOut, QEvent.EnabledChange) and obj.parentWidget() is not None:
            obj.parentWidget().update()  # разделители прячутся рядом с пилюлей, тень пилюли — на группе
        if LIQUID:
            return  # неоновых ореолов у жидкого стекла нет: нажатие и фокус видны на самом стекле
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
    if window.property("glassPopup") is True or window.windowType() == Qt.Popup:
        # меню и выпадающие списки не тянем: нажатие на пункт меню — это выбор пункта (ревью 1.11.0)
        return False
    # нажатие, которое элемент не взял (ссылка, поле), Qt передаёт родителю — такое окно не тянет
    target = window.childAt(window.mapFromGlobal(event.globalPosition().toPoint())) or window
    if obj is not target:
        return False
    if obj is not window and type(obj) not in (QWidget, QFrame, QLabel) and obj.metaObject().className() != "QStatusBar":
        return False
    parent = obj.parentWidget()
    while parent is not None and parent is not window:  # область таблицы, заметки, списка — простой QWidget
        if isinstance(parent, QAbstractScrollArea):    # (viewport), но нажатие нужно им самим
            return False
        parent = parent.parentWidget()
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
    menu.setProperty("glassPopup", True)  # стекло: на Mac под ним размытие рабочего стола (sysglass)
    menu.setProperty("glassRadius", POPUP_RADIUS)
    return menu


def rounded_popup(combo):
    """То же для выпадающего списка: его окошко (контейнер списка) делаем прозрачным."""
    combo.setStyleSheet("QComboBox { combobox-popup: 0; }")  # список под полем, а не поверх него
    popup = combo.view().window()
    popup.setWindowFlags(popup.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    popup.setAttribute(Qt.WA_TranslucentBackground)
    popup.setProperty("glassPopup", True)
    popup.setProperty("glassRadius", POPUP_RADIUS)
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
    if name == "primary" and not LIQUID:  # у жидкого стекла неонового ореола нет
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
        if LIQUID:  # жидкое стекло: фон окна спокойнее (вуаль); преломляются пятна света под ней
            painter.fillRect(sharp.rect(), _with_alpha(_veil_ink(True) if LIGHT else _mix(BG, ACC, 0.16), 90 if LIGHT else 140))
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
        _button_label(painter, button, rect, ink)
    finally:
        painter.end()


def _button_label(painter, button, rect, ink):
    """Надпись или значок кнопки по центру."""
    enabled = button.isEnabled()
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
            # при системном стекле изморозь тоньше: иначе панель почти белая и рабочий стол не проступает
            _draw_glass(painter, card, rect, CARD_RADIUS, _with_alpha(WHITE, 30), dark=60 if _see_through() else 175,
                        sheen=90, rim_top=230, rim_bottom=200, depth_alpha=8)
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
        if LIGHT:  # под ней светлая изморозь macOS: дымка лишь выравнивает тон, чтобы текст читался.
            # Вдвое тоньше прежней (1.12, выбрано вживую): сквозь окно видно очертания рабочего стола
            wash.setColorAt(0, _with_alpha(GLOW_1, 35))
            wash.setColorAt(0.5, _with_alpha(BG, 47))
            wash.setColorAt(1, _with_alpha(BG, 60))
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
            if LIGHT:  # пастельные пятна тоже вдвое слабее — как в пробном окне
                light.setColorAt(0, _with_alpha(color, min(255, int(alpha * 0.575))))
            else:
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
    try:
        liquid = _paint_liquid(obj)
    except Exception:  # стекло B не нарисовалось — рисуем прежнее
        traceback.print_exc()
        liquid = None
    if liquid is not None:
        return liquid
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
