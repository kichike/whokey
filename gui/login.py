"""Окно входа: открыть хранилище, создать новое или восстановить из копии.

Логика та же, что у консольной версии (manager.py), включая всё, что
исправлено после двух независимых проверок.
"""

import os
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from generator import weakness_reasons
from gui import theme
from gui.widgets import PasswordField, StrengthBar, ask_yes, show_error, show_info, weakness_text
import texts
from texts import set_language, t
from vault import (SaveError, Vault, VaultError, VaultLocked, WrongPassword, backup_path,
                   in_icloud_folder, is_readable, lock, open_backup, tidy_old_files)

MASTER_MIN_LENGTH = 12
LANGUAGES = [("ru", "Русский"), ("en", "English")]

# Замок на файл хранилища держим, пока программа работает: второе окно
# (или консольная версия) с тем же файлом иначе затёрло бы записи.
_lock = {"path": None, "fd": None}


def hold_lock(path):
    """Берёт замок на файл. VaultLocked — если он уже открыт где-то ещё."""
    if _lock["path"] == path:
        return
    if _lock["fd"] is not None:  # выбрали другой файл — старый отпускаем
        os.close(_lock["fd"])
        _lock["path"] = _lock["fd"] = None
    _lock["fd"] = lock(path)
    _lock["path"] = path


class LoginWindow(QWidget):
    opened = Signal(object)   # хранилище открыто — передаём Vault
    restart = Signal(object)  # сменили язык или файл — окно пересоздаётся (передаём путь)

    def __init__(self, path, state):
        """state — общее для пересоздаваемых окон: флаг «создать новое»
        и сообщение, которое надо показать в новом окне (state["notice"])."""
        super().__init__()
        self.path = path
        self.state = state
        self.setWindowTitle(t("g_app_title"))
        self.resize(560, 1)  # начальная ширина, а не минимум — см. EntryDialog

        # снаружи — выбор языка, внутри «карточки» с жёсткой тенью — всё остальное
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 20, 40, 40)  # место для неонового ореола вокруг карточки
        theme.role(self, "backdrop")  # фон окна с фиолетовым заревом
        outer.setSpacing(16)
        outer.addLayout(self._language_row())
        card = theme.role(QFrame(), "card")
        theme.neon_card(card)
        outer.addWidget(card)

        column = QVBoxLayout(card)
        column.setContentsMargins(28, 24, 28, 24)
        column.setSpacing(12)
        column.addWidget(theme.neon_title(theme.role(QLabel(t("g_app_title")), "title")))
        column.addWidget(theme.role(QLabel(t("g_tagline")), "muted"))
        column.addLayout(self._file_row())

        tidy_old_files(path)  # копия и замок от прежней версии — на новые места
        # state["create"] — человек нажал «Создать новое», хотя копия есть
        if path.exists():
            self._build_open(column)
        elif backup_path(path).exists() and not state.pop("create", False):
            self._build_missing(column)
        else:
            self._build_create(column)

        self.error = theme.role(QLabel(), "error")
        self.error.setWordWrap(True)
        self.error.setText(state.pop("notice", ""))
        column.addWidget(self.error)
        outer.addStretch()

    # --- общие части окна ---

    def _language_row(self):
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(QLabel(t("g_language")))
        combo = theme.rounded_popup(QComboBox())
        for code, name in LANGUAGES:
            combo.addItem(name, code)
        combo.setCurrentIndex([code for code, _ in LANGUAGES].index(texts.LANG))
        # отступы пунктов в оформлении Qt при расчёте ширины списка не учитывает — добавляем сами
        combo.view().setMinimumWidth(combo.view().sizeHintForColumn(0) + 48)
        combo.currentIndexChanged.connect(lambda i: self._set_language(combo.itemData(i)))
        row.addWidget(combo)
        return row

    def _set_language(self, code):
        set_language(code)
        self.restart.emit(self.path)

    def _file_row(self):
        row = QHBoxLayout()
        # невидимые точки переноса после «\» и «/»: длинный путь Windows (C:\Users\…)
        # иначе не переносится и обрезается справа
        shown = str(self.path).replace("\\", "\\\u200b").replace("/", "/\u200b")
        label = theme.role(QLabel(f"{t('g_vault_file')} {shown}"), "muted")
        label.setWordWrap(True)
        row.addWidget(label, 1)
        other = QPushButton(t("g_other_file"))
        other.clicked.connect(self._choose_file)
        row.addWidget(other)
        return row

    def _choose_file(self):
        # «Сохранить как» без вопроса о замене: подходит и чтобы выбрать
        # существующий файл, и чтобы указать имя нового
        name, _ = QFileDialog.getSaveFileName(
            self, t("g_choose_file"), str(self.path), t("g_files_filter"),
            options=QFileDialog.DontConfirmOverwrite)
        if name:
            self.restart.emit(Path(name).resolve())

    def _button(self, text, handler, default=False):
        button = QPushButton(text)
        button.clicked.connect(handler)
        button.setDefault(default)
        if default:
            theme.kind(button, "primary")  # главное действие — лавандовая кнопка
        return button

    # --- три режима окна ---

    def _build_open(self, column):
        self.master = PasswordField(t("g_master"))
        self.master.edit.returnPressed.connect(self.on_open)
        column.addWidget(self.master)
        column.addWidget(self._button(t("g_open"), self.on_open, default=True))
        self.master.setFocus()

    def _build_missing(self, column):
        text = QLabel(t("g_missing_question", name=self.path.name,
                        backup=backup_path(self.path).name))
        text.setWordWrap(True)
        column.addWidget(text)
        self.master = PasswordField(t("g_master"))
        self.master.edit.returnPressed.connect(self.on_restore)
        column.addWidget(self.master)
        row = QHBoxLayout()
        row.addWidget(self._button(t("g_create_new"), self._switch_to_create))
        row.addStretch()
        row.addWidget(self._button(t("g_restore"), self.on_restore, default=True))
        column.addLayout(row)
        self.master.setFocus()

    def _build_create(self, column):
        hint = QLabel(t("g_create_hint") + "\n" + t("new_master_rules"))
        hint.setWordWrap(True)
        column.addWidget(hint)
        self.master = PasswordField(t("g_master"))
        self.repeat = PasswordField(t("g_master_repeat"))
        self.repeat.edit.returnPressed.connect(self.on_create)
        self.strength = StrengthBar("g_strength_master_empty")
        self.master.textChanged.connect(self.strength.show_for)
        for widget in (self.master, self.repeat, self.strength):
            column.addWidget(widget)
        column.addWidget(self._button(t("g_create"), self.on_create, default=True))
        self.master.setFocus()

    def _switch_to_create(self):
        """Из режима «файл пропал» — в режим создания (старая копия отложится сама)."""
        self.state["create"] = True
        self.restart.emit(self.path)

    # --- действия ---

    def _take_lock(self):
        try:
            # при первом запуске папки ~/Library/Application Support/EduPasswords
            # ещё нет — а файл-замок кладётся рядом с хранилищем, поэтому создаём её сразу
            self.path.parent.mkdir(parents=True, exist_ok=True)
            hold_lock(self.path)
            return True
        except VaultLocked:
            self.error.setText(t("vault_locked"))
        except OSError as error:
            self.error.setText(t("lock_error", path=self.path, error=error.strerror or error))
        return False

    def _wrong_password(self):
        # Без ограничения попыток: оно лишь косметика (обходится перезапуском),
        # а от перебора защищает медленная функция Argon2id.
        self.master.clear()
        self.error.setText(t("wrong_password"))

    def _restore(self, vault):
        vault.path = self.path
        try:
            vault.save()
        except SaveError as error:
            show_error(self, t("save_failed", error=error))
            return
        show_info(self, t("g_restore_title"), t("restored"))
        self.opened.emit(vault)

    def _offer_restore(self, backup):
        """Пароль подошёл к копии той же «эпохи» — значит, испорчен файл, а не забыт пароль."""
        if ask_yes(self, t("g_restore_title"), t("main_damaged") + "\n\n" + t("restore_question")):
            self._restore(backup)
        else:
            self.error.setText(t("restore_declined"))

    def on_open(self):
        password = self.master.text()
        if not password or not self._take_lock():
            return
        try:
            vault = Vault.open(self.path, password)
        except WrongPassword:
            backup = open_backup(self.path, password)
            if backup is not None:
                self._offer_restore(backup)
            else:
                # без подсказок: не говорим, «почти» ли угадан пароль и т.п.
                self._wrong_password()
            return
        except VaultError:
            backup = open_backup(self.path, password)
            if backup is not None:
                self._offer_restore(backup)
            elif backup_path(self.path).exists() and is_readable(backup_path(self.path)):
                self._wrong_password()  # копия цела, но пароль к ней не подошёл
            elif backup_path(self.path).exists():
                # испорчены и файл, и копия — честно говорим, что дело в файлах,
                # иначе человек решит, что забыл пароль
                self.error.setText(t("g_both_damaged"))
            else:
                self.error.setText(t("vault_damaged", path=self.path))
            return
        self.opened.emit(vault)

    def on_restore(self):
        password = self.master.text()
        if not password or not self._take_lock():
            return
        backup = open_backup(self.path, password)
        if backup is None:
            self._wrong_password()
            return
        self._restore(backup)

    def on_create(self):
        password = self.master.text()
        if len(password) < MASTER_MIN_LENGTH:
            self.error.setText(t("too_short", n=len(password)))
            return
        # короткие уже отсеяли — остальные слабости только предупреждение
        reasons = [r for r in weakness_reasons(password) if r != "weak_short"]
        if reasons and not ask_yes(self, t("g_weak_title"),
                                   t("g_weak_question", reasons=weakness_text(reasons))):
            return
        if self.repeat.text() != password:
            self.error.setText(t("mismatch"))
            self.repeat.clear()
            return
        if not self._take_lock():
            return
        if self.path.exists():
            # пока окно было открыто, файл появился (например, его создала консольная
            # версия) — не затираем его новым пустым хранилищем, а предлагаем открыть
            self.state["notice"] = t("g_file_appeared")
            self.restart.emit(self.path)
            return
        try:
            vault = Vault.create(self.path, password)
        except (SaveError, OSError) as error:
            show_error(self, t("save_failed", error=error))
            return
        notes = [t("vault_created", path=self.path)]
        if vault.old_backup:
            notes.append(t("old_backup_kept", name=vault.old_backup.name))
        if in_icloud_folder(self.path):
            notes.append(t("g_icloud"))
        show_info(self, t("g_app_title"), "\n\n".join(notes))
        self.opened.emit(vault)
