"""Быстрая проверка WhoKey на любой системе — прежде всего на Windows в GitHub Actions,
где нет человека, который бы посмотрел глазами.

    python tests/smoke_test.py [папка-для-снимков]

Проверяет хранилище (создание, вход, замок, скрытая копия, переезд старых файлов),
буфер обмена (копирование, пометки «не сохранять в журнал», очистка) и окна
(путь «вход → главное окно → поиск → правый клик → окна записи»). Снимки окон
сохраняются в папку — их выкладывает GitHub Actions, чтобы посмотреть, как
приложение выглядит на Windows. Код выхода 1 — если хоть одна проверка не прошла.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # окна рисуются в памяти, без экрана
sys.stdout.reconfigure(encoding="utf-8")  # консоль Windows по умолчанию cp1252 — русские буквы не печатаются

import vault as V  # noqa: E402

SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
APP = Path(tempfile.mkdtemp())
V.app_data_dir = lambda: APP  # замки — во временной папке, а не в настоящей папке программы
PW = "Зелёный-Кит-Летит-2026!"
results = []


def check(ok, message):
    results.append(bool(ok))
    print(("OK   " if ok else "FAIL ") + message, flush=True)


def hidden(path):
    if sys.platform == "win32":
        import ctypes
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        return attrs != -1 and bool(attrs & 0x2)
    return path.name.startswith(".")


# --- хранилище ---
folder = Path(tempfile.mkdtemp())
path = folder / "vault.dat"
fd = V.lock(path)
vault = V.Vault.create(path, PW)
vault.add("github.com", "egor", "Kj8#mP2$vL9!qR4w", "работа")
vault.add("госуслуги", "", "пароль-с-русскими-буквами", "")  # сохранение второй раз — копия уже скрытая
check(sorted(os.listdir(folder)) == [".vault.dat.bak", "vault.dat"], f"в папке хранилище и копия: {sorted(os.listdir(folder))}")
check(hidden(V.backup_path(path)), "резервная копия скрыта")
check(len(V.Vault.open(path, PW).entries) == 2, "хранилище открывается, записи на месте")
check(len(V.Vault.open(V.backup_path(path), PW).entries) == 2, "копия перезаписалась, хотя была скрытой")
try:
    V.Vault.open(path, "не тот пароль")
    check(False, "неверный пароль не принят")
except V.WrongPassword:
    check(True, "неверный пароль не принят")
try:
    V.lock(path)
    check(False, "второе окно на то же хранилище — «уже открыто»")
except V.VaultLocked:
    check(True, "второе окно на то же хранилище — «уже открыто»")
try:
    V.lock(folder / "VAULT.DAT")
    check(False, "тот же файл ЗАГЛАВНЫМИ — тот же замок")
except V.VaultLocked:
    check(True, "тот же файл ЗАГЛАВНЫМИ — тот же замок")
os.close(fd)

old = Path(tempfile.mkdtemp())
shutil.copy(path, old / "vault.dat")
shutil.copy(V.backup_path(path), old / "vault.dat.bak")
(old / "vault.dat.lock").touch()
V.tidy_old_files(old / "vault.dat")
check(sorted(os.listdir(old)) == [".vault.dat.bak", "vault.dat"], f"старые файлы переехали: {sorted(os.listdir(old))}")
check(hidden(old / ".vault.dat.bak"), "переехавшая копия скрыта")

# --- буфер обмена ---
if sys.platform in ("win32", "darwin"):
    import clipboard as C
    secret = "Пароль-Ж ü #42"
    board = C.Clipboard()
    check(board.copy(secret), "пароль скопирован")
    check(C._read() == secret, f"в буфере ровно тот пароль (с русскими буквами): {C._read()!r}")
    if sys.platform == "win32":
        import ctypes
        user32 = ctypes.windll.user32
        user32.RegisterClipboardFormatW.restype = ctypes.c_uint
        for name in C._WIN_PRIVATE_FORMATS:
            fmt = user32.RegisterClipboardFormatW(name)
            check(user32.IsClipboardFormatAvailable(fmt), f"пометка {name}")
    check(board.clear_now(), "буфер очищен")
    check(C._read() == "", "в буфере пусто")

# --- окна ---
from PySide6.QtCore import QPoint, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton  # noqa: E402

app = QApplication([])
from gui import theme  # noqa: E402

theme.apply(app)
from PySide6.QtGui import QIcon  # noqa: E402

window_icon = QIcon(str(theme.ICON_FILE))
check(not window_icon.isNull() and window_icon.availableSizes(),
      f"иконка окна загружается ({theme.ICON_FILE.name}, размеров: {len(window_icon.availableSizes())})")
from gui.secure_clipboard import SecureClipboard  # noqa: E402

# буфер обмена приложения — через Qt (QClipboard) с пометками «секретное»
if sys.platform in ("win32", "darwin"):
    secret = "Пароль-Ж ü #42"
    qt_board = SecureClipboard()
    check(qt_board.copy(secret), "приложение: пароль скопирован через QClipboard")
    check(QApplication.clipboard().text() == secret, "приложение: в буфере ровно тот пароль")
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.RegisterClipboardFormatW.restype = wintypes.UINT
        user32.GetClipboardData.restype = wintypes.HANDLE
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        user32.OpenClipboard(None)
        try:
            for name, value in (("ExcludeClipboardContentFromMonitorProcessing", None),
                                ("CanIncludeInClipboardHistory", 0), ("CanUploadToCloudClipboard", 0)):
                fmt = user32.RegisterClipboardFormatW(name)
                present = bool(user32.IsClipboardFormatAvailable(fmt))
                if present and value is not None:
                    handle = user32.GetClipboardData(fmt)
                    pointer = kernel32.GlobalLock(handle)
                    present = ctypes.c_uint32.from_address(pointer).value == value
                    kernel32.GlobalUnlock(handle)
                check(present, f"приложение: пометка {name}" + ("" if value is None else f" = {value}"))
        finally:
            user32.CloseClipboard()
    check(qt_board.clear_now() and QApplication.clipboard().text() == "", "приложение: буфер очищен")
import gui.dialogs as Dg  # noqa: E402
import gui.login as L  # noqa: E402
import gui.main_window as MW  # noqa: E402

errors = []
sys.excepthook = lambda kind, error, trace: errors.append(repr(error))
L.lock = V.lock


class FakeClipboard:  # окна проверяем без настоящего буфера
    def copy(self, text):
        return True


def buttons_fit(window, name):
    """Ни одна кнопка не сжата уже, чем нужно для её текста (так обрезалось «Сгенерировать»)."""
    squeezed = [b.text() for b in window.findChildren(QPushButton)
                if b.isVisible() and b.width() < b.sizeHint().width()]
    check(not squeezed, f"{name}: кнопки не обрезаны {squeezed}")


def shot(widget, name):
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        widget.grab().save(str(SHOTS / f"{name}.png"))


def run():
    login = L.LoginWindow(path, {})
    login.show()
    login.master.edit.setFocus()
    QTest.keyClicks(login.master.edit, "abc")
    app.processEvents()
    shot(login, "login")
    buttons_fit(login, "окно входа")
    from texts import t
    file_label = [x for x in login.findChildren(QLabel) if x.text().startswith(t("g_vault_file"))][0]
    check("\u200b" in file_label.text(), "в пути к файлу есть точки переноса (длинный путь не обрежется)")
    login.close()
    login.deleteLater()

    main = MW.MainWindow(V.Vault.open(path, PW), FakeClipboard())
    main.resize(960, 600)
    main.show()
    QApplication.sendPostedEvents(None, 0)  # окно входа действительно удалено
    main.search.setFocus()
    QTest.keyClicks(main.search, "git")
    app.processEvents()
    check(main.table.rowCount() == 1, "поиск после окна входа работает, без вылета")
    main.search.clear()
    main.table.selectRow(0)
    main.copy()
    app.processEvents()
    check(main.countdown.isVisible(), "после копирования виден таймер буфера")
    shot(main, "main")
    buttons_fit(main, "главное окно")

    def grab_menu():
        menu = QApplication.activePopupWidget()
        if menu:
            shot(menu, "menu")
            menu.close()
    QTimer.singleShot(300, grab_menu)
    main._context_menu(QPoint(20, main.table.visualRect(main.table.model().index(0, 0)).center().y()))
    check(True, "правый клик — меню открылось и закрылось")

    for name, make in (("entry", lambda: Dg.EntryDialog(main, main.vault.entries[0])),
                       ("generator", lambda: Dg.GeneratorDialog(main, lambda text: True)),
                       ("change_master", lambda: Dg.ChangeMasterDialog(main, main.vault))):
        dialog = make()
        dialog.show()
        for edit in dialog.findChildren(QLineEdit)[:2]:
            edit.setFocus()
            QTest.keyClicks(edit, "x")
        app.processEvents()
        shot(dialog, name)
        buttons_fit(dialog, name)
        dialog.close()
        dialog.deleteLater()
        QApplication.sendPostedEvents(None, 0)
        QTest.keyClicks(main.search, "m")
        main.search.clear()
        app.processEvents()
    check(True, "окна записи, генератора и смены пароля открываются и закрываются")
    check(not errors, f"ни одной ошибки в окнах: {errors[:2]}")
    app.quit()


QTimer.singleShot(200, run)
app.exec()

print(f"\n{sum(results)} из {len(results)} проверок прошли")
sys.exit(0 if all(results) else 1)
