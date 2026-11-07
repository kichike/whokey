"""Менеджер паролей — приложение с окнами (PySide6 / Qt).

То же шифрование, что у консольной версии (manager.py): vault.py, generator.py.
Буфер обмена — через Qt (gui/secure_clipboard.py). Окна — в папке gui/.

Хранилище по умолчанию лежит там, где программы Mac держат свои данные:
~/Library/Application Support/EduPasswords/vault.dat (на Windows — в %APPDATA%).
Эта папка не синхронизируется с iCloud. Другой файл можно выбрать в окне входа.

Запуск: ../.venv/bin/python app.py
"""

import hashlib
import os
import signal
import socket
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # чтобы найти vault.py и остальные модули рядом



def restore_library_path():
    """Linux: собранный WhoKey указывает системе на свои библиотеки (LD_LIBRARY_PATH).
    Запущенные из него программы — браузер, проигрыватель звука — должны видеть
    системные, иначе не откроются. Самому WhoKey это уже не мешает: свои он нашёл при старте."""
    if not (getattr(sys, "frozen", False) and sys.platform.startswith("linux")):
        return
    original = os.environ.pop("LD_LIBRARY_PATH_ORIG", None)
    if original is None:
        os.environ.pop("LD_LIBRARY_PATH", None)
    else:
        os.environ["LD_LIBRARY_PATH"] = original


restore_library_path()


def no_core_dumps():
    """При падении система может сохранить снимок памяти программы на диск, а в нём —
    мастер-пароль и пароли. Запрещаем такие снимки для WhoKey (macOS, Linux)."""
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ImportError, ValueError, OSError):
        pass  # на Windows этого механизма нет


no_core_dumps()  # сразу: и окнам, и мосту для расширения (через него тоже идут пароли)

# Браузер запускает этот же файл как мост для расширения, передавая адрес
# расширения (chrome-extension://…/). Тогда никаких окон — сразу работа моста.
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1].startswith("chrome-extension://"):
    import bridge_host
    bridge_host.main()
    sys.exit(0)

from PySide6.QtCore import QLocale, QSettings, QStandardPaths, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox

import bridge_protocol
from vault import SaveError, app_data_dir
from gui.secure_clipboard import SecureClipboard
from gui import theme
from gui.autolock import AutoLock
from gui.bridge import BridgeServer
from gui.i18n import LANGUAGES, set_language, tr
from gui.widgets import show_error
from gui.login import LoginWindow
from gui.main_window import MainWindow
from gui import i18n, prefs

APP_NAME = "EduPasswords"


def default_vault_path():
    folder = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    return folder / "vault.dat"


class Controller:
    """Переключает окна: вход -> главное окно."""

    def __init__(self):
        # настройки (язык, последний файл) — не секрет, пароли сюда не попадают
        self.settings = QSettings(APP_NAME, APP_NAME)
        self.clipboard = SecureClipboard()  # буфер обмена через Qt (у консольной версии — clipboard.py)
        self.state = {}
        self.window = None
        self.bridge = None  # сервер для расширения браузера — пока открыто хранилище
        # экран заблокировали или Mac уснул — закрыть хранилище (расширение перестанет получать пароли)
        self.autolock = AutoLock()
        self.autolock.lock.connect(self.lock)
        if getattr(sys, "frozen", False):
            # собранное приложение: прописать мост в браузерах (путь к себе мог поменяться)
            bridge_protocol.install_native_host(Path(sys.executable).resolve())

        # язык — только из известных: с неизвестным (кто-то поправил настройки
        # вручную) окно входа падало бы при каждом запуске
        system_lang = "ru" if QLocale.system().name().startswith("ru") else "en"
        lang = self.settings.value("language", system_lang)
        set_language(lang if lang in dict(LANGUAGES) else system_lang)

        path = default_vault_path()
        saved = self.settings.value("vault_path")
        if saved and Path(saved).parent.is_dir():
            path = Path(saved)
        elif saved and Path(saved) != path:
            # папка прошлого хранилища недоступна (например, не подключена флешка).
            # Не предлагаем создать новое на её месте — открываем хранилище
            # по умолчанию и прямо говорим, что случилось.
            self.state["notice"] = tr("The folder of the last vault is unavailable: {folder}\nMaybe a drive is not connected. The default vault is shown; to go back, connect the drive and click \"Other file…\".").format(folder=Path(saved).parent)
        self.show_login(path)

    def _replace_window(self, window):
        # сначала показываем новое окно, потом закрываем старое — иначе
        # на мгновение не останется окон и программа решит, что пора выйти
        old, self.window = self.window, window
        window.show()
        if old is not None:
            old.close()
            old.deleteLater()

    def _egg_off(self):
        """Пасхалка не должна мешать блокировке, что бы с ней ни случилось."""
        try:
            theme.set_egg(False)
        except Exception:
            traceback.print_exc()

    def show_login(self, path):
        self._egg_off()
        window = LoginWindow(path, self.state)
        window.restart.connect(self.show_login)
        window.opened.connect(self.show_main)
        self._replace_window(window)

    def show_main(self, vault):
        if isinstance(self.window, MainWindow):
            return  # хранилище уже открыто (например, отпечаток и пароль пришли почти одновременно)
        self.stop_bridge()
        if vault.header_repaired:
            # открытая часть файла не совпала с копией внутри шифровки (испорчена или
            # подменена) — сразу записываем правильную, чтобы мастер-пароль подходил
            try:
                vault.save()
            except SaveError:
                pass  # не вышло сейчас — исправится при следующем сохранении
        self.settings.setValue("vault_path", str(vault.path))
        rolled_back = self._remember_generation(vault)
        window = self._new_main(vault)
        self.bridge = BridgeServer(vault, window, self.settings)
        self.bridge.start()
        self.autolock.start()
        if rolled_back is not None:
            show_error(window, tr("This vault file is older than the one this computer saw last time (save {now} instead of {seen}). It may have been replaced with an old copy: entries changed since then and the browser extension access you turned off could be back.\n\nIf you did not restore an old copy yourself, check your entries and disconnect the extension (Extension button).").format(now=vault.generation, seen=rolled_back))

    def _remember_generation(self, vault):
        """Номер сохранения хранилища — в настройках (он не секретный). Если файл «моложе»
        того, что этот компьютер уже видел, его подменили старой копией: вернулись бы
        отозванный доступ расширения и старые записи. Возвращает прежний номер или None."""
        key = "generation/" + hashlib.sha256(str(vault.path.resolve()).encode("utf-8")).hexdigest()
        seen = 0 if vault.fresh else int(self.settings.value(key, 0) or 0)
        vault.on_saved = lambda number: self.settings.setValue(key, number)
        self.settings.setValue(key, vault.generation)
        return seen if vault.generation < seen else None

    def _new_main(self, vault):
        self._egg_off()
        window = MainWindow(vault, self.clipboard)
        window.language_changed.connect(lambda code: self.change_language(vault, code))
        window.lock_requested.connect(lambda: self.lock("manual"))
        self._replace_window(window)
        return window

    def change_language(self, vault, code):
        """Язык из настроек: главное окно пересоздаётся с новыми надписями, хранилище остаётся открытым."""
        set_language(code)
        self.settings.setValue("language", i18n.LANG)
        window = self._new_main(vault)
        if self.bridge is not None:
            self.bridge.window = window  # окошки расширения — поверх нового окна
        # язык меняли в «Настройках» — они открываются снова, уже на новом языке,
        # а не закрываются посреди работы
        QTimer.singleShot(0, window.open_settings)

    def stop_bridge(self):
        if self.bridge is not None:
            self.bridge.stop()
            self.bridge = None

    def lock(self, reason="system"):
        """Блокировка: закрыть хранилище и вернуть окно входа.
        reason — "system" (экран, сон), "idle" (бездействие) или "manual" (кнопка, ⌘L)."""
        if not isinstance(self.window, MainWindow):
            return
        self.autolock.stop()
        self.stop_bridge()
        # открытые окошки (запись, генератор…) закрываем — они держат данные хранилища
        self.window.locking = True  # окно записи не откроется снова после ошибки сохранения
        self.window.lock_state = self.state
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible():
                # не reject(): окно записи с правками спросило бы «Закрыть без сохранения?»,
                # и блокировка ждала бы ответа, пока на экране открыты записи (ревью 1.6.3)
                widget.done(QDialog.Rejected)
            elif isinstance(widget, QMenu) and widget.isVisible():
                widget.close()  # меню правого клика: иначе «Копировать пароль» сработал бы после блокировки
        self.clipboard.clear_now()
        if reason == "manual":
            self.state["notice"] = tr("WhoKey is locked. Enter your master password.")
        elif reason == "idle":
            self.state["notice"] = tr("WhoKey locked after {n} min without use. Enter your master password.").format(n=prefs.idle_lock_minutes())
        else:
            self.state["notice"] = tr("WhoKey locked: the screen was locked or the computer slept. Enter your master password.")
        path = self.window.vault.path
        # окно меняем, когда закроются окошки (их циклы событий ещё работают)
        QTimer.singleShot(0, lambda: self.show_login(path))


INSTANCE_NAME = "whokey-instance-" + bridge_protocol.user_tag()


def hand_over_to_running():
    """WhoKey уже открыт — показать его окно вместо второй копии. True — выходим."""
    if sys.platform == "win32":
        return _hand_over_windows()
    if sys.platform.startswith("linux"):
        return _hand_over_linux()
    return False  # на Mac вторую копию не даёт открыть сама система


def _hand_over_linux():
    """Кто уже работает, узнаём по замку на файл: его снимает сама система, даже если
    первая копия упала. Показывать окно просим только настоящий WhoKey."""
    import fcntl
    try:
        folder = app_data_dir()
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(folder / "instance.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    except OSError:
        return False  # замок не создать — лучше запуститься, чем молча не открыться
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        os.close(fd)
        if not isinstance(error, BlockingIOError):
            return False  # замок на этом диске не работает — это ещё не значит, что копия открыта
        sock = QLocalSocket()
        sock.connectToServer(bridge_protocol.instance_address())
        if sock.waitForConnected(1000):
            try:
                with socket.socket(fileno=os.dup(int(sock.socketDescriptor()))) as peer:
                    if bridge_protocol.trusted_peer(peer):
                        sock.write(b"show\n")
                        sock.waitForBytesWritten(500)
            except OSError:
                pass
            sock.disconnectFromServer()
        return True
    _hand_over_linux.lock = fd  # держим, пока программа работает
    return False


def _hand_over_windows():
    """Windows: WhoKey уже открыт — показать его окно вместо второй копии. True — выходим.

    На Mac вторую копию не даёт открыть сама система; на Windows её запустил бы,
    например, мост расширения, пока окно входа уже открыто.
    Кто уже работает, узнаём по мьютексу в пространстве имён своего сеанса
    (Local\\…): другой пользователь занять его не может — значит, и не помешает
    WhoKey запуститься (канал с тем же именем он занять мог бы).
    """
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, False, "Local\\WhoKey-" + bridge_protocol.user_tag())
    if not handle:
        return False  # мьютекс не создать — лучше запуститься, чем молча не открыться
    if ctypes.get_last_error() != 183:  # не ERROR_ALREADY_EXISTS — значит, мы первые
        hand_over_to_running.mutex = handle  # держим, пока программа работает
        return False
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_NAME)
    if sock.waitForConnected(1000):
        # выводить вперёд разрешаем только настоящему WhoKey этого же пользователя
        pid = ctypes.c_ulong()
        handle = ctypes.c_void_p(int(sock.socketDescriptor()))
        if (kernel32.GetNamedPipeServerProcessId(handle, ctypes.byref(pid))
                and bridge_protocol.windows_program_of(pid.value) == bridge_protocol.own_program()
                and bridge_protocol.pipe_owner_sid(handle.value) == bridge_protocol.current_sid()):
            ctypes.windll.user32.AllowSetForegroundWindow(pid.value)
            sock.write(b"show\n")
            sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
    return True


def listen_for_second_copy(controller):
    """Windows и Linux: вторая копия просит показать окно — выводим его вперёд."""
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)  # только этот пользователь
    if sys.platform == "win32":
        address = INSTANCE_NAME
    else:
        address = bridge_protocol.instance_address()
        QLocalServer.removeServer(address)  # от упавшей копии: замок наш, значит, других нет
    if not server.listen(address):
        return server

    def show():
        while server.hasPendingConnections():
            server.nextPendingConnection().deleteLater()
        window = controller.window
        if window is not None:
            window.showNormal()
            window.raise_()
            window.activateWindow()
    server.newConnection.connect(show)
    return server


def main():
    app = QApplication(sys.argv)
    if hand_over_to_running():
        return
    # APP_NAME — имя папки с данными, его не меняем (иначе «потеряется» уже
    # созданное хранилище); видимое название программы — WhoKey
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName("WhoKey")
    app.setWindowIcon(QIcon(str(theme.ICON_FILE)))  # иконка в Dock при запуске без .app
    app.setDesktopFileName("whokey")  # Wayland: по этому имени система находит значок и название
    theme.apply(app)

    # обработчик ошибок ставим ДО создания окон — иначе ошибка при запуске
    # закрыла бы приложение молча, без всякого окна
    def on_error(kind, error, trace):
        # непредвиденная ошибка — понятное окошко вместо молчаливого падения;
        # подробности для разработчика — в Терминал
        traceback.print_exception(kind, error, trace)
        QMessageBox.critical(None, tr("Error"),
                             tr("⚠ Unexpected error: {error}.\nThe vault file is intact: changes are written via a temporary file.").format(error=f"{kind.__name__}: {error}"))
    sys.excepthook = on_error

    controller = Controller()
    if sys.platform == "win32" or sys.platform.startswith("linux"):
        controller.instance_server = listen_for_second_copy(controller)  # держим, пока программа работает

    # что бы ни случилось — при выходе не оставляем пароль в буфере обмена
    app.aboutToQuit.connect(controller.clipboard.clear_now)
    app.aboutToQuit.connect(controller.stop_bridge)

    # kill, закрытие Терминала, Ctrl+\ — тоже нормальный выход с очисткой буфера.
    # Qt почти всё время занят своим циклом, и Python замечает сигнал, только
    # когда сам выполняет код, — поэтому таймер «будит» его 3 раза в секунду.
    for name in ("SIGTERM", "SIGHUP", "SIGQUIT", "SIGINT"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: app.quit())
    wake = QTimer()
    wake.timeout.connect(lambda: None)
    wake.start(300)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
