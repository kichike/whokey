"""Общие элементы окон: поле пароля с «глазом», шкала надёжности, генератор,
и короткие функции для стандартных окошек-вопросов."""

import math

from PySide6.QtCore import QElapsedTimer, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QKeySequence, QLinearGradient, QPainter
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                               QProgressBar, QPushButton, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from generator import MAX_LENGTH, MIN_LENGTH, entropy_bits, estimate_bits, generate_password
from gui import theme
from gui.i18n import tr

# Цвета шкалы надёжности — «светофор» из оформления: хорошо / так себе / плохо
GOOD, WARNING, BAD = theme.OK, theme.WARN, theme.BAD


REVEAL_SECONDS = 15  # показанный «глазом» пароль сам скроется — как в таблице


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


class PasswordField(QWidget):
    """Поле для пароля: символы скрыты, кнопка-«глаз» показывает их на 15 секунд."""

    textChanged = Signal(str)

    def __init__(self, placeholder="", parent=None, copy_password=None):
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
        self.hide_timer.setInterval(REVEAL_SECONDS * 1000)
        self.hide_timer.timeout.connect(lambda: self.eye.setChecked(False))

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.edit)
        row.addWidget(self.eye)

    def _toggle(self, shown):
        self.edit.setEchoMode(QLineEdit.Normal if shown else QLineEdit.Password)
        if shown:
            self.hide_timer.start()  # через 15 с «глаз» закроется сам
        else:
            self.hide_timer.stop()

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
        self.length = QSpinBox()
        self.length.setRange(MIN_LENGTH, MAX_LENGTH)
        self.length.setValue(20)
        self.kinds = {}
        for name, label in [("lower", "abc"), ("upper", "ABC"), ("digits", "123"), ("symbols", "!@#")]:
            box = QCheckBox(label)
            box.setChecked(True)
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
        password = generate_password(length, **settings)
        self.generated.emit(password, entropy_bits(length, **settings))


# --- Стандартные окошки ---

def _message(parent, title, text, symbol, color):
    """Окошко с сообщением и нашим значком вместо стандартного (тот почти не виден)."""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIconPixmap(theme.badge(symbol, color))
    return box


def ask_yes(parent, title, text):
    box = _message(parent, title, text, "?", theme.NEON)
    # свои кнопки: стандартные Yes/No Qt без перевода показал бы по-английски
    no = box.addButton(tr("No"), QMessageBox.RejectRole)
    yes = box.addButton(tr("Yes"), QMessageBox.AcceptRole)
    box.setDefaultButton(no)  # Enter по ошибке не удалит запись
    box.exec()
    return box.clickedButton() is yes


def show_error(parent, text):
    _message(parent, tr("Error"), text, "!", theme.BAD_INK).exec()


def show_info(parent, title, text):
    _message(parent, title, text, "i", theme.NEON).exec()


def weakness_text(reasons):
    """Причины слабого пароля (ключи из generator.weakness_reasons) — списком."""
    reason_texts = {
        "weak_common": tr("contains a very common word or pattern (qwerty, 123456, password...)"),
        "weak_one_kind": tr("only one kind of characters — mix upper/lower case, digits, symbols"),
        "weak_repeat": tr("one character repeated 4 times in a row"),
        "weak_short": tr("shorter than 12 characters"),
    }
    return "\n".join("• " + reason_texts[reason] for reason in reasons)
