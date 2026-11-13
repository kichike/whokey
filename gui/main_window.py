"""Главное окно: поиск, таблица записей и меню действий по правому клику."""

import os
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QDesktopServices, QFontDatabase, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMainWindow, QMenu, QPushButton, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

import csv_io
import sites
from gui import prefs, theme
from gui.dates import full_date, shown_date
from gui.dialogs import AboutDialog, ChangeMasterDialog, EntryDialog, ExportDialog, ExtensionDialog, GeneratorDialog, SettingsDialog
from gui.widgets import ClickableLabel, ClipboardCountdown, RoundedRowDelegate, ask_yes, choose_csv, save_problem, show_error, show_info
from gui.i18n import tr
from gui.sound import play_purr
from gui import cat
from vault import SaveError
from version import GITHUB_URL

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
            return sites.link(text if text == entry.get("url") else host)
    return None


EGG_CLICK_GAP = 1.5  # секунд между нажатиями на ключ, чтобы они считались одной серией


class MainWindow(QMainWindow):
    language_changed = Signal(str)  # выбран другой язык в настройках — app.py пересоздаст окно
    lock_requested = Signal()       # «Заблокировать» (⌘L / Ctrl+L) — app.py вернёт окно входа
    update_requested = Signal()     # нажата «Обновить до …» — app.py скачает и поставит (gui/updater.py)
    updater = None                  # проверка обновлений (app.Controller); для «О программе»

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
        central = QWidget()
        central.setLayout(column)
        self.setCentralWidget(central)

        # слева в строке состояния — сообщения и таймер буфера, справа — число записей
        self.countdown = ClipboardCountdown(bar_width=220)
        self.countdown.setContentsMargins(22, 0, 0, 4)  # вровень с содержимым окна
        self.statusBar().addWidget(self.countdown)
        # подсказка — в строке состояния (пока нет таймера буфера), а не отдельной строкой над ней
        new_entry = QKeySequence(QKeySequence.New).toString(QKeySequence.NativeText)
        self.hint = theme.role(QLabel(tr("Right-click — actions  ·  double-click — edit  ·  {keys} — new entry").format(keys=new_entry)), "faint")
        self.hint.setContentsMargins(22, 0, 0, 4)
        self.statusBar().addWidget(self.hint)
        self.countdown.finished.connect(self.hint.show)
        self.entries_count = theme.role(QLabel(), "muted")
        self.statusBar().addPermanentWidget(self.entries_count)
        if theme.SYSTEM:  # точки уголка-растяжки торчали бы из скруглённого угла стекла
            self.statusBar().setSizeGripEnabled(False)
            self.entries_count.setContentsMargins(0, 0, 14, 4)

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
        # после входа — сразу в поиск (иначе фокус доставался первой кнопке, «Генератору»)
        self.search.setFocus()

    def _menus(self):
        """Строка меню: все действия и их клавиши в одном месте (на Mac — вверху экрана)."""
        bar = self.menuBar()
        file_menu = bar.addMenu(tr("File"))
        for text, keys, handler in [(tr("New entry"), QKeySequence.New, self.add),
                                    (tr("Import from CSV…"), None, self.import_csv),
                                    (tr("Export to CSV…"), None, self.export_csv),
                                    (tr("Save encrypted copy…"), None, self.save_copy),
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
        help_menu = bar.addMenu(tr("Help"))
        about = self._menu_action(help_menu, tr("About WhoKey"), None, self.about)
        about.setMenuRole(QAction.AboutRole)  # на Mac — в меню программы, как у всех
        # на Mac «О программе» уезжает в меню WhoKey, а пустую «Справку» система прячет —
        # поэтому в ней своя строка: страница проекта (README, новые версии, сообщить о проблеме)
        github = self._menu_action(help_menu, tr("WhoKey on GitHub"), None,
                                   lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        github.setMenuRole(QAction.NoRole)

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
        row.setSpacing(10)
        self.logo = ClickableLabel()
        self.logo.setPixmap(theme.logo_pixmap(36))  # пиксельный ключ с иконки WhoKey
        self.logo.clicked.connect(self._logo_clicked)
        row.addWidget(self.logo)
        title = theme.neon_title(theme.role(QLabel(tr("WhoKey")), "title"))
        row.addWidget(title)
        # открытый файл — плашкой со щитом (значки — символы шрифта Nerd Font)
        vault_file = theme.role(QLabel(theme.GLYPHS["shield"] + "  " + self.vault.path.name), "chip")
        vault_file.setToolTip(theme.plain_tip(str(self.vault.path)))
        row.addWidget(vault_file, 0, Qt.AlignVCenter)
        row.addStretch()
        # новая версия: кнопка появляется сама, без отдельного окна (gui/updater.py)
        self.update_button = theme.kind(QPushButton(), "primary")
        self.update_button.clicked.connect(self._update_clicked)
        self.update_button.hide()
        row.addWidget(self.update_button)
        glyph = theme.GLYPHS
        for text, tip, handler in [(glyph["magic"] + "  " + tr("Generator"), "", self.open_generator),
                                   (glyph["puzzle"] + "  " + tr("Extension"), "", self.extension),
                                   (glyph["cog"] + "  " + tr("Settings"), shortcut_text("Ctrl+,"), self.open_settings),
                                   (glyph["lock"], tr("Lock WhoKey") + " " + shortcut_text("Ctrl+L"), self.lock_requested.emit)]:
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
        self.search_action = self.search.addAction(theme.glyph_icon("search", theme.FAINT, 13), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(lambda: self.refresh())
        row.addWidget(self.search, 1)
        add = theme.kind(QPushButton("+ " + tr("Add")), "primary")
        add.clicked.connect(lambda: self.add())  # без lambda clicked передал бы False вместо адреса
        row.addWidget(add)
        return row

    def _table_card(self):
        """Таблица в «карточке» с неоновым ореолом; если записей нет — подсказка вместо неё."""
        self.table = QTableWidget(0, len(COLUMNS))
        # Tab — к следующему элементу окна, а не по ячейкам (иначе из таблицы не выйти)
        self.table.setTabKeyNavigation(False)
        self.table.itemSelectionChanged.connect(self._remember_choice)
        self.table.setHorizontalHeaderLabels(
            [tr("Name"), tr("Login"), tr("Password"), tr("Note"), tr("Updated")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)  # правка — только в окне записи
        self.table.setShowGrid(False)
        self.table.setItemDelegate(RoundedRowDelegate(self.table))  # выделение — скруглённой плашкой
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setIconSize(QSize(24, 24))  # буква-кружок у названия
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        # восемь одинаковых точек не нуждаются в широкой колонке — место названию и логину
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, 120)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # по умолчанию — по сайту от А до Я (Qt сам начал бы с обратного порядка)
        self.table.horizontalHeader().setSortIndicator(0, Qt.AscendingOrder)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self.edit)
        # правый клик — меню действий с записью
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)

        self.empty = self._empty_state()
        self.nothing_found = self._nothing_found_state()

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

    def _centered(self, widgets):
        """Блок по центру карточки: виджеты один под другим."""
        page = QWidget()
        column = QVBoxLayout(page)
        column.addStretch()
        for widget in widgets:
            if isinstance(widget, QHBoxLayout):
                column.addLayout(widget)
            else:
                if isinstance(widget, QLabel):
                    widget.setAlignment(Qt.AlignCenter)
                column.addWidget(widget, 0, Qt.AlignHCenter)
        column.addStretch()
        column.setSpacing(10)
        return page

    def _empty_state(self):
        """Пустое хранилище — первое, что видит новый человек: что здесь будет и с чего начать."""
        logo = QLabel()
        logo.setPixmap(theme.logo_pixmap(96))
        self.big_logo = logo
        heading = theme.role(QLabel(tr("Your passwords will live here")), "heading")
        about = theme.role(QLabel(tr("Everything is stored encrypted on this computer.\nAdd your first entry or move your passwords from a browser.")), "muted")
        first = theme.kind(QPushButton(theme.GLYPHS["plus"] + "  " + tr("Add first entry")), "primary")
        first.clicked.connect(lambda: self.add())
        import_button = QPushButton(theme.GLYPHS["import"] + "  " + tr("Import from CSV…"))
        import_button.clicked.connect(lambda: self.import_csv())
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(first)
        buttons.addWidget(import_button)
        buttons.addStretch()
        extension = theme.role(QLabel(self._extension_link()), "accent")
        self.extension_link = extension
        extension.setTextFormat(Qt.RichText)  # ссылка — HTML (role() делает надписи простым текстом)
        extension.linkActivated.connect(lambda _: self.extension())
        return self._centered([logo, heading, about, buttons, extension])

    def _extension_link(self):
        return (f'{theme.GLYPHS["puzzle"]}  <a href="#" style="color: {theme.ACC}; text-decoration: none;">'
                + tr("Passwords can be filled right on websites — connect the extension") + "</a>")

    def _nothing_found_state(self):
        icon = QLabel()
        icon.setPixmap(theme.glyph_pixmap("search", theme.FAINT, 44, 56))
        self.nothing_icon = icon
        self.nothing_text = theme.role(QLabel(), "heading")
        hint = theme.role(QLabel(tr("Search looks in the name, login, note and website address.")), "muted")
        clear = QPushButton(tr("Clear search"))
        clear.clicked.connect(lambda: (self.search.clear(), self.search.setFocus()))
        return self._centered([icon, self.nothing_text, hint, clear])

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

    # --- пасхалка «😺 котик» (gui/cat.py): три нажатия на ключ — мурлыканье, открывается кошачий зрачок,
    #     чёрный кот вместо ключа и кошачья палитра; одно нажатие на кота — обратно ---

    locking = False  # окно уже закрывается из-за блокировки (см. Controller.lock)
    lock_state = None  # общие данные окон: сообщение для окна входа
    _logo_clicks = 0
    _wave = None

    def _logo_clicked(self):
        if self._wave is not None:
            return  # волна ещё идёт
        now = time.monotonic()
        self._logo_clicks = self._logo_clicks + 1 if now - self._last_logo_click < EGG_CLICK_GAP else 1
        self._last_logo_click = now
        if theme.egg or self._logo_clicks >= 3:
            self._logo_clicks = 0
            if not theme.egg:
                play_purr()  # только на третье нажатие; обратно — тихо
            self._toggle_egg()

    _last_logo_click = 0.0

    def _toggle_egg(self):
        before = self.grab()  # снимок старых цветов: зрачок открывает новые из середины
        theme.set_egg(not theme.egg)
        self._recolor()
        self._wave = cat.Reveal(self, before)
        self._wave.done.connect(self._wave_finished)

    def _end_wave(self):
        """Переход рисует снимок окна: пароль спрятали — на снимке его тоже быть не должно."""
        if self._wave is not None:
            self._wave.animation.setCurrentTime(self._wave.DURATION)

    def _wave_finished(self):
        self._wave = None

    def _recolor(self):
        """То, что нарисовано заранее и само не перекрасится."""
        self.logo.setPixmap(theme.logo_pixmap(36))
        self.big_logo.setPixmap(theme.logo_pixmap(96))
        cat.decorate(self)  # кот выглядывает снизу — или прячется
        self.search_action.setIcon(theme.glyph_icon("search", theme.FAINT, 13))
        self.nothing_icon.setPixmap(theme.glyph_pixmap("search", theme.FAINT, 44, 56))
        self.extension_link.setText(self._extension_link())
        self.refresh(select=self.selected_index())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if theme.egg:
            cat.decorate(self)  # кот остаётся у нижнего края

    _monograms = {}  # буква -> значок: рисуем каждую букву один раз

    def _monogram(self, name):
        letter = (name.strip() or "?")[0].upper()
        key = (letter, theme.egg, theme.LIGHT)  # у пасхалки и светлой темы свои цвета
        if key not in self._monograms:
            MainWindow._monograms[key] = QIcon(theme.monogram(letter, 24))
        return self._monograms[key]

    _chosen = None  # последняя выбранная запись — чтобы выделение пережило поиск без результатов

    def _remember_choice(self):
        index = self.selected_index()
        if index is not None:
            self._chosen = index

    def refresh(self, select=None):
        """Перерисовывает таблицу. select — номер записи, которую выделить."""
        if select is None:
            select = self.selected_index()
        if select is None:
            select = self._chosen
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
                if field == "site":
                    item.setIcon(self._monogram(text))
                if field != "password":
                    item.setToolTip(theme.plain_tip(text) if field != "updated" else full_date(text))  # обрезанное — целиком
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
            self.nothing_text.setText(tr("Nothing found for «{query}»").format(query=query))
            self.stack.setCurrentWidget(self.nothing_found)
        else:
            self.stack.setCurrentWidget(self.table)
        # число — отдельной переменной, а не len() внутри: иначе lupdate не поймёт,
        # что у надписи есть формы «1 запись / 2 записи / 5 записей»
        count = len(self.vault.entries)
        self.entries_count.setText(self.tr("%n entries", "", count))
        self._end_wave()  # пароль могли спрятать или поменять, а на снимке волны он ещё виден

    def _save(self, change):
        """Выполняет изменение хранилища и сообщает об ошибках записи. True — получилось."""
        try:
            change()
        except SaveError as error:
            # диск полон, нет прав на запись — изменение не применено
            show_error(self, tr("⚠ Could not save: {error}. The change was not applied, the file on disk is untouched.").format(error=save_problem(error)))
            return False
        if self.vault.backup_error:
            self.statusBar().showMessage(tr("⚠ The change is saved, but the backup was not updated: {error}.").format(error=self.vault.backup_error), 10000)
            self.vault.backup_error = None
        return True

    # --- действия ---

    def add(self, url="", login="", password=""):
        """Новая запись; url, login, password — если запись добавляют из расширения браузера
        (после «Сгенерировать пароль» на странице регистрации)."""
        entry = {"site": url, "login": login, "password": password, "note": "", "url": url} if url else None
        dialog = EntryDialog(self, entry, copy_password=self.copy_password)
        # не сохранилось — окно открывается снова: введённое (и пароль, уже вписанный на сайте) не теряется
        while dialog.exec():
            if self._save(lambda: self.vault.add(**dialog.values())):
                self.search.clear()
                self.refresh(select=len(self.vault.entries) - 1)
                return
            if self.locking:
                break
        if self.locking and password:
            self._keep_generated(dialog, url)

    def _keep_generated(self, dialog, url):
        """Блокировка закрыла новую запись из расширения. Пароль уже вписан на сайте: потерять его
        нельзя, а спрашивать на заблокированном экране некого — сохраняем то, что в окне (ревью 1.6.3)."""
        values = dialog.values()
        site = values["site"] = values["site"] or url
        try:
            self.vault.add(**values)
            text = tr("The password generated on {site} was saved to WhoKey.").format(site=site)
        except SaveError as error:
            text = tr("⚠ The password generated on {site} was not saved: {error}. It is only on the website now.").format(site=site, error=save_problem(error))
        self.lock_state["notice"] = (self.lock_state.get("notice", "") + "\n" + text).strip()

    def edit(self):
        index = self.selected_index()
        if index is None:
            return
        entry = self.vault.entries[index]
        dialog = EntryDialog(self, entry, copy_password=self.copy_password)
        while dialog.exec():
            changes = {k: v for k, v in dialog.values().items() if v != entry.get(k, "")}  # у старых записей нет url
            if not changes:
                return
            if self._save(lambda: self.vault.update(index, **changes)):
                self.refresh(select=index)
                return
            if self.locking:
                return

    def delete(self):
        index = self.selected_index()
        if index is None:
            return
        entry = self.vault.entries[index]
        # без логина — без пустых скобок «()»
        question = (tr("Delete \"{site}\" ({login})?\nThis cannot be undone.").format(site=entry["site"], login=entry["login"]) if entry["login"]
                    else tr("Delete \"{site}\"?\nThis cannot be undone.").format(site=entry["site"]))
        if not ask_yes(self, tr("Delete entry"), question, danger=tr("Delete")):
            return
        if self._save(lambda: self.vault.delete(index)):
            # номера записей после удалённой сдвинулись — показанный пароль прячем
            self.revealed = None
            self._chosen = None
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
        self.hint.hide()  # на месте подсказки — таймер буфера
        self.countdown.start(prefs.clear_after())
        return True

    def import_csv(self):
        """Пароли из CSV-файла браузера или другого менеджера паролей."""
        chosen = choose_csv(self)
        if chosen is None:
            return
        found = chosen[1]
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

    def save_copy(self):
        """Копия хранилища как есть — зашифрованная тем же мастер-паролем. В отличие от CSV,
        её можно хранить где угодно (флешка, облако): без мастер-пароля она бесполезна."""
        default = Path.home() / "Documents" / f"WhoKey {QDate.currentDate().toString('yyyy-MM-dd')}.dat"
        name, _ = QFileDialog.getSaveFileName(self, tr("Save encrypted copy"), str(default),
                                              tr("Password vault (*.dat)"))
        if not name:
            return
        target = Path(name)
        if target.resolve() == self.vault.path.resolve():
            show_error(self, tr("This is the vault file itself — choose another place for the copy."))
            return
        try:
            shutil.copyfile(self.vault.path, target)
            os.chmod(target, 0o600)  # как само хранилище: только владельцу
        except OSError as error:
            show_error(self, tr("Could not write the file: {error}").format(error=error.strerror or error))
            return
        show_info(self, tr("Save encrypted copy"),
                  tr("The copy is saved: {name}\n\nIt is encrypted with the same master password. To open it, choose it with the \"Other file…\" button in the WhoKey window.").format(name=target.name))

    # --- обновление по кнопке ---

    def offer_update(self, version):
        """Найдена новая версия: кнопка «Обновить до …» вверху окна."""
        self._update_version = version
        self.update_button.setText("↓  " + tr("Update to {version}").format(version=version))
        self.update_button.setToolTip(theme.plain_tip(tr("Download WhoKey {version}, check its signature and restart. The vault is locked; your passwords stay where they are.").format(version=version)))
        self.update_button.setEnabled(True)
        self.update_button.show()

    def _update_clicked(self):
        self.update_button.setEnabled(False)
        self.update_button.setText("↓  " + tr("Downloading…"))
        self.update_requested.emit()

    def update_progress(self, percent):
        self.update_button.setText("↓  " + tr("Downloading… {percent}%").format(percent=percent))

    def offer_restart(self, version):
        """Новая версия скачана и проверена, но сейчас открыто окно — ставим, когда человек нажмёт."""
        self._update_version = version
        self.update_button.setText("↻  " + tr("Restart to update"))
        self.update_button.setToolTip(theme.plain_tip(tr("WhoKey {version} is downloaded and checked. Press to restart into it.").format(version=version)))
        self.update_button.setEnabled(True)
        self.update_button.show()

    def update_installing(self):
        self.update_button.setText(tr("Installing…"))

    def update_failed(self, message):
        """Не скачалось или не прошло проверку: кнопка снова доступна, причина — в строке состояния."""
        self.offer_update(self._update_version)
        self.statusBar().showMessage("⚠ " + message, 15000)

    _update_version = ""

    def about(self):
        AboutDialog(self, self.updater).exec()

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
        if self.findChild(SettingsDialog):
            return  # уже открыты (⌘, нажали второй раз)
        dialog = SettingsDialog(self, self.vault, self.change_master)
        dialog.language_chosen.connect(self.language_changed)
        # open(), а не exec(): окно поверх главного, но не останавливает программу —
        # так его можно открыть заново сразу после смены языка (app.change_language)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.open()

    def change_master(self):
        if not ChangeMasterDialog(self, self.vault).exec():
            return
        self.statusBar().showMessage(tr("Master password changed, vault re-encrypted."), 10000)
        if self.vault.backup_error:
            # копия со старым паролем при этом удалена — человек должен знать,
            # что резервной копии сейчас нет
            show_error(self, tr("⚠ The change is saved, but the backup was not updated: {error}.").format(error=self.vault.backup_error))
            self.vault.backup_error = None
