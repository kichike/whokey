"""Общие элементы окон: поле пароля с «глазом», шкала надёжности, генератор,
и короткие функции для стандартных окошек-вопросов."""

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                               QProgressBar, QPushButton, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from generator import MAX_LENGTH, MIN_LENGTH, entropy_bits, estimate_bits, generate_password
from gui import theme
from texts import t

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
        menu = QMenu(self)
        if self.copy_password:
            menu.addAction(t("g_copy"), self._copy_out).setEnabled(bool(self.text()))
        menu.addAction(t("g_paste"), self.paste).setEnabled(not self.isReadOnly())
        menu.addAction(t("g_select_all"), self.selectAll)
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
        self.eye.setText("👁")
        self.eye.setCheckable(True)
        self.eye.setToolTip(t("g_show_chars"))
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
        return t("verdict_strong"), GOOD
    if bits >= 70:
        return t("verdict_ok"), GOOD
    if bits >= 45:
        return t("g_verdict_medium"), WARNING
    return t("g_verdict_weak"), BAD


class StrengthBar(QWidget):
    """Полоска надёжности пароля + подпись «≈129 бит — очень надёжно»."""

    def __init__(self, empty_text="g_strength_empty", parent=None):
        """empty_text — подсказка, пока пароль не введён (у мастер-пароля
        нет кнопки «Сгенерировать», поэтому для него своя подсказка)."""
        super().__init__(parent)
        self.empty_text = empty_text
        self.bar = QProgressBar()
        self.bar.setRange(0, 128)  # 128 бит и больше — полная шкала
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setStyleSheet(f"QProgressBar {{ border: 1px solid {theme.LINE}; background: {theme.WELL}; }}")
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
            self.label.setText(t(self.empty_text))
            return
        if bits is None:
            bits = estimate_bits(password)
        words, color = verdict(bits)
        self.bar.setValue(min(int(bits), 128))
        self.bar.setStyleSheet(
            f"QProgressBar {{ border: 1px solid {theme.LINE}; background: {theme.WELL}; }}"
            f"QProgressBar::chunk {{ background: {color}; }}")
        self.label.setText(t("g_strength", bits=bits, verdict=words))


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
        self.button = QPushButton(t("g_generate"))
        self.button.clicked.connect(self.generate)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(t("g_length")))
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

def ask_yes(parent, title, text):
    answer = QMessageBox.question(parent, title, text,
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    return answer == QMessageBox.Yes


def show_error(parent, text):
    QMessageBox.warning(parent, t("g_error_title"), text)


def weakness_text(reasons):
    return "\n".join("• " + t(reason) for reason in reasons)
