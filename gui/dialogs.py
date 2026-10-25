"""Окна поверх главного: запись (добавить / изменить), генератор, смена мастер-пароля."""

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout)

import sites
from clipboard import CLEAR_AFTER
from generator import weakness_reasons
from gui import theme
from gui.widgets import ClipboardCountdown, GeneratorPanel, PasswordField, StrengthBar, ask_yes, show_error, weakness_text
from gui.i18n import tr
from vault import SaveError

MASTER_MIN_LENGTH = 12


def _buttons(dialog, ok_text):
    """Кнопки «Сохранить» / «Отмена» внизу окна."""
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.button(QDialogButtonBox.Ok).setText(ok_text)
    theme.kind(box.button(QDialogButtonBox.Ok), "primary")
    box.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


class EntryDialog(QDialog):
    """Добавление или изменение записи. Пароль на экран сам не выводится —
    только по кнопке-«глазу»."""

    def __init__(self, parent, entry=None, copy_password=None):
        """copy_password — как копировать пароль из поля (через буфер с автоочисткой)."""
        super().__init__(parent)
        self.setWindowTitle(tr("Edit entry") if entry else tr("New entry"))
        # начальная ширина, а не жёсткий минимум: с жёстким минимумом Qt перестаёт
        # расширять окно под содержимое и сжимает кнопки (на Windows шрифт шире —
        # «Сгенерировать» обрезалось до «нериров»)
        self.resize(520, 1)
        entry = entry or {"site": "", "login": "", "password": "", "note": ""}

        self.site = QLineEdit(entry["site"])
        # адрес сайта — для расширения браузера: по нему решается, на какой странице заполнять
        self.url = QLineEdit(entry.get("url", ""))
        self.url.setPlaceholderText(tr("mail.ru — for filling in the browser"))
        self.login = QLineEdit(entry["login"])
        self.password = PasswordField(copy_password=copy_password)
        self.password.setText(entry["password"])
        self.strength = StrengthBar()
        self.generator = GeneratorPanel()
        self.note = QLineEdit(entry["note"])

        self._generated = None  # точная надёжность для только что сгенерированного
        self.password.textChanged.connect(self._on_password_changed)
        self.generator.generated.connect(self._on_generated)
        self._on_password_changed(entry["password"])

        form = QFormLayout()
        form.addRow(tr("Site"), self.site)
        form.addRow(tr("Website"), self.url)
        form.addRow(tr("Login"), self.login)
        form.addRow(tr("Password"), self.password)
        form.addRow("", self.strength)
        form.addRow("", self.generator)
        form.addRow(tr("Note"), self.note)

        self.error = QLabel()
        theme.role(self.error, "error")
        column = QVBoxLayout(self)
        column.addLayout(form)
        column.addWidget(self.error)
        column.addWidget(_buttons(self, tr("Save")))

    def _on_generated(self, password, bits):
        self._generated = (password, bits)
        self.password.setText(password)

    def _on_password_changed(self, text):
        if self._generated and self._generated[0] == text:
            self.strength.show_for(text, self._generated[1])
        else:
            self.strength.show_for(text)

    def accept(self):
        if not self.site.text().strip():
            self.error.setText(tr("Site is required."))
            return
        if not self.password.text():
            self.error.setText(tr("Password cannot be empty."))
            return
        if sites.normalize(self.url.text()) is None:
            self.error.setText(tr("This does not look like a website address. Example: mail.ru"))
            return
        super().accept()

    def values(self):
        return {"site": self.site.text().strip(), "login": self.login.text().strip(),
                "password": self.password.text(), "note": self.note.text().strip(),
                "url": sites.normalize(self.url.text())}


class GeneratorDialog(QDialog):
    """Отдельный генератор: пароль нигде не сохраняется — посмотреть или скопировать."""

    def __init__(self, parent, copy_password):
        super().__init__(parent)
        self.setWindowTitle(tr("Password generator"))
        self.resize(520, 1)  # начальная ширина, см. EntryDialog
        self.copy_password = copy_password

        self.generator = GeneratorPanel()
        self.result = PasswordField(copy_password=self._copy)
        self.result.edit.setReadOnly(True)
        self.strength = StrengthBar()
        self.generator.generated.connect(self._on_generated)

        copy = theme.kind(QPushButton(tr("Copy password")), "primary")
        copy.clicked.connect(lambda: self._copy(self.result.text()))
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)

        column = QVBoxLayout(self)
        column.addWidget(self.generator)
        column.addWidget(self.result)
        column.addWidget(self.strength)
        # до копирования — подсказка, после — на её месте таймер с убывающей полоской
        self.note = theme.role(QLabel(tr("A copied password is removed from the clipboard after {sec} s.").format(sec=CLEAR_AFTER)), "muted")
        self.countdown = ClipboardCountdown()
        self.countdown.finished.connect(self.note.show)
        column.addWidget(self.note)
        column.addWidget(self.countdown)
        column.addWidget(copy)
        column.addWidget(close)
        self.generator.generate()

    def _copy(self, password):
        if self.copy_password(password):
            self.note.hide()
            self.countdown.start(CLEAR_AFTER)

    def _on_generated(self, password, bits):
        self.result.setText(password)
        self.strength.show_for(password, bits)


class ChangeMasterDialog(QDialog):
    """Смена мастер-пароля: текущий + новый дважды. Хранилище перешифровывается."""

    def __init__(self, parent, vault):
        super().__init__(parent)
        self.setWindowTitle(tr("Change master password"))
        self.resize(480, 1)  # начальная ширина, см. EntryDialog
        self.vault = vault

        self.current = PasswordField(tr("Current master password"))
        self.new = PasswordField(tr("New master password"))
        self.repeat = PasswordField(tr("Repeat master password"))
        self.strength = StrengthBar(tr("Type a master password"))
        self.new.textChanged.connect(self.strength.show_for)
        rules = QLabel(tr("Choose a master password: at least 12 characters. It cannot be recovered — if you forget it, your passwords are lost."))
        rules.setWordWrap(True)
        self.error = QLabel()
        self.error.setWordWrap(True)
        theme.role(self.error, "error")

        column = QVBoxLayout(self)
        for widget in (self.current, rules, self.new, self.repeat, self.strength, self.error):
            column.addWidget(widget)
        column.addWidget(_buttons(self, tr("Save")))
        self.current.setFocus()

    def accept(self):
        if not self.vault.check_password(self.current.text()):
            self.error.setText(tr("Wrong master password."))
            self.current.clear()
            return
        password = self.new.text()
        if len(password) < MASTER_MIN_LENGTH:
            self.error.setText(tr("Too short: {n} characters, at least 12 required.").format(n=len(password)))
            return
        reasons = [r for r in weakness_reasons(password) if r != "weak_short"]
        if reasons and not ask_yes(self, tr("Weak password"),
                                   tr("The password is weak:\n{reasons}\n\nUse it anyway?").format(reasons=weakness_text(reasons))):
            return
        if self.repeat.text() != password:
            self.error.setText(tr("Passwords don't match, try again."))
            self.repeat.clear()
            return
        try:
            self.vault.change_password(password)
        except SaveError as error:
            show_error(self, tr("⚠ Could not save: {error}. The change was not applied, the file on disk is untouched.").format(error=error))
            return
        super().accept()
