"""Буфер обмена приложения — через QClipboard (Qt), с автоочисткой и пометкой «секретное».

Консольная версия (manager.py) пользуется clipboard.py: в ней нет Qt. Приложение
с окнами — этим модулем: Qt сам работает с буфером на Windows, macOS и Linux,
без внешних команд и скриптов.

Пометки «не сохранять пароль в истории буфера» — те же, что ставит KeePassXC:
  - Windows: форматы ExcludeClipboardContentFromMonitorProcessing,
    CanIncludeInClipboardHistory = 0 и CanUploadToCloudClipboard = 0 — пароль
    не попадает в журнал Win+V и в облачный буфер;
  - Linux: x-kde-passwordManagerHint = secret (понимают Klipper и другие);
  - macOS: org.nspasteboard.ConcealedType и TransientType, и «только этот Mac»
    (без Universal Clipboard на другие устройства Apple). Через Qt такое имя
    формата не задать (QUtiMimeConverter в PySide6 нет), поэтому на macOS
    текст с пометками кладёт прямой вызов системного NSPasteboard (ctypes),
    а читает и стирает буфер — QClipboard, как на других системах.
"""

import ctypes
import ctypes.util
import sys

from PySide6.QtCore import QMimeData, QObject, QTimer
from PySide6.QtGui import QGuiApplication

from gui import prefs


def _windows_format(name):
    """Так Qt кладёт данные в системный формат Windows с точным именем."""
    return f'application/x-qt-windows-mime;value="{name}"'


def _copy_macos(secret):
    """Кладёт текст в буфер macOS сразу с пометками «секретное» и «временное».

    Одним вызовом системного NSPasteboard (через ctypes, без внешних программ):
    Qt на macOS записывает буфер «лениво» и при следующем обращении переписывает
    его заново, поэтому добавить пометки поверх записи Qt не получается.
    """
    objc = ctypes.CDLL(ctypes.util.find_library("objc"))
    ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")  # класс NSPasteboard
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]

    def send(restype, *argtypes):
        # objc_msgSend на Apple Silicon нужно вызывать с точными типами аргументов
        return ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes)(("objc_msgSend", objc))

    def nsstring(text):
        return send(ctypes.c_void_p, ctypes.c_char_p)(
            objc.objc_getClass(b"NSString"), objc.sel_registerName(b"stringWithUTF8String:"),
            text.encode("utf-8"))

    board = send(ctypes.c_void_p)(objc.objc_getClass(b"NSPasteboard"), objc.sel_registerName(b"generalPasteboard"))
    plain = nsstring("public.utf8-plain-text")
    marks = [nsstring("org.nspasteboard.ConcealedType"), nsstring("org.nspasteboard.TransientType")]
    types = send(ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_ulong)(
        objc.objc_getClass(b"NSArray"), objc.sel_registerName(b"arrayWithObjects:count:"),
        (ctypes.c_void_p * 3)(plain, *marks), 3)
    # вместо clearContents: «только этот Mac» (NSPasteboardContentsCurrentHostOnly) —
    # Universal Clipboard не отправит пароль на iPhone и другие устройства Apple
    send(ctypes.c_long, ctypes.c_ulong)(board, objc.sel_registerName(b"prepareForNewContentsWithOptions:"), 1)
    send(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)(board, objc.sel_registerName(b"addTypes:owner:"), types, None)
    set_string = send(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    if not set_string(board, objc.sel_registerName(b"setString:forType:"), nsstring(secret), plain):
        raise OSError("NSPasteboard refused the text")
    for mark in marks:
        set_string(board, objc.sel_registerName(b"setString:forType:"), nsstring(""), mark)


class SecureClipboard(QObject):
    """То же, что clipboard.Clipboard у консольной версии: copy / clear / clear_now."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._secret = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.clear)

    def copy(self, secret):
        """Кладёт пароль в буфер с пометками и заводит таймер очистки. False — если не вышло."""
        board = QGuiApplication.clipboard()
        if board is None:
            return False
        # напрямую в NSPasteboard — только когда Qt и правда работает с буфером macOS
        # (в режиме без экрана, offscreen, у Qt свой буфер в памяти)
        if sys.platform == "darwin" and QGuiApplication.platformName() == "cocoa":
            try:
                _copy_macos(secret)
            except (OSError, AttributeError, TypeError, ValueError):
                board.setText(secret)  # без пометок — лучше, чем никак; сотрётся по таймеру
        else:
            data = QMimeData()
            data.setText(secret)
            if sys.platform == "win32":
                data.setData(_windows_format("ExcludeClipboardContentFromMonitorProcessing"), b"\x01\x00\x00\x00")
                data.setData(_windows_format("CanIncludeInClipboardHistory"), b"\x00\x00\x00\x00")
                data.setData(_windows_format("CanUploadToCloudClipboard"), b"\x00\x00\x00\x00")
            else:
                data.setData("x-kde-passwordManagerHint", b"secret")
            board.setMimeData(data)  # буфер забирает data себе — удалять её самим нельзя
        if board.text() != secret:
            return False
        self._secret = secret
        self._timer.start(prefs.clear_after() * 1000)  # время — в Настройках
        return True

    def clear(self):
        """Очищает буфер — но только если там всё ещё наш пароль.

        Если человек за это время скопировал что-то своё, не трогаем.
        Возвращает True, если буфер был очищен.
        """
        if self._secret is None:
            return False
        board = QGuiApplication.clipboard()
        cleared = False
        if board is not None and board.text() == self._secret:
            board.clear()
            cleared = True
        self._secret = None
        return cleared

    def clear_now(self):
        """При выходе и при автоблокировке — не ждать 30 секунд."""
        self._timer.stop()
        return self.clear()
