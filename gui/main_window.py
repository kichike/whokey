"""Главное окно: поиск, таблица записей и меню действий по правому клику."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFontDatabase, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMainWindow, QMenu, QPushButton, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from clipboard import CLEAR_AFTER
from gui import theme
from gui.dialogs import ChangeMasterDialog, EntryDialog, GeneratorDialog
from gui.widgets import ClipboardCountdown, ask_yes, show_error
from texts import t
from vault import SaveError

HIDDEN = "••••••••"   # одинаковые точки — не выдаём даже длину пароля
REVEAL_SECONDS = 15   # показанный пароль сам скроется через столько секунд
COLUMNS = ["site", "login", "password", "note", "updated"]


class MainWindow(QMainWindow):
    def __init__(self, vault, clipboard):
        super().__init__()
        self.vault = vault
        self.clipboard = clipboard
        self.revealed = None  # номер записи, чей пароль сейчас показан
        self.setWindowTitle(f"{t('g_app_title')} — {vault.path.name}")
        self.resize(960, 600)

        column = QVBoxLayout()
        column.setContentsMargins(24, 20, 24, 12)
        column.setSpacing(14)
        column.addLayout(self._header())
        column.addLayout(self._toolbar())
        column.addWidget(self._table_card(), 1)
        column.addWidget(theme.role(QLabel(t("g_hint")), "muted"))
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
        # ⌘C, ⌫ и Enter — только когда в фокусе таблица (WidgetShortcut). Иначе они
        # срабатывали бы во всём окне: Enter в поиске открывал бы правку записи,
        # а ⌘C в поиске копировал бы пароль вместо набранного текста.
        for keys, handler in [(QKeySequence.Copy, self.copy),
                              (QKeySequence(Qt.Key_Backspace), self.delete),
                              (QKeySequence(Qt.Key_Return), self.edit)]:
            QShortcut(keys, self.table, handler).setContext(Qt.WidgetShortcut)

        self.refresh()

    # --- части окна ---

    def _header(self):
        """Заголовок слева, общие действия справа."""
        row = QHBoxLayout()
        title = theme.neon_title(theme.role(QLabel(t("g_app_title")), "title"))
        row.addWidget(title)
        row.addWidget(theme.role(QLabel(t("g_tagline")), "muted"), 0, Qt.AlignBottom)
        row.addWidget(theme.role(QLabel(self.vault.path.name), "accent"), 0, Qt.AlignBottom)
        row.addStretch()
        for text, handler in [(t("g_generator"), self.open_generator),
                              (t("g_change_master"), self.change_master)]:
            button = QPushButton(text)
            button.clicked.connect(handler)
            row.addWidget(button)
        return row

    def _toolbar(self):
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("g_search"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda: self.refresh())
        row.addWidget(self.search, 1)
        add = theme.kind(QPushButton("+ " + t("g_add")), "primary")
        add.clicked.connect(self.add)
        row.addWidget(add)
        return row

    def _table_card(self):
        """Таблица в «карточке» с неоновым ореолом; если записей нет — подсказка вместо неё."""
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(
            [t("col_site"), t("col_login"), t("col_password"), t("col_note"), t("g_col_updated")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)  # правка — только в окне записи
        self.table.setShowGrid(False)
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

        self.empty = theme.role(QLabel(t("g_empty_list")), "muted")
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
        show = t("g_ctx_hide") if self.revealed == index else t("g_ctx_show")
        menu.addAction(show, self.toggle_reveal)
        menu.addAction(t("g_copy"), self.copy)
        login = menu.addAction(t("g_ctx_copy_login"), self.copy_login)
        login.setEnabled(bool(entry["login"]))
        menu.addSeparator()
        menu.addAction(t("g_ctx_edit"), self.edit)
        menu.addAction(t("g_delete"), self.delete)
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
        self.entries_count.setText(t("g_status_entries", n=len(self.vault.entries)))

    def _save(self, change):
        """Выполняет изменение хранилища и сообщает об ошибках записи. True — получилось."""
        try:
            change()
        except SaveError as error:
            # диск полон, нет прав на запись — изменение не применено
            show_error(self, t("save_failed", error=error))
            return False
        if self.vault.backup_error:
            self.statusBar().showMessage(t("backup_failed", error=self.vault.backup_error), 10000)
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
        changes = {k: v for k, v in dialog.values().items() if v != entry[k]}
        if changes and self._save(lambda: self.vault.update(index, **changes)):
            self.refresh(select=index)

    def delete(self):
        index = self.selected_index()
        if index is None:
            return
        entry = self.vault.entries[index]
        # без логина — без пустых скобок «()»
        question = (t("g_delete_question", site=entry["site"], login=entry["login"]) if entry["login"]
                    else t("g_delete_question_nologin", site=entry["site"]))
        if not ask_yes(self, t("g_delete_title"), question):
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
            QTimer.singleShot(REVEAL_SECONDS * 1000, lambda: self._auto_hide(index))

    def _auto_hide(self, index):
        if self.revealed == index:
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
            self.statusBar().showMessage(t("g_login_copied"), 5000)

    def copy_password(self, password):
        """Копирует через буфер с автоочисткой и запускает таймер внизу окна. True — получилось."""
        if not self.clipboard.copy(password):
            show_error(self, t("copy_failed"))
            return False
        self.statusBar().clearMessage()  # сообщение поверх скрыло бы таймер
        self.countdown.start(CLEAR_AFTER)
        return True

    def open_generator(self):
        GeneratorDialog(self, self.copy_password).exec()

    def change_master(self):
        if not ChangeMasterDialog(self, self.vault).exec():
            return
        self.statusBar().showMessage(t("master_changed"), 10000)
        if self.vault.backup_error:
            # копия со старым паролем при этом удалена — человек должен знать,
            # что резервной копии сейчас нет
            show_error(self, t("backup_failed", error=self.vault.backup_error))
            self.vault.backup_error = None
