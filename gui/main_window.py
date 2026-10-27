"""Главное окно: поиск, таблица записей и меню действий по правому клику."""

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFontDatabase, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMainWindow, QMenu, QPushButton, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

import sites
from clipboard import CLEAR_AFTER
from gui import theme
from gui.dialogs import ChangeMasterDialog, EntryDialog, GeneratorDialog, SettingsDialog
from gui.widgets import REVEAL_SECONDS, ClipboardCountdown, RoundedRowDelegate, ask_yes, show_error, show_info
from gui.i18n import tr
from vault import SaveError

HIDDEN = "••••••••"   # одинаковые точки — не выдаём даже длину пароля
COLUMNS = ["site", "login", "password", "note", "updated"]


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

        # горячие клавиши, как в обычных программах Mac
        QShortcut(QKeySequence.New, self, self.add)
        QShortcut(QKeySequence.Find, self, self.search.setFocus)
        # настройки — ⌘, на Mac (Qt сам заменяет Ctrl на ⌘), Ctrl+, на Windows
        QShortcut(QKeySequence("Ctrl+,"), self, self.open_settings)
        # ⌘C, ⌫ и Enter — только когда в фокусе таблица (WidgetShortcut). Иначе они
        # срабатывали бы во всём окне: Enter в поиске открывал бы правку записи,
        # а ⌘C в поиске копировал бы пароль вместо набранного текста.
        for keys, handler in [(QKeySequence.Copy, self.copy),
                              (QKeySequence.Open, self.open_website),  # ⌘O / Ctrl+O
                              (QKeySequence(Qt.Key_Backspace), self.delete),
                              (QKeySequence(Qt.Key_Return), self.edit)]:
            QShortcut(keys, self.table, handler).setContext(Qt.WidgetShortcut)

        self.refresh()

    # --- части окна ---

    def _header(self):
        """Заголовок слева, общие действия справа."""
        row = QHBoxLayout()
        title = theme.neon_title(theme.role(QLabel(tr("WhoKey")), "title"))
        row.addWidget(title)
        row.addWidget(theme.role(QLabel(tr("password manager")), "muted"), 0, Qt.AlignBottom)
        row.addWidget(theme.role(QLabel(self.vault.path.name), "accent"), 0, Qt.AlignBottom)
        row.addStretch()
        for text, handler in [(tr("Generator"), self.open_generator),
                              (tr("Extension"), self.extension),
                              (tr("Settings"), self.open_settings)]:
            button = QPushButton(text)
            button.clicked.connect(handler)
            row.addWidget(button)
        return row

    def _toolbar(self):
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search by site, login or note"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda: self.refresh())
        row.addWidget(self.search, 1)
        add = theme.kind(QPushButton("+ " + tr("Add")), "primary")
        add.clicked.connect(self.add)
        row.addWidget(add)
        return row

    def _table_card(self):
        """Таблица в «карточке» с неоновым ореолом; если записей нет — подсказка вместо неё."""
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(
            [tr("Site"), tr("Login"), tr("Password"), tr("Note"), tr("Updated")])
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

        card = theme.role(QFrame(), "card")
        self.stack = QStackedWidget()
        inside = QVBoxLayout(card)
        inside.setContentsMargins(8, 8, 8, 8)  # чтобы таблица не залезала на скруглённые углы
        inside.addWidget(self.stack)
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
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
                item = QTableWidgetItem(text)
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
        # пустое хранилище — вместо пустой таблицы подсказка
        self.stack.setCurrentWidget(self.empty if not self.vault.entries else self.table)
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

    def add(self):
        dialog = EntryDialog(self, copy_password=self.copy_password)
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
            self.reveal_timer.start(REVEAL_SECONDS * 1000)

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
        self.countdown.start(CLEAR_AFTER)
        return True

    def extension(self):
        """Расширение браузера: подключено ли — и кнопка «отключить»."""
        if not self.vault.bridge_keys:
            show_info(self, tr("Extension"), tr("The browser extension is not connected.\nHow to install it — see the README on GitHub."))
            return
        if not ask_yes(self, tr("Extension"), tr("Disconnect the browser extension?\nIt will no longer receive passwords. To connect it again, WhoKey will ask for permission once more.")):
            return
        if self._save(lambda: self.vault.set_bridge_keys([])):
            self.statusBar().showMessage(tr("Extension disconnected"), 8000)

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
