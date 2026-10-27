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


def screen_locked():
    """Заблокирован ли экран (macOS, Windows). На других системах — False."""
    if sys.platform == "win32":
        return _windows_screen_locked()
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
