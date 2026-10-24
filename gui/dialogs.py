"""Окна поверх главного: запись (добавить / изменить), генератор, смена мастер-пароля."""

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout)

from clipboard import CLEAR_AFTER
from generator import weakness_reasons
from gui import theme
from gui.widgets import GeneratorPanel, PasswordField, StrengthBar, ask_yes, show_error, weakness_text
from texts import t
from vault import SaveError

MASTER_MIN_LENGTH = 12


def _buttons(dialog, ok_text):
    """Кнопки «Сохранить» / «Отмена» внизу окна."""
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.button(QDialogButtonBox.Ok).setText(ok_text)
    theme.kind(box.button(QDialogButtonBox.Ok), "primary")
    box.button(QDialogButtonBox.Cancel).setText(t("g_cancel"))
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


class EntryDialog(QDialog):
    """Добавление или изменение записи. Пароль на экран сам не выводится —
    только по кнопке-«глазу»."""

    def __init__(self, parent, entry=None, copy_password=None):
        """copy_password — как копировать пароль из поля (через буфер с автоочисткой)."""
        super().__init__(parent)
        self.setWindowTitle(t("g_edit_title" if entry else "g_add_title"))
        self.setMinimumWidth(520)
        entry = entry or {"site": "", "login": "", "password": "", "note": ""}

        self.site = QLineEdit(entry["site"])
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
        form.addRow(t("col_site"), self.site)
        form.addRow(t("col_login"), self.login)
        form.addRow(t("col_password"), self.password)
        form.addRow("", self.strength)
        form.addRow("", self.generator)
        form.addRow(t("col_note"), self.note)

        self.error = QLabel()
        theme.role(self.error, "error")
        column = QVBoxLayout(self)
        column.addLayout(form)
        column.addWidget(self.error)
        column.addWidget(_buttons(self, t("g_save")))

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
            self.error.setText(t("site_required"))
            return
        if not self.password.text():
            self.error.setText(t("g_password_required"))
            return
        super().accept()

    def values(self):
        return {"site": self.site.text().strip(), "login": self.login.text().strip(),
                "password": self.password.text(), "note": self.note.text().strip()}


class GeneratorDialog(QDialog):
    """Отдельный генератор: пароль нигде не сохраняется — посмотреть или скопировать."""

    def __init__(self, parent, copy_password):
        super().__init__(parent)
        self.setWindowTitle(t("g_generator_title"))
        self.setMinimumWidth(520)
        self.copy_password = copy_password

        self.generator = GeneratorPanel()
        self.result = PasswordField(copy_password=copy_password)
        self.result.edit.setReadOnly(True)
        self.strength = StrengthBar()
        self.generator.generated.connect(self._on_generated)

        copy = theme.kind(QPushButton(t("g_copy")), "primary")
        copy.clicked.connect(lambda: self.copy_password(self.result.text()))
        close = QPushButton(t("g_close"))
        close.clicked.connect(self.accept)

        column = QVBoxLayout(self)
        column.addWidget(self.generator)
        column.addWidget(self.result)
        column.addWidget(self.strength)
        column.addWidget(theme.role(QLabel(t("g_clear_note", sec=CLEAR_AFTER)), "muted"))
        column.addWidget(copy)
        column.addWidget(close)
        self.generator.generate()

    def _on_generated(self, password, bits):
        self.result.setText(password)
        self.strength.show_for(password, bits)


class ChangeMasterDialog(QDialog):
    """Смена мастер-пароля: текущий + новый дважды. Хранилище перешифровывается."""

    def __init__(self, parent, vault):
        super().__init__(parent)
        self.setWindowTitle(t("g_change_master"))
        self.setMinimumWidth(480)
        self.vault = vault

        self.current = PasswordField(t("g_current_master"))
        self.new = PasswordField(t("g_new_master"))
        self.repeat = PasswordField(t("g_master_repeat"))
        self.strength = StrengthBar("g_strength_master_empty")
        self.new.textChanged.connect(self.strength.show_for)
        rules = QLabel(t("new_master_rules"))
        rules.setWordWrap(True)
        self.error = QLabel()
        self.error.setWordWrap(True)
        theme.role(self.error, "error")

        column = QVBoxLayout(self)
        for widget in (self.current, rules, self.new, self.repeat, self.strength, self.error):
            column.addWidget(widget)
        column.addWidget(_buttons(self, t("g_save")))
        self.current.setFocus()

    def accept(self):
        if not self.vault.check_password(self.current.text()):
            self.error.setText(t("wrong_password"))
            self.current.clear()
            return
        password = self.new.text()
        if len(password) < MASTER_MIN_LENGTH:
            self.error.setText(t("too_short", n=len(password)))
            return
        reasons = [r for r in weakness_reasons(password) if r != "weak_short"]
        if reasons and not ask_yes(self, t("g_weak_title"),
                                   t("g_weak_question", reasons=weakness_text(reasons))):
            return
        if self.repeat.text() != password:
            self.error.setText(t("mismatch"))
            self.repeat.clear()
            return
        try:
            self.vault.change_password(password)
        except SaveError as error:
            show_error(self, t("save_failed", error=error))
            return
        super().accept()
