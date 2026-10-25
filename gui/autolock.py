"""Автоблокировка: при блокировке экрана или сне Mac WhoKey закрывает хранилище.

После этого расширение браузера ничего не получит, пока снова не введён
мастер-пароль. Во время обычной работы ничего не происходит.

Без сторонних библиотек: раз в несколько секунд спрашиваем систему.
  - экран заблокирован — CoreGraphics (встроен в macOS) возвращает словарь
    текущего сеанса, в нём есть ключ CGSSessionScreenIsLocked;
  - Mac спал — «монотонные» часы во сне стоят, а обычные идут: если разница
    между ними вдруг выросла, значит, был сон.
"""

import ctypes
import ctypes.util
import sys
import time

from PySide6.QtCore import QObject, QTimer, Signal

CHECK_EVERY_MS = 3000
SLEEP_GAP = 20  # секунд «пропало» из монотонного времени — считаем, что Mac спал


def screen_locked():
    """Заблокирован ли экран (macOS). На других системах — False."""
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


class AutoLock(QObject):
    """Сигнал lock — когда экран заблокировали или Mac проснулся после сна."""

    lock = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clocks = (time.time(), time.monotonic())
        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_EVERY_MS)
        self._timer.timeout.connect(self._check)

    def start(self):
        self._clocks = (time.time(), time.monotonic())
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _check(self):
        wall, mono = time.time(), time.monotonic()
        slept = (wall - self._clocks[0]) - (mono - self._clocks[1]) > SLEEP_GAP
        self._clocks = (wall, mono)
        if slept or screen_locked():
            self.lock.emit()
