"""Оформление: почти чёрный фон с фиолетовым заревом, лавандовый неон и
«стекло» в духе Liquid Glass, моноширинный шрифт MesloLGS Nerd Font.

Цвета взяты из CSS-переменных chat.eblo.id (--bg, --surf, --acc и т.д.);
лавандовые оттенки сдвинуты на 15° к розовому (по просьбе).
Стекло: полупрозрачные панели, кнопки и поля со скруглёнными углами и светлой
кромкой сверху — сквозь них видно зарево фона. Настоящее Liquid Glass (с
размытием и преломлением того, что под ним) macOS рисует только для своих
родных элементов, в Qt его нет — поэтому стекло нарисовано прозрачностью.
"""

import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QLinearGradient, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QGraphicsDropShadowEffect, QLineEdit, QWidget
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



def rgba(color, alpha):
    """Цвет с прозрачностью для оформления Qt: rgba("#caa7f0", 80). alpha — от 0 до 255."""
    color = color.lstrip("#")
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def solid(color, alpha, over="#1f1329"):
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


GLASS = glass(rgba(WHITE, 52), rgba(WHITE, 24), rgba(WHITE, 12))
GLASS_HOVER = glass(rgba(WHITE, 72), rgba(WHITE, 36), rgba(WHITE, 20))
GLASS_PANEL = glass(rgba(WHITE, 24), rgba(WHITE, 10), rgba(WHITE, 4))
GLASS_ACC = glass(rgba(ACC_LIGHT, 150), rgba(ACC, 105), rgba(ACC_DEEP, 70))
GLASS_ACC_HOVER = glass(rgba(ACC_LIGHT, 190), rgba(ACC, 145), rgba(ACC_DEEP, 105))
GLASS_BAD = glass(rgba(BAD, 90), rgba(BAD, 50), rgba(BAD, 28))
RIM = solid(WHITE, 40)       # кромка стекла
RIM_HOVER = solid(WHITE, 75)
RIM_ACC = solid(ACC_LIGHT, 150)
RIM_CARD = solid(ACC, 120)
HOLLOW = rgba("#000000", 95) # «углубление» поля ввода

STYLE = f"""
/* шрифт — здесь, а не только через app.setFont: на macOS Qt ставит кнопкам, подписям
   и таблице системный шрифт отдельно, и общий шрифт приложения до них не доходил */
QWidget {{ color: {TEXT}; font-family: "{FONT_FAMILY}"; font-size: {FONT_SIZE}px; }}
/* фиолетовое зарево сверху окна — как неоновая подсветка; его видно сквозь стекло */
QMainWindow, QDialog, QWidget[role="backdrop"] {{
    background: qradialgradient(cx:0.5, cy:-0.15, radius:1.1, fx:0.5, fy:-0.15,
                                stop:0 #3f2160, stop:0.45 #1a1024, stop:1 {BG}); }}
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: {FONT_SIZE * 2 + 2}px; font-weight: 800; color: {NEON}; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="error"] {{ color: {BAD_INK}; }}
QLabel[role="accent"] {{ color: {ACC}; font-weight: 600; }}

QFrame[role="card"] {{
    background: {GLASS_PANEL}; border: 1px solid {RIM_CARD}; border-radius: {CARD_RADIUS}px; }}
QFrame[role="card"] QLabel, QFrame[role="card"] QCheckBox {{ background: transparent; }}

QLineEdit, QSpinBox {{
    background: {HOLLOW}; border: 1px solid {RIM}; border-radius: {FIELD_RADIUS}px;
    padding: 7px 10px; selection-background-color: {ACC_DEEP}; }}
QLineEdit:focus, QSpinBox:focus {{ border-color: {ACC}; }}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; background: transparent; width: 18px; }}
QSpinBox::up-arrow {{ image: url("{ARROW_UP_FILE}"); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url("{ARROW_FILE}"); width: 10px; height: 10px; }}

QPushButton {{
    background: {GLASS}; border: 1px solid {RIM};
    border-radius: {BUTTON_RADIUS}px; padding: 7px 16px; font-weight: 600; }}
QPushButton:hover {{ background: {GLASS_HOVER}; border-color: {RIM_HOVER}; }}
QPushButton:pressed {{ background: {rgba(WHITE, 8)}; }}
QPushButton:disabled {{ color: {FAINT}; background: {rgba(WHITE, 8)}; border-color: {solid(WHITE, 20)}; }}
QPushButton[kind="primary"] {{
    background: {GLASS_ACC}; border-color: {RIM_ACC}; color: {WHITE}; }}
QPushButton[kind="primary"]:hover {{ background: {GLASS_ACC_HOVER}; border-color: {NEON}; }}
QPushButton[kind="danger"] {{ background: {GLASS_BAD}; border-color: {solid(BAD_INK, 110)}; color: {BAD_INK}; }}

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
            self._handle(obj, event)
        except Exception:
            traceback.print_exc()
        return False  # событие идёт дальше как обычно

    def _handle(self, obj, event):
        kind = event.type()
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
