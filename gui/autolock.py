"""Автоблокировка: при блокировке экрана или сне компьютера WhoKey закрывает хранилище.

После этого расширение браузера ничего не получит, пока снова не введён
мастер-пароль. Во время обычной работы ничего не происходит.

Без сторонних библиотек: раз в несколько секунд спрашиваем систему.
  - экран заблокирован — CoreGraphics (встроен в macOS) возвращает словарь
    текущего сеанса, в нём есть ключ CGSSessionScreenIsLocked;
  - экран заблокирован (Windows) — WTSQuerySessionInformation сообщает
    состояние сеанса: «заблокирован» или нет;
  - компьютер спал — «монотонные» часы во сне стоят, а обычные идут: если разница
    между ними вдруг выросла, значит, был сон. На Windows для этого нужны особые
    часы (QueryUnbiasedInterruptTime): обычные «монотонные» часы Python там во
    сне продолжают идти, и сон был бы незаметен.
"""

import ctypes
import ctypes.util
import os
import struct
import sys
import time

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QTimer, Signal

from gui import prefs

CHECK_EVERY_MS = 3000
SLEEP_GAP = 20  # секунд «пропало» из монотонного времени — считаем, что компьютер спал


def session_info_locked(raw):
    """Разбор начала WTSINFOEXW (20 байт): True — сеанс Windows заблокирован.

    Level (4 байта), 4 байта выравнивания (внутри есть 8-байтные поля), затем
    SessionId, SessionState, SessionFlags. Смещение флагов — 16, не 12: иначе
    прочли бы SessionState («активен» = 0) и блокировались бы каждые 3 секунды.
    """
    level, _session, _state, flags = struct.unpack_from("<I4xIii", raw)
    return level == 1 and flags == 0  # WTS_SESSIONSTATE_LOCK


def _windows_screen_locked():
    """Заблокирован ли сеанс Windows (экран блокировки). Ошибка — False."""
    if sys.getwindowsversion()[:2] < (6, 2):
        return False  # в Windows 7 значение флага перевёрнуто — там полагаемся только на сон
    try:
        wts = ctypes.WinDLL("wtsapi32")
        wts.WTSQuerySessionInformationW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int,
                                                    ctypes.POINTER(ctypes.c_void_p),
                                                    ctypes.POINTER(ctypes.c_uint32)]
        wts.WTSFreeMemory.argtypes = [ctypes.c_void_p]
        buffer, size = ctypes.c_void_p(), ctypes.c_uint32()
        # текущий сеанс (-1 = WTS_CURRENT_SESSION), сведения WTSSessionInfoEx (25)
        if not wts.WTSQuerySessionInformationW(None, 0xFFFFFFFF, 25, ctypes.byref(buffer), ctypes.byref(size)):
            return False
        try:
            if size.value < 20:
                return False
            return session_info_locked(ctypes.string_at(buffer, 20))
        finally:
            wts.WTSFreeMemory(buffer)
    except (OSError, AttributeError, struct.error):
        return False


def monotonic():
    """Часы, которые стоят, пока компьютер спит (по ним видно, что был сон)."""
    if sys.platform == "win32":
        try:
            value = ctypes.c_uint64()
            if ctypes.windll.kernel32.QueryUnbiasedInterruptTime(ctypes.byref(value)):
                return value.value / 10_000_000  # в сотнях наносекунд → секунды
        except (OSError, AttributeError):
            pass
    return time.monotonic()  # на Mac монотонные часы во сне и так стоят


# Программы блокировки экрана на Linux. У окружений без общего сервиса блокировки
# (Hyprland, Sway, i3) другого признака нет. Ошибочное совпадение безопасно: хранилище просто закроется.
_LINUX_LOCKERS = {"hyprlock", "swaylock", "gtklock", "waylock", "i3lock", "xsecurelock", "slock", "physlock"}

# Кто ещё может знать о блокировке: (сервис, объект, интерфейс)
_SCREENSAVERS = (
    ("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver", "org.freedesktop.ScreenSaver"),  # KDE, Xfce
    ("org.freedesktop.ScreenSaver", "/ScreenSaver", "org.freedesktop.ScreenSaver"),
    ("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver"),
    ("org.cinnamon.ScreenSaver", "/org/cinnamon/ScreenSaver", "org.cinnamon.ScreenSaver"),
    ("org.mate.ScreenSaver", "/org/mate/ScreenSaver", "org.mate.ScreenSaver"),
)
_DBUS_TIMEOUT_MS = 200  # таймер блокировки работает в потоке окон — надолго его не держим


def _locker_running():
    """Запущена ли у этого пользователя программа блокировки экрана."""
    uid = os.getuid()
    try:
        processes = [name for name in os.listdir("/proc") if name.isdigit()]
    except OSError:
        return False
    for pid in processes:
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            with open(f"/proc/{pid}/comm", encoding="utf-8", errors="replace") as f:
                if f.read().strip() in _LINUX_LOCKERS:
                    return True
        except OSError:
            continue  # процесс уже завершился
    return False


def _dbus_answer(bus, service, path, interface, method, *args):
    """Ответ сервиса D-Bus или None, если сервиса нет. Сам сервис не запускаем."""
    from PySide6.QtDBus import QDBus, QDBusMessage, QDBusVariant
    message = QDBusMessage.createMethodCall(service, path, interface, method)
    message.setArguments(list(args))
    message.setAutoStartService(False)
    reply = bus.call(message, QDBus.Block, _DBUS_TIMEOUT_MS)
    if reply.type() != QDBusMessage.ReplyMessage or not reply.arguments():
        return None
    answer = reply.arguments()[0]
    # свойство приходит завёрнутым в «вариант»: без этого «is True» никогда не сработает
    return answer.variant() if isinstance(answer, QDBusVariant) else answer


def _linux_screen_locked():
    if _locker_running():
        return True
    try:
        from PySide6.QtDBus import QDBusConnection
    except ImportError:
        return False
    # systemd-logind: блокировку отмечают GNOME, KDE и другие. «auto» — сеанс этой программы.
    system = QDBusConnection.systemBus()
    if system.isConnected() and _dbus_answer(
            system, "org.freedesktop.login1", "/org/freedesktop/login1/session/auto",
            "org.freedesktop.DBus.Properties", "Get", "org.freedesktop.login1.Session", "LockedHint") is True:
        return True
    session = QDBusConnection.sessionBus()
    if session.isConnected():
        for service, path, interface in _SCREENSAVERS:
            if _dbus_answer(session, service, path, interface, "GetActive") is True:
                return True
    return False


def screen_locked():
    """Заблокирован ли экран (macOS, Windows, Linux). На других системах — False."""
    if sys.platform == "win32":
        return _windows_screen_locked()
    if sys.platform.startswith("linux"):
        return _linux_screen_locked()
    if sys.platform != "darwin":
        return False
    try:
        cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
        cg = ctypes.CDLL(ctypes.util.find_library("CoreGraphics"))
        cg.CGSessionCopyCurrentDictionary.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFDictionaryGetValue.restype = ctypes.c_void_p
        cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        session = cg.CGSessionCopyCurrentDictionary()
        if not session:
            return False  # нет графического сеанса — не повод блокировать
        key = cf.CFStringCreateWithCString(None, b"CGSSessionScreenIsLocked", 0x08000100)  # UTF-8
        try:
            return bool(cf.CFDictionaryGetValue(session, key))
        finally:
            cf.CFRelease(key)
            cf.CFRelease(session)
    except (OSError, AttributeError, TypeError):
        return False


# действия человека в окнах WhoKey: от них отсчитывается бездействие
_INPUT_EVENTS = {QEvent.KeyPress, QEvent.MouseButtonPress, QEvent.Wheel}


class AutoLock(QObject):
    """Сигнал lock(причина) — экран заблокировали или компьютер проснулся после сна
    ("system"), или в WhoKey долго ничего не делали ("idle", время — в Настройках)."""

    lock = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clocks = (time.time(), monotonic())
        self._last_input = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_EVERY_MS)
        self._timer.timeout.connect(self._check)
        app = QCoreApplication.instance()
        if app is not None:
            app.installEventFilter(self)  # смотрим на нажатия во всех окнах, ничего не меняя

    def eventFilter(self, obj, event):
        if event.type() in _INPUT_EVENTS:
            self._last_input = time.monotonic()
        return False

    def start(self):
        self._clocks = (time.time(), monotonic())
        self._last_input = time.monotonic()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def touch(self):
        """Человек что-то сделал вне окон WhoKey, но для WhoKey (нажал в расширении)."""
        self._last_input = time.monotonic()

    def _check(self):
        wall, mono = time.time(), monotonic()
        slept = (wall - self._clocks[0]) - (mono - self._clocks[1]) > SLEEP_GAP
        self._clocks = (wall, mono)
        if slept or screen_locked():
            self.lock.emit("system")
            return
        minutes = prefs.idle_lock_minutes()
        if minutes and time.monotonic() - self._last_input > minutes * 60:
            self.lock.emit("idle")
