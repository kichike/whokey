"""Окна поверх главного: запись (добавить / изменить), генератор, смена мастер-пароля,
настройки, расширение браузера (журнал выдач паролей)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

import sites
from generator import weakness_reasons
from gui import i18n, prefs, theme, touchid
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
        # у записи из расширения уже вписан адрес, но она новая: «изменить» — только сохранённую
        self.setWindowTitle(tr("Edit entry") if entry and "created" in entry else tr("New entry"))
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
        # заметка — в несколько строк: туда помещаются, например, коды восстановления
        self.note = QPlainTextEdit(entry["note"])
        self.note.setTabChangesFocus(True)  # Tab переходит дальше, а не вставляет табуляцию
        self.note.setFixedHeight(self.note.fontMetrics().lineSpacing() * 4 + 20)

        self._generated = None  # точная надёжность для только что сгенерированного
        self.password.textChanged.connect(self._on_password_changed)
        self.generator.generated.connect(self._on_generated)
        self._on_password_changed(entry["password"])

        form = QFormLayout()
        form.addRow(tr("Name"), self.site)
        form.addRow(tr("Website address"), self.url)
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
        self._initial = self.values(normalize=False)  # чтобы при закрытии понять, было ли что-то изменено

    def _on_generated(self, password, bits):
        self._generated = (password, bits)
        self.password.setText(password)

    def _on_password_changed(self, text):
        if self._generated and self._generated[0] == text:
            self.strength.show_for(text, self._generated[1])
        else:
            self.strength.show_for(text)

    def _problem(self, field, text):
        """Ошибка: текст внизу и красная рамка у поля, которое нужно исправить."""
        for widget in (self.site, self.password.edit, self.url):
            theme.mark_invalid(widget, widget is field)
        self.error.setText(text)
        field.setFocus()

    def accept(self):
        if not self.site.text().strip():
            return self._problem(self.site, tr("Name is required."))
        if not self.password.text():
            return self._problem(self.password.edit, tr("Password cannot be empty."))
        if sites.normalize(self.url.text()) is None:
            return self._problem(self.url, tr("This does not look like a website address. Example: mail.ru"))
        super().accept()

    def reject(self):
        """Esc или «Отмена» при несохранённых изменениях — сначала спросить."""
        if self.values(normalize=False) != self._initial and not ask_yes(
                self, tr("Unsaved changes"), tr("Close without saving the changes?")):
            return
        super().reject()

    def values(self, normalize=True):
        url = sites.normalize(self.url.text()) if normalize else self.url.text().strip()
        return {"site": self.site.text().strip(), "login": self.login.text().strip(),
                "password": self.password.text(), "note": self.note.toPlainText().strip(),
                "url": url}


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
        self.result.show_always()  # пароль ещё нигде не сохранён — прятать его незачем
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
        self.note = theme.role(QLabel(tr("A copied password is removed from the clipboard after {sec} s.").format(sec=prefs.clear_after())), "muted")
        self.countdown = ClipboardCountdown()
        self.countdown.finished.connect(self.note.show)
        column.addWidget(self.note)
        column.addWidget(self.countdown)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(close)
        buttons.addWidget(copy)
        column.addLayout(buttons)
        copy.setDefault(True)
        self.generator.generate()

    def _copy(self, password):
        if self.copy_password(password):
            self.note.hide()
            self.countdown.start(prefs.clear_after())

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

        self.current = PasswordField()
        self.new = PasswordField()
        self.repeat = PasswordField()
        self.strength = StrengthBar(tr("Type a master password"))
        self.new.textChanged.connect(self.strength.show_for)
        rules = theme.role(QLabel(tr("Choose a master password: at least 12 characters. It cannot be recovered — if you forget it, your passwords are lost.")), "muted")
        rules.setWordWrap(True)
        self.error = QLabel()
        self.error.setWordWrap(True)
        theme.role(self.error, "error")

        # подписи слева у каждого поля; полоска надёжности — сразу под новым паролем
        form = QFormLayout()
        form.addRow(tr("Current:"), self.current)
        form.addRow(tr("New:"), self.new)
        form.addRow("", self.strength)
        form.addRow(tr("Repeat:"), self.repeat)
        column = QVBoxLayout(self)
        column.addWidget(rules)
        column.addLayout(form)
        column.addWidget(self.error)
        column.addWidget(_buttons(self, tr("Save")))
        self.current.setFocus()

    def accept(self):
        if not self.vault.check_password(self.current.text()):
            self.error.setText(tr("Wrong master password."))
            self.current.clear()
            return
        password = self.new.text()
        # порядок проверок: длина → совпадение → слабость (о слабости спрашиваем последней)
        if len(password) < MASTER_MIN_LENGTH:
            self.error.setText(self.tr("Too short: %n characters, at least 12 required.", "", len(password)))
            return
        if self.repeat.text() != password:
            self.error.setText(tr("Passwords don't match, try again."))
            self.repeat.clear()
            self.repeat.setFocus()
            return
        reasons = [r for r in weakness_reasons(password) if r != "weak_short"]
        if reasons and not ask_yes(self, tr("Weak password"),
                                   tr("The password is weak:\n{reasons}\n\nUse it anyway?").format(reasons=weakness_text(reasons))):
            return
        try:
            self.vault.change_password(password)
        except SaveError as error:
            show_error(self, tr("⚠ Could not save: {error}. The change was not applied, the file on disk is untouched.").format(error=error))
            return
        # ключ сменился — старый, сохранённый для Touch ID, стираем; при следующем
        # входе по новому паролю WhoKey снова предложит включить Touch ID
        touchid.forget(self.vault.path)
        touchid.set_offered(self.vault.path, False)
        super().accept()


class ExportDialog(QDialog):
    """Перед экспортом в CSV: предупреждение, что файл не зашифрован, и мастер-пароль ещё раз —
    чтобы все пароли разом не выгрузил тот, кто просто подошёл к открытому WhoKey."""

    def __init__(self, parent, vault):
        super().__init__(parent)
        self.setWindowTitle(tr("Export to CSV"))
        self.resize(480, 1)
        self.vault = vault
        warning = QLabel(tr("The CSV file is plain text: all your passwords in it are NOT encrypted, and anyone who opens the file can read them. "
                            "Import it where you need it and then delete it (and empty the Trash)."))
        warning.setWordWrap(True)
        # с переносом строк Qt иначе считает высоту окна по неверной ширине и обрезает текст
        warning.setMinimumWidth(440)
        warning.setMinimumHeight(warning.heightForWidth(440))
        self.master = PasswordField(tr("Master password"))
        self.error = theme.role(QLabel(), "error")
        column = QVBoxLayout(self)
        column.addWidget(warning)
        column.addWidget(self.master)
        column.addWidget(self.error)
        column.addWidget(_buttons(self, tr("Export…")))
        self.master.setFocus()

    def accept(self):
        if not self.vault.check_password(self.master.text()):
            self.error.setText(tr("Wrong master password."))
            self.master.clear()
            return
        self.master.clear()
        super().accept()


class SettingsDialog(QDialog):
    """Настройки (⌘, на Mac, Ctrl+, на Windows): язык, время очистки буфера и показа
    пароля, автоблокировка, вход по Touch ID, смена мастер-пароля."""

    language_chosen = Signal(str)  # окна пересоздаются на новом языке — это делает app.py

    def __init__(self, parent, vault, change_master):
        """change_master — смена мастер-пароля главного окна (там же сообщения об ошибках)."""
        super().__init__(parent)
        self.setWindowTitle(tr("Settings"))
        self.resize(460, 1)
        self.vault = vault
        self.change_master = change_master

        form = QFormLayout()
        form.setSpacing(14)
        language = theme.rounded_popup(QComboBox())
        for code, name in i18n.LANGUAGES:
            language.addItem(name, code)
        language.setCurrentIndex([code for code, _ in i18n.LANGUAGES].index(i18n.LANG))
        language.view().setMinimumWidth(language.view().sizeHintForColumn(0) + 48)
        language.currentIndexChanged.connect(lambda i: self._choose_language(language.itemData(i)))
        form.addRow(tr("Language:"), language)

        seconds = lambda n: self.tr("%n s", "", n)  # noqa: E731 — «15 с» / «15 s»
        minutes = lambda n: self.tr("%n min", "", n)  # noqa: E731
        form.addRow(tr("Clear copied password after:"),
                    self._choice("clear_after", prefs.CLEAR_CHOICES, prefs.clear_after(), seconds))
        form.addRow(tr("Hide shown password after:"),
                    self._choice("reveal_seconds", prefs.REVEAL_CHOICES, prefs.reveal_seconds(), seconds))
        form.addRow(tr("Lock when not used for:"),
                    self._choice("idle_lock_minutes", prefs.IDLE_CHOICES, prefs.idle_lock_minutes(),
                                 lambda n: minutes(n) if n else tr("never")))

        self.touch_id = None
        if touchid.available():
            self.touch_id = QCheckBox(tr("Sign in with Touch ID"))
            self.touch_id.setChecked(touchid.is_enabled(vault.path))
            self.touch_id.toggled.connect(self._touch_id_toggled)
            form.addRow(tr("Touch ID:"), self.touch_id)

        change = QPushButton(tr("Change master password"))
        change.clicked.connect(self._change_master)
        form.addRow(tr("Master password:"), change)

        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.button(QDialogButtonBox.Close).setText(tr("Close"))
        close.rejected.connect(self.reject)
        column = QVBoxLayout(self)
        column.addLayout(form)
        column.addWidget(close)

    def _choice(self, name, choices, current, label):
        combo = theme.rounded_popup(QComboBox())
        for value in choices:
            combo.addItem(label(value), value)
        combo.setCurrentIndex(choices.index(current))
        combo.view().setMinimumWidth(combo.view().sizeHintForColumn(0) + 48)
        combo.currentIndexChanged.connect(lambda i: prefs.set_value(name, combo.itemData(i)))
        return combo

    def _choose_language(self, code):
        self.reject()
        self.language_chosen.emit(code)

    def _touch_id_toggled(self, checked):
        touchid.set_offered(self.vault.path)  # выбор сделан — при входе больше не спрашиваем
        if not checked:
            touchid.forget(self.vault.path)
        elif not touchid.save_key(self.vault.path, self.vault.key):
            show_error(self, tr("macOS did not allow saving the key to the Keychain. Touch ID is off."))
            self.touch_id.setChecked(False)

    def _change_master(self):
        had_touch_id = touchid.is_enabled(self.vault.path)
        self.hide()  # окно смены пароля — вместо Настроек, а не второе окно поверх
        self.change_master()
        self.reject()
        # после смены пароля старый ключ стёрт; раз Touch ID был включён — кладём новый
        if had_touch_id and not touchid.is_enabled(self.vault.path):
            touchid.save_key(self.vault.path, self.vault.key)
            touchid.set_offered(self.vault.path)


README_URL = "https://github.com/kichike/whokey#browser-extension"


class ExtensionDialog(QDialog):
    """Расширение браузера: подключено ли, журнал выдач паролей и кнопка «Отключить»."""

    def __init__(self, parent, vault, save):
        """save — сохранение главного окна (там же сообщения об ошибках записи)."""
        super().__init__(parent)
        self.setWindowTitle(tr("Extension"))
        self.resize(620, 460)
        self.vault, self.save = vault, save

        column = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.RichText)
        self.status.setOpenExternalLinks(True)
        column.addWidget(self.status)

        column.addWidget(theme.role(QLabel(tr("Passwords sent to the browser (newest first):")), "muted"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("When"), tr("Website"), tr("Login")])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        column.addWidget(self.table, 1)
        self.empty = theme.role(QLabel(tr("Nothing has been sent yet.")), "muted")
        column.addWidget(self.empty)

        row = QHBoxLayout()
        self.clear_button = QPushButton(tr("Clear log"))
        self.clear_button.clicked.connect(self._clear)
        self.disconnect_button = QPushButton(tr("Disconnect extension"))
        self.disconnect_button.clicked.connect(self._disconnect)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.reject)
        row.addWidget(self.clear_button)
        row.addWidget(self.disconnect_button)
        row.addStretch()
        row.addWidget(close)
        column.addLayout(row)
        self._refresh()

    def _refresh(self):
        connected = bool(self.vault.bridge_keys)
        if connected:
            self.status.setText(tr("The browser extension is connected."))
        else:
            self.status.setText(tr("The browser extension is not connected.") + " "
                                + tr('How to install it: <a href="{url}">README on GitHub</a>.').format(url=README_URL))
        self.disconnect_button.setEnabled(connected)
        log = list(reversed(self.vault.access_log))
        self.table.setRowCount(len(log))
        for row, item in enumerate(log):
            for col, key in enumerate(("time", "site", "login")):
                self.table.setItem(row, col, QTableWidgetItem(item[key]))
        self.table.setVisible(bool(log))
        self.empty.setVisible(not log)
        self.clear_button.setEnabled(bool(log))

    def _clear(self):
        if self.save(self.vault.clear_access_log):
            self._refresh()

    def _disconnect(self):
        if not ask_yes(self, tr("Extension"), tr("Disconnect the browser extension?\nIt will no longer receive passwords. To connect it again, WhoKey will ask for permission once more.")):
            return
        if self.save(lambda: self.vault.set_bridge_keys([])):
            self._refresh()
