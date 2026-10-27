"""Главное окно: поиск, таблица записей и меню действий по правому клику."""

import sys
from pathlib import Path

from PySide6.QtCore import QDateTime, QLocale, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFontDatabase, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMainWindow, QMenu, QPushButton, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

import csv_io
import sites
from gui import i18n, prefs, theme
from gui.dialogs import ChangeMasterDialog, EntryDialog, ExportDialog, ExtensionDialog, GeneratorDialog, SettingsDialog
from gui.widgets import ClipboardCountdown, RoundedRowDelegate, ask_yes, show_error, show_info
from gui.i18n import tr
from vault import SaveError

HIDDEN = "••••••••"   # одинаковые точки — не выдаём даже длину пароля
COLUMNS = ["site", "login", "password", "note", "updated"]


def shortcut_text(keys):
    """«⌘,» на Mac и «Ctrl+,» на Windows — для подсказок на кнопках."""
    return "(" + QKeySequence(keys).toString(QKeySequence.NativeText) + ")"


class SortItem(QTableWidgetItem):
    """Ячейка, которая сортируется по своему ключу: без учёта регистра («apple» перед «Zoom»),
    а дата — по самой дате, а не по тексту на выбранном языке."""

    def __init__(self, text, key):
        super().__init__(text)
        self.key = key

    def __lt__(self, other):
        return self.key < getattr(other, "key", other.text())


def shown_date(stamp):
    """«2026-10-27 22:54» из хранилища — в привычном виде для выбранного языка."""
    moment = QDateTime.fromString(stamp, "yyyy-MM-dd HH:mm")
    if not moment.isValid():
        return stamp
    return QLocale("ru_RU" if i18n.LANG == "ru" else "en_US").toString(moment, QLocale.ShortFormat)


def TABLE_KEYS(window):
    """Клавиши действий с выбранной записью (работают, когда в фокусе таблица)."""
    return [(QKeySequence.Copy, window.copy),                          # ⌘C / Ctrl+C
            (QKeySequence("Ctrl+Shift+C"), window.copy_login),         # ⌘⇧C — как в 1Password
            (QKeySequence.Open, window.open_website),                  # ⌘O / Ctrl+O
            (QKeySequence(Qt.Key_Space), window.toggle_reveal),        # пробел — показать / скрыть
            (QKeySequence(Qt.Key_Return), window.edit),
            (QKeySequence(Qt.Key_Backspace), window.delete),           # ⌫ на Mac
            (QKeySequence.Delete, window.delete)]                      # Delete на Windows


def TABLE_TEXTS():
    return [tr("Copy password"), tr("Copy login"), tr("Open website"), tr("Show / hide password"),
            tr("Edit…"), tr("Delete"), None]


def site_link(entry):
    """Ссылка на сайт записи: из «Адреса сайта», а если он пуст — из названия,
    если оно похоже на адрес (github.com). None — открыть нечего («госуслуги»)."""
    for text in (entry.get("url", ""), entry.get("site", "")):
        host = sites.normalize(text)
        if host and ("." in host.split(":")[0] or host.startswith("localhost")):
            scheme = "http" if host.startswith(("localhost", "127.", "[::1]")) else "https"
            return f"{scheme}://{host}"
    return None


class MainWindow(QMainWindow):
    language_changed = Signal(str)  # выбран другой язык в настройках — app.py пересоздаст окно
    lock_requested = Signal()       # «Заблокировать» (⌘L / Ctrl+L) — app.py вернёт окно входа

    def __init__(self, vault, clipboard):
        super().__init__()
        self.vault = vault
        self.clipboard = clipboard
        self.revealed = None  # номер записи, чей пароль сейчас показан
        self.reveal_timer = QTimer(self)
        self.reveal_timer.setSingleShot(True)
        self.reveal_timer.timeout.connect(self._auto_hide)
        self.setWindowTitle(tr("WhoKey") + " — " + vault.path.name)
        self.resize(960, 600)

        column = QVBoxLayout()
        column.setContentsMargins(24, 20, 24, 12)
        column.setSpacing(14)
        column.addLayout(self._header())
        column.addLayout(self._toolbar())
        column.addWidget(self._table_card(), 1)
        column.addWidget(theme.role(QLabel(tr("Right-click an entry for actions. Double-click to edit.")), "muted"))
        central = QWidget()
        central.setLayout(column)
        self.setCentralWidget(central)

        # слева в строке состояния — сообщения и таймер буфера, справа — число записей
        self.countdown = ClipboardCountdown(bar_width=220)
        self.countdown.setContentsMargins(22, 0, 0, 4)  # вровень с содержимым окна
        self.statusBar().addWidget(self.countdown)
        self.entries_count = theme.role(QLabel(), "muted")
        self.statusBar().addPermanentWidget(self.entries_count)

        # горячие клавиши (Qt сам заменяет Ctrl на ⌘ на Mac) — те же, что показаны в меню
        QShortcut(QKeySequence.New, self, self.add)
        QShortcut(QKeySequence.Find, self, self.search.setFocus)
        QShortcut(QKeySequence("Ctrl+,"), self, self.open_settings)
        QShortcut(QKeySequence("Ctrl+L"), self, self.lock_requested.emit)
        # действия с записью — только когда в фокусе таблица (WidgetShortcut). Иначе они
        # срабатывали бы во всём окне: Enter в поиске открывал бы правку записи,
        # а ⌘C в поиске копировал бы пароль вместо набранного текста.
        for keys, handler in TABLE_KEYS(self):
            QShortcut(keys, self.table, handler).setContext(Qt.WidgetShortcut)
        # из поиска — в результаты: ↓ или Enter
        for key in (Qt.Key_Down, Qt.Key_Return, Qt.Key_Enter):
            QShortcut(QKeySequence(key), self.search, self._to_results).setContext(Qt.WidgetShortcut)
        self._menus()

        self.refresh()

    def _menus(self):
        """Строка меню: все действия и их клавиши в одном месте (на Mac — вверху экрана)."""
        bar = self.menuBar()
        file_menu = bar.addMenu(tr("File"))
        for text, keys, handler in [(tr("New entry"), QKeySequence.New, self.add),
                                    (tr("Import from CSV…"), None, self.import_csv),
                                    (tr("Export to CSV…"), None, self.export_csv),
                                    (tr("Settings…"), QKeySequence("Ctrl+,"), self.open_settings),
                                    (tr("Lock WhoKey"), QKeySequence("Ctrl+L"), self.lock_requested.emit)]:
            self._menu_action(file_menu, text, keys, handler)
        entry_menu = bar.addMenu(tr("Entry"))
        for (keys, handler), text in zip(TABLE_KEYS(self), TABLE_TEXTS()):
            if text is None:  # вторая клавиша того же действия — в меню не дублируем
                continue
            if handler == self.delete and sys.platform == "win32":
                keys = QKeySequence.Delete  # на Windows в меню показываем привычную Delete
            self._menu_action(entry_menu, text, keys, handler)

    def _menu_action(self, menu, text, keys, handler):
        action = menu.addAction(text)
        action.triggered.connect(lambda: handler())
        if keys is not None:
            action.setShortcut(keys)
            # клавиша только показана в меню, а работает через QShortcut выше (в нужном месте окна)
            action.setShortcutContext(Qt.WidgetShortcut)
        return action

    def _to_results(self):
        if self.table.rowCount():
            self.table.setFocus()
            if self.selected_index() is None:
                self.table.selectRow(0)

    # --- части окна ---

    def _header(self):
        """Заголовок слева, общие действия справа."""
        row = QHBoxLayout()
        title = theme.neon_title(theme.role(QLabel(tr("WhoKey")), "title"))
        row.addWidget(title)
        row.addWidget(theme.role(QLabel(tr("password manager")), "muted"), 0, Qt.AlignBottom)
        row.addWidget(theme.role(QLabel(self.vault.path.name), "accent"), 0, Qt.AlignBottom)
        row.addStretch()
        for text, tip, handler in [(tr("Generator"), "", self.open_generator),
                                   (tr("Extension"), "", self.extension),
                                   (tr("Settings"), shortcut_text("Ctrl+,"), self.open_settings),
                                   ("🔒", tr("Lock WhoKey") + " " + shortcut_text("Ctrl+L"), self.lock_requested.emit)]:
            button = QPushButton(text)
            button.setToolTip(tip)
            button.clicked.connect(lambda checked=False, h=handler: h())
            row.addWidget(button)
        return row

    def _toolbar(self):
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search by name, login or note"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda: self.refresh())
        row.addWidget(self.search, 1)
        add = theme.kind(QPushButton("+ " + tr("Add")), "primary")
        add.clicked.connect(lambda: self.add())  # без lambda clicked передал бы False вместо адреса
        row.addWidget(add)
        return row

    def _table_card(self):
        """Таблица в «карточке» с неоновым ореолом; если записей нет — подсказка вместо неё."""
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(
            [tr("Name"), tr("Login"), tr("Password"), tr("Note"), tr("Updated")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)  # правка — только в окне записи
        self.table.setShowGrid(False)
        self.table.setItemDelegate(RoundedRowDelegate(self.table))  # выделение — скруглённой плашкой
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # по умолчанию — по сайту от А до Я (Qt сам начал бы с обратного порядка)
        self.table.horizontalHeader().setSortIndicator(0, Qt.AscendingOrder)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self.edit)
        # правый клик — меню действий с записью
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)

        self.empty = theme.role(QLabel(tr("No entries yet — click \"+ Add\".")), "muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.nothing_found = theme.role(QLabel(tr("Nothing found.")), "muted")
        self.nothing_found.setAlignment(Qt.AlignCenter)

        card = theme.role(QFrame(), "card")
        self.stack = QStackedWidget()
        inside = QVBoxLayout(card)
        inside.setContentsMargins(8, 8, 8, 8)  # чтобы таблица не залезала на скруглённые углы
        inside.addWidget(self.stack)
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.nothing_found)
        theme.neon_card(card)
        return card

    def _context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        self.table.selectRow(row)  # правый клик сразу выделяет запись, как в Finder
        index = self.selected_index()
        entry = self.vault.entries[index]

        menu = theme.rounded_menu(QMenu(self))
        show = tr("Hide password") if self.revealed == index else tr("Show password")
        menu.addAction(show, self.toggle_reveal)
        menu.addAction(tr("Copy password"), self.copy)
        login = menu.addAction(tr("Copy login"), self.copy_login)
        login.setEnabled(bool(entry["login"]))
        website = menu.addAction(tr("Open website"), self.open_website)
        website.setEnabled(site_link(entry) is not None)
        menu.addSeparator()
        menu.addAction(tr("Edit…"), self.edit)
        menu.addAction(tr("Delete"), self.delete)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # --- таблица ---

    def selected_index(self):
        """Номер выбранной записи в хранилище (не номер строки — таблицу можно сортировать)."""
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole)

    def refresh(self, select=None):
        """Перерисовывает таблицу. select — номер записи, которую выделить."""
        if select is None:
            select = self.selected_index()
        query = self.search.text().strip()
        indexes = self.vault.search(query) if query else range(len(self.vault.entries))

        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.table.setSortingEnabled(False)  # иначе строки перемешиваются, пока их заполняешь
        self.table.setRowCount(0)
        for index in indexes:
            entry = self.vault.entries[index]
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, field in enumerate(COLUMNS):
                if field == "password":
                    text = entry["password"] if index == self.revealed else HIDDEN
                else:
                    text = entry[field]
                    if field == "note":
                        text = " ⏎ ".join(line for line in text.splitlines() if line.strip())  # заметка — в одну строку
                if field == "updated":
                    item = SortItem(shown_date(text), text)
                else:
                    item = SortItem(text, text.casefold())
                if field != "password":
                    item.setToolTip(text if field != "updated" else item.text())  # обрезанное — целиком
                if field == "password" and index == self.revealed:
                    item.setFont(mono)  # в моноширинном шрифте не спутать l и 1, O и 0
                    item.setForeground(QColor(theme.ACC_LIGHT))
                elif field in ("note", "updated"):
                    item.setForeground(QColor(theme.MUTED))
                item.setData(Qt.UserRole, index)
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)

        if select is not None:
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0).data(Qt.UserRole) == select:
                    self.table.selectRow(row)
                    break
        # пустое хранилище — вместо пустой таблицы подсказка; ничего не нашлось — так и пишем
        if not self.vault.entries:
            self.stack.setCurrentWidget(self.empty)
        elif not self.table.rowCount():
            self.stack.setCurrentWidget(self.nothing_found)
        else:
            self.stack.setCurrentWidget(self.table)
        # число — отдельной переменной, а не len() внутри: иначе lupdate не поймёт,
        # что у надписи есть формы «1 запись / 2 записи / 5 записей»
        count = len(self.vault.entries)
        self.entries_count.setText(self.tr("%n entries", "", count))

    def _save(self, change):
        """Выполняет изменение хранилища и сообщает об ошибках записи. True — получилось."""
        try:
            change()
        except SaveError as error:
            # диск полон, нет прав на запись — изменение не применено
            show_error(self, tr("⚠ Could not save: {error}. The change was not applied, the file on disk is untouched.").format(error=error))
            return False
        if self.vault.backup_error:
            self.statusBar().showMessage(tr("⚠ The change is saved, but the backup was not updated: {error}.").format(error=self.vault.backup_error), 10000)
            self.vault.backup_error = None
        return True

    # --- действия ---

    def add(self, url=""):
        """Новая запись; url — адрес сайта, если запись добавляют из расширения браузера."""
        entry = {"site": url, "login": "", "password": "", "note": "", "url": url} if url else None
        dialog = EntryDialog(self, entry, copy_password=self.copy_password)
        if dialog.exec() and self._save(lambda: self.vault.add(**dialog.values())):
            self.search.clear()
            self.refresh(select=len(self.vault.entries) - 1)

    def edit(self):
        index = self.selected_index()
        if index is None:
            return
        entry = self.vault.entries[index]
        dialog = EntryDialog(self, entry, copy_password=self.copy_password)
        if not dialog.exec():
            return
        changes = {k: v for k, v in dialog.values().items() if v != entry.get(k, "")}  # у старых записей нет url
        if changes and self._save(lambda: self.vault.update(index, **changes)):
            self.refresh(select=index)

    def delete(self):
        index = self.selected_index()
        if index is None:
            return
        entry = self.vault.entries[index]
        # без логина — без пустых скобок «()»
        question = (tr("Delete \"{site}\" ({login})?\nThis cannot be undone.").format(site=entry["site"], login=entry["login"]) if entry["login"]
                    else tr("Delete \"{site}\"?\nThis cannot be undone.").format(site=entry["site"]))
        if not ask_yes(self, tr("Delete entry"), question):
            return
        if self._save(lambda: self.vault.delete(index)):
            # номера записей после удалённой сдвинулись — показанный пароль прячем
            self.revealed = None
            self.refresh(select=-1)

    def toggle_reveal(self):
        index = self.selected_index()
        if index is None:
            return
        self.revealed = None if self.revealed == index else index
        self.refresh(select=index)
        if self.revealed is not None:
            # один таймер окна: перезапускается при каждом показе (старый не спрячет раньше)
            # и удаляется вместе с окном (не сработает на уже удалённой таблице)
            self.reveal_timer.start(prefs.reveal_seconds() * 1000)

    def _auto_hide(self):
        if self.revealed is not None:
            self.revealed = None
            self.refresh()

    def copy(self):
        index = self.selected_index()
        if index is not None:
            self.copy_password(self.vault.entries[index]["password"])

    def copy_login(self):
        """Логин — не секрет, поэтому обычное копирование, без автоочистки."""
        index = self.selected_index()
        if index is not None:
            QGuiApplication.clipboard().setText(self.vault.entries[index]["login"])
            self.statusBar().showMessage(tr("Login copied."), 5000)

    def copy_password(self, password):
        """Копирует через буфер с автоочисткой и запускает таймер внизу окна. True — получилось."""
        if not self.clipboard.copy(password):
            show_error(self, tr("Could not copy the password to the clipboard."))
            return False
        self.statusBar().clearMessage()  # сообщение поверх скрыло бы таймер
        self.countdown.start(prefs.clear_after())
        return True

    def import_csv(self):
        """Пароли из CSV-файла браузера или другого менеджера паролей."""
        name, _ = QFileDialog.getOpenFileName(self, tr("Import from CSV"), str(Path.home() / "Downloads"),
                                              tr("CSV files (*.csv);;All files (*)"))
        if not name:
            return
        try:
            found = csv_io.read(name)
        except OSError as error:
            show_error(self, tr("Could not read the file: {error}").format(error=error.strerror or error))
            return
        except csv_io.CsvError as error:
            show_error(self, {
                "too_big": tr("The file is too big for a password list."),
                "encoding": tr("The file is not in UTF-8 encoding. Export the passwords again or save the file as UTF-8."),
            }.get(str(error), tr("No passwords found in this file. It needs columns with the name or website address and the password, as in an export from a browser, Bitwarden or KeePassXC.")))
            return
        entries = csv_io.new_only(found, self.vault.entries)
        skipped = len(found) - len(entries)
        if not entries:
            show_info(self, tr("Import from CSV"), tr("All passwords from this file are already in WhoKey."))
            return
        count = len(entries)  # отдельной переменной — см. refresh (формы слова для числа)
        question = self.tr("Add %n passwords to WhoKey?", "", count)
        if skipped:
            question += "\n" + self.tr("%n are already in WhoKey and will be skipped.", "", skipped)
        if not ask_yes(self, tr("Import from CSV"), question):
            return
        if self._save(lambda: self.vault.add_many(entries)):
            self.search.clear()
            self.refresh()
            show_info(self, tr("Import from CSV"), self.tr("Added %n passwords.", "", count) + "\n\n" +
                      tr("The CSV file is not encrypted — delete it now (and empty the Trash)."))

    def export_csv(self):
        """Все пароли в CSV-файл — после мастер-пароля и предупреждения, что файл не зашифрован."""
        if not self.vault.entries:
            show_info(self, tr("Export to CSV"), tr("There are no entries to export yet."))
            return
        if not ExportDialog(self, self.vault).exec():
            return
        name, _ = QFileDialog.getSaveFileName(self, tr("Export to CSV"), str(Path.home() / "Desktop" / "WhoKey.csv"),
                                              tr("CSV files (*.csv)"))
        if not name:
            return
        count = len(self.vault.entries)
        try:
            csv_io.write(name, self.vault.entries)
        except OSError as error:
            show_error(self, tr("Could not write the file: {error}").format(error=error.strerror or error))
            return
        show_info(self, tr("Export to CSV"), self.tr("Exported %n passwords.", "", count) + "\n\n" +
                  tr("The CSV file is not encrypted — delete it as soon as you no longer need it (and empty the Trash)."))

    def extension(self):
        """Расширение браузера: подключено ли, журнал выдач паролей, «Отключить»."""
        ExtensionDialog(self, self.vault, self._save).exec()

    def open_generator(self):
        GeneratorDialog(self, self.copy_password).exec()

    def open_website(self):
        """Открывает сайт записи в браузере по умолчанию."""
        index = self.selected_index()
        if index is None:
            return
        link = site_link(self.vault.entries[index])
        if link is not None:
            QDesktopServices.openUrl(QUrl(link))

    def open_settings(self):
        dialog = SettingsDialog(self, self.vault, self.change_master)
        dialog.language_chosen.connect(self.language_changed)
        dialog.exec()

    def change_master(self):
        if not ChangeMasterDialog(self, self.vault).exec():
            return
        self.statusBar().showMessage(tr("Master password changed, vault re-encrypted."), 10000)
        if self.vault.backup_error:
            # копия со старым паролем при этом удалена — человек должен знать,
            # что резервной копии сейчас нет
            show_error(self, tr("⚠ The change is saved, but the backup was not updated: {error}.").format(error=self.vault.backup_error))
            self.vault.backup_error = None
