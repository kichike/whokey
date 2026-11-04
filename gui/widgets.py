"""Общие элементы окон: поле пароля с «глазом», шкала надёжности, генератор,
и короткие функции для стандартных окошек-вопросов."""

import ctypes
import math
import sys
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QLinearGradient, QPainter, QPalette
from PySide6.QtWidgets import (QCheckBox, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                               QProgressBar, QPushButton, QSpinBox, QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QToolButton, QVBoxLayout, QWidget)

import csv_io
from vault import VaultTooLarge
from generator import MAX_LENGTH, MIN_LENGTH, entropy_bits, estimate_bits, generate_password
from gui import prefs, theme
from gui.i18n import tr

# Цвета шкалы надёжности — «светофор» из оформления: хорошо / так себе / плохо
GOOD, WARNING, BAD = theme.OK, theme.WARN, theme.BAD




class SecretEdit(QLineEdit):
    """Строка ввода пароля, из которой нельзя скопировать «мимо» нашего буфера.

    Обычный QLineEdit после «глаза» даёт скопировать пароль ⌘C прямо в
    системный буфер — и там он остался бы навсегда. Здесь «Копировать» и
    «Вырезать» (клавишами и из меню) идут через copy_password — то есть через
    clipboard.py с автоочисткой. Если copy_password не задан (мастер-пароль),
    копирование просто не работает.
    """

    def __init__(self, copy_password=None):
        super().__init__()
        self.copy_password = copy_password
        self.setDragEnabled(False)  # и перетащить выделенный пароль мышью тоже нельзя

    def _copy_out(self):
        if self.copy_password and self.text():
            self.copy_password(self.text())

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy) or event.matches(QKeySequence.Cut):
            self._copy_out()  # «вырезать» тоже только копирует: пароль из поля не пропадает
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        # своё меню вместо стандартного: в стандартном «Копировать» шло бы мимо нас
        menu = theme.rounded_menu(QMenu(self))
        if self.copy_password:
            menu.addAction(tr("Copy password"), self._copy_out).setEnabled(bool(self.text()))
        menu.addAction(tr("Paste"), self.paste).setEnabled(not self.isReadOnly())
        menu.addAction(tr("Select all"), self.selectAll)
        menu.exec(event.globalPos())


def caps_lock_on():
    """Включён ли Caps Lock (macOS и Windows; на остальных — «не знаем», False)."""
    try:
        if sys.platform == "darwin":
            from AppKit import NSEvent  # PyObjC, ставится вместе с Touch ID (requirements.txt)
            return bool(NSEvent.modifierFlags() & (1 << 16))  # NSEventModifierFlagCapsLock
        if sys.platform == "win32":
            return bool(ctypes.windll.user32.GetKeyState(0x14) & 1)  # VK_CAPITAL
    except Exception:  # нет PyObjC или вызов не удался — просто без подсказки
        pass
    return False


class PasswordField(QWidget):
    """Поле для пароля: символы скрыты, кнопка-«глаз» показывает их на 15 секунд."""

    textChanged = Signal(str)

    def __init__(self, placeholder="", parent=None, copy_password=None, master=False):
        """master=True — поле мастер-пароля: под ним предупреждение, если включён Caps Lock
        (неверный мастер-пароль из-за заглавных букв — самая частая ошибка)."""
        super().__init__(parent)
        self.edit = SecretEdit(copy_password)
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self.textChanged)

        self.eye = QToolButton()
        icon = QIcon()  # открытый глаз, пока пароль скрыт; зачёркнутый неоновый — пока показан
        icon.addFile(theme.EYE_FILE, QSize(), QIcon.Normal, QIcon.Off)
        icon.addFile(theme.EYE_OFF_FILE, QSize(), QIcon.Normal, QIcon.On)
        self.eye.setIcon(icon)
        self.eye.setIconSize(QSize(18, 18))
        self.eye.setCheckable(True)
        self.eye.setToolTip(tr("Show / hide characters"))
        self.eye.toggled.connect(self._toggle)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(lambda: self.eye.setChecked(False))

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        row = QHBoxLayout()
        row.addWidget(self.edit)
        row.addWidget(self.eye)
        column.addLayout(row)
        self.caps = theme.role(QLabel(tr("Caps Lock is on")), "error")
        self.caps.hide()
        column.addWidget(self.caps)
        if master:
            # Qt не сообщает о Caps Lock сам — пока поле в фокусе, проверяем пару раз в секунду
            self.caps_timer = QTimer(self)
            self.caps_timer.timeout.connect(self._check_caps)
            self.caps_timer.start(300)

    def _check_caps(self):
        shown = self.edit.hasFocus() and caps_lock_on()
        if shown != self.caps.isVisible():
            self.caps.setVisible(shown)
            QTimer.singleShot(0, self._fit_window)

    def _fit_window(self):
        """Строка про Caps Lock добавилась — окно подрастает, а не сплющивает поля."""
        window = self.window()
        layout = window.layout()
        if layout is None:
            return
        need = layout.totalHeightForWidth(window.width()) if layout.hasHeightForWidth() else layout.totalSizeHint().height()
        if window.height() < need:
            window.setMinimumHeight(need)
            window.resize(window.width(), need)

    def _toggle(self, shown):
        self.edit.setEchoMode(QLineEdit.Normal if shown else QLineEdit.Password)
        if shown:
            self.hide_timer.start(prefs.reveal_seconds() * 1000)  # «глаз» закроется сам (время — в Настройках)
        else:
            self.hide_timer.stop()

    def show_always(self):
        """Символы видны всегда, «глаза» нет — для пароля, который ещё нигде не сохранён (генератор)."""
        self.eye.hide()
        self.edit.setEchoMode(QLineEdit.Normal)

    def text(self):
        return self.edit.text()

    def setText(self, text):
        self.edit.setText(text)

    def clear(self):
        self.edit.clear()

    def setFocus(self):
        self.edit.setFocus()


def verdict(bits):
    """Оценка словами и цвет для шкалы."""
    if bits >= 100:
        return tr("very strong"), GOOD
    if bits >= 70:
        return tr("strong"), GOOD
    if bits >= 45:
        return tr("medium"), WARNING
    return tr("weak"), BAD


class RoundedRowDelegate(QStyledItemDelegate):
    """Строки таблицы — скруглёнными плашками, а не прямоугольниками: выделенная —
    лавандовой, а каждая вторая — едва заметной светлой («зебра»), чтобы строки
    не сливались перед глазами.

    Qt красит фон в каждой ячейке отдельно и скруглить может только ячейку,
    поэтому плашку на всю строку рисуем сами: каждая ячейка рисует свой кусок
    общей скруглённой плашки (обрезанный по границам ячейки).
    """

    RADIUS = 10
    INSET = 4  # отступ плашки от краёв таблицы, чтобы были видны скругления
    STRIPE_ALPHA = 11  # яркость «зебры»: заметно глазу, но не спорит с выделением

    def _plate(self, painter, option, color):
        viewport = option.widget.viewport() if option.widget else None
        width = viewport.width() if viewport else option.rect.right()
        row = QRectF(self.INSET, option.rect.top() + 1,
                     width - 2 * self.INSET, option.rect.height() - 2)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setClipRect(option.rect)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(row, self.RADIUS, self.RADIUS)
        painter.restore()

    def paint(self, painter, option, index):
        if option.state & QStyle.State_Selected:
            # переливом через всю строку, как ключ на логотипе: лавандовый → фуксия
            width = option.widget.viewport().width() if option.widget else option.rect.right()
            fill = QLinearGradient(0, 0, width, 0)
            start, end = QColor(theme.ACC), QColor(theme.MAGENTA)
            start.setAlpha(120)
            end.setAlpha(110)
            fill.setColorAt(0, start)
            fill.setColorAt(1, end)
            self._plate(painter, option, fill)
            # остальное (текст) — как обычно, но без стандартной прямоугольной заливки
            option = QStyleOptionViewItem(option)
            option.state &= ~QStyle.State_Selected
            self._selected = True  # для initStyleOption: текст выделенной строки — белый
        elif index.row() % 2:
            # после сортировки номер строки — её место на экране, так что полосы не скачут
            stripe = QColor(theme.WHITE)
            stripe.setAlpha(self.STRIPE_ALPHA)
            self._plate(painter, option, stripe)
        super().paint(painter, option, index)
        self._selected = False

    _selected = False

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if self._selected:
            # серые колонки (заметка, дата) на светлой плашке читались бы плохо
            option.palette.setColor(QPalette.Text, QColor(theme.WHITE))


class _DrainingBar(QWidget):
    """Неоновая полоска, которая плавно убывает справа налево."""

    def __init__(self):
        super().__init__()
        self.fraction = 1.0  # какая часть полоски ещё заполнена
        self.setFixedHeight(6)
        self.setMinimumWidth(160)
        theme.glow(self, theme.NEON, radius=12, alpha=200)

    def set_fraction(self, fraction):
        self.fraction = max(0.0, min(1.0, fraction))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        r = self.height() / 2
        track = QColor(theme.WHITE)
        track.setAlpha(22)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(self.rect()), r, r)
        fill = QRectF(0, 0, self.width() * self.fraction, self.height())
        if fill.width() > 0:
            gradient = QLinearGradient(0, 0, self.width(), 0)
            gradient.setColorAt(0, QColor(theme.ACC_DEEP))
            gradient.setColorAt(1, QColor(theme.NEON))
            p.setBrush(gradient)
            p.drawRoundedRect(fill, r, r)


class ClipboardCountdown(QWidget):
    """«Пароль в буфере · 27 с» и полоска, которая убывает, пока буфер не очистится.

    Сам буфер чистит clipboard.py по своему таймеру — здесь только показ.
    """

    finished = Signal()

    def __init__(self, bar_width=None, parent=None):
        """bar_width — фиксированная длина полоски; без неё полоска занимает всю ширину."""
        super().__init__(parent)
        self.seconds = 0
        self.label = theme.role(QLabel(), "accent")
        self.bar = _DrainingBar()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(self.label)
        if bar_width:
            self.bar.setFixedWidth(bar_width)
            row.addWidget(self.bar)
            row.addStretch()
        else:
            row.addWidget(self.bar, 1)
        self._clock = QElapsedTimer()
        self._tick = QTimer(self)
        self._tick.setInterval(33)  # ~30 кадров в секунду — убывает плавно
        self._tick.timeout.connect(self._update)
        self.hide()

    def start(self, seconds):
        """Запускает отсчёт заново (и при повторном копировании тоже)."""
        self.seconds = seconds
        self._clock.start()
        self._tick.start()
        self._update()
        self.show()

    def _update(self):
        left = self.seconds - self._clock.elapsed() / 1000
        if left <= 0:
            self._tick.stop()
            self.hide()
            self.finished.emit()
            return
        self.label.setText(tr("Password in clipboard · {sec} s").format(sec=math.ceil(left)))
        self.bar.set_fraction(left / self.seconds)


class StrengthBar(QWidget):
    """Полоска надёжности пароля + подпись «≈129 бит — очень надёжно»."""

    def __init__(self, empty_text=None, parent=None):
        """empty_text — подсказка, пока пароль не введён (у мастер-пароля
        нет кнопки «Сгенерировать», поэтому для него своя подсказка)."""
        super().__init__(parent)
        self.empty_text = empty_text
        self.bar = QProgressBar()
        self.bar.setRange(0, 128)  # 128 бит и больше — полная шкала
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.label = theme.role(QLabel(), "muted")
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.bar)
        column.addWidget(self.label)
        self.show_for("")

    def show_for(self, password, bits=None):
        """bits — точное значение для сгенерированного пароля, иначе оценка."""
        if not password:
            self.bar.setValue(0)
            self.label.setText(self.empty_text or tr("Type or generate a password"))
            return
        if bits is None:
            bits = estimate_bits(password)
        words, color = verdict(bits)
        self.bar.setValue(min(int(bits), 128))
        # сама полоска оформлена в theme.py, здесь только цвет заполнения
        self.bar.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; }}")
        self.label.setText(tr("≈{bits:.0f} bits — {verdict}").format(bits=bits, verdict=words))


class GeneratorPanel(QWidget):
    """Настройки генератора и кнопка «Сгенерировать»."""

    generated = Signal(str, float)  # пароль и его надёжность в битах

    def __init__(self, parent=None):
        super().__init__(parent)
        remembered = prefs.generator_options()  # длина и наборы символов — как в прошлый раз
        self.length = QSpinBox()
        self.length.setRange(MIN_LENGTH, MAX_LENGTH)
        self.length.setValue(remembered[0] if remembered else 20)
        self.length.setToolTip(tr("Password length"))
        self.kinds = {}
        for name, label, tip in [("lower", "abc", tr("Lowercase letters")), ("upper", "ABC", tr("Uppercase letters")),
                                 ("digits", "123", tr("Digits")), ("symbols", "!@#", tr("Symbols"))]:
            box = QCheckBox(label)
            box.setToolTip(tip)
            box.setChecked(remembered[1].get(name, True) if remembered else True)
            box.toggled.connect(self._update_button)
            self.kinds[name] = box
        self.button = QPushButton(tr("Generate"))
        self.button.clicked.connect(self.generate)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(tr("Length:")))
        row.addWidget(self.length)
        for box in self.kinds.values():
            row.addWidget(box)
        row.addStretch()
        row.addWidget(self.button)

    def _update_button(self):
        # без единого вида символов генерировать не из чего
        self.button.setEnabled(any(box.isChecked() for box in self.kinds.values()))

    def generate(self):
        settings = {name: box.isChecked() for name, box in self.kinds.items()}
        length = self.length.value()
        prefs.remember_generator(length, settings)
        password = generate_password(length, **settings)
        self.generated.emit(password, entropy_bits(length, **settings))


# --- Стандартные окошки ---

def _message(parent, title, text, symbol, color):
    """Окошко с сообщением и нашим значком вместо стандартного (тот почти не виден)."""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setTextFormat(Qt.PlainText)  # в тексте бывает название записи — не HTML
    box.setText(text)
    box.setIconPixmap(theme.badge(symbol, color))
    return box


def ask_yes(parent, title, text, danger=None):
    """Вопрос «Да / Нет». danger — надпись красной кнопки для необратимого действия
    («Удалить»): тогда кнопки «Отмена» и «Удалить» — сразу понятно, что произойдёт."""
    box = _message(parent, title, text, "?", theme.NEON)
    # свои кнопки: стандартные Yes/No Qt без перевода показал бы по-английски
    no = box.addButton(tr("Cancel") if danger else tr("No"), QMessageBox.RejectRole)
    yes = box.addButton(danger or tr("Yes"), QMessageBox.AcceptRole)
    if danger:
        theme.kind(yes, "danger")
    box.setDefaultButton(no)  # Enter по ошибке не удалит запись
    box.exec()
    return box.clickedButton() is yes


def ask_code(parent, title, text):
    """Окно ввода 4-значного кода. Возвращает введённые цифры или None (отмена)."""
    box = _message(parent, title, text, "?", theme.NEON)
    edit = QLineEdit()
    edit.setMaxLength(4)
    edit.setInputMask("9999;_")  # только цифры
    edit.setAlignment(Qt.AlignCenter)
    font = edit.font()
    font.setPixelSize(28)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 8)
    edit.setFont(font)
    edit.setFixedWidth(180)
    box.addButton(tr("Cancel"), QMessageBox.RejectRole)
    allow = box.addButton(tr("Allow"), QMessageBox.AcceptRole)
    # поле — в разметку QMessageBox, между текстом и кнопками (кнопки переставляем ниже него)
    layout, buttons = box.layout(), box.findChild(QDialogButtonBox)
    columns = layout.columnCount()
    layout.removeWidget(buttons)
    row = layout.rowCount()
    layout.addWidget(edit, row, 0, 1, columns, Qt.AlignCenter)
    layout.addWidget(buttons, row + 1, 0, 1, columns)
    box.setDefaultButton(allow)
    QTimer.singleShot(0, edit.setFocus)
    box.exec()
    if box.clickedButton() is not allow:
        return None
    return edit.text().strip()


def show_error(parent, text):
    _message(parent, tr("Error"), text, "!", theme.BAD_INK).exec()


def show_info(parent, title, text):
    _message(parent, title, text, "i", theme.NEON).exec()


def save_problem(error):
    """Причина ошибки записи для окна: у «слишком большого» хранилища — на языке человека."""
    if isinstance(error, VaultTooLarge):
        return tr("the vault would be larger than 10 MB, delete some entries or shorten long notes")
    return str(error)


def choose_csv(parent):
    """Спрашивает CSV-файл и читает его: (имя файла, записи). None — отказались или в файле нет паролей
    (об ошибке человеку уже сказали)."""
    name, _ = QFileDialog.getOpenFileName(parent, tr("Import from CSV"), str(Path.home() / "Downloads"),
                                          tr("CSV files (*.csv);;All files (*)"))
    if not name:
        return None
    nothing = tr("No passwords found in this file. It needs columns with the name or website address and the password, as in an export from a browser, Bitwarden or KeePassXC.")
    try:
        found = csv_io.read(name)
    except OSError as error:
        show_error(parent, tr("Could not read the file: {error}").format(error=error.strerror or error))
        return None
    except csv_io.CsvError as error:
        show_error(parent, {
            "too_big": tr("The file is too big for a password list."),
            "encoding": tr("The file is not in UTF-8 encoding. Export the passwords again or save the file as UTF-8."),
        }.get(str(error), nothing))
        return None
    if not found:
        show_error(parent, nothing)
        return None
    return name, found


def weakness_text(reasons):
    """Причины слабого пароля (ключи из generator.weakness_reasons) — списком."""
    reason_texts = {
        "weak_common": tr("contains a very common word or pattern (qwerty, 123456, password...)"),
        "weak_one_kind": tr("only one kind of characters — mix upper/lower case, digits, symbols"),
        "weak_repeat": tr("one character repeated 4 times in a row"),
        "weak_short": tr("shorter than 12 characters"),
    }
    return "\n".join("• " + reason_texts[reason] for reason in reasons)
