"""Копирование пароля в буфер обмена с автоочисткой.

На Mac — встроенные команды системы (osascript, pbcopy/pbpaste). Пароль
передаётся им через стандартный ввод, а не в командной строке — иначе его
было бы видно в списке процессов. На Windows — прямые вызовы системы
(user32.dll через ctypes): без PowerShell, который мигал бы окном консоли
и портил русские буквы.

Риск, о котором стоит помнить: пока пароль в буфере, его может прочитать
любая программа, а на Mac буфер может синхронизироваться на iPhone/iPad
(«Универсальный буфер обмена»). Поэтому буфер очищается через 30 секунд
и при выходе из программы.
"""

import os
import subprocess
import sys
import threading
import time

CLEAR_AFTER = 30  # секунд


def _run(command, text=None):
    # Явно UTF-8: без этого pbcopy/pbpaste портят русские буквы, и тогда
    # в буфер попал бы не тот пароль, а проверка при очистке не совпала бы
    env = dict(os.environ, LANG="en_US.UTF-8", LC_ALL="en_US.UTF-8")
    result = subprocess.run(command, input=text, capture_output=True,
                            text=True, encoding="utf-8", env=env)
    if result.returncode != 0:
        raise OSError(f"{command[0]} exited with code {result.returncode}")
    return result.stdout


# Скрипт на JavaScript для macOS (JXA, встроен в систему — ничего ставить не нужно).
# Кладёт текст в буфер с пометками org.nspasteboard.ConcealedType («секретное»)
# и TransientType («временное»): по этому общему соглашению программы с историей
# буфера (Raycast, Alfred, Maccy…) такой текст не сохраняют. Так делает KeePassXC.
# Сам пароль приходит через стандартный ввод, а не в тексте скрипта.
_CONCEALED_COPY = """
ObjC.import('AppKit');
var data = $.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile;
var text = $.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding);
var pb = $.NSPasteboard.generalPasteboard;
pb.clearContents;
pb.declareTypesOwner($(['public.utf8-plain-text', 'org.nspasteboard.ConcealedType',
                        'org.nspasteboard.TransientType']), null);
pb.setStringForType(text, 'public.utf8-plain-text');
pb.setStringForType($(''), 'org.nspasteboard.ConcealedType');
pb.setStringForType($(''), 'org.nspasteboard.TransientType');
'';
"""


def _write(text):
    if sys.platform == "darwin":
        if text:
            try:
                _run(["osascript", "-l", "JavaScript", "-e", _CONCEALED_COPY], text)
                return
            except (OSError, subprocess.SubprocessError):
                pass  # не вышло — обычное копирование (без пометок) лучше, чем никакого
        _run(["pbcopy"], text)
    elif sys.platform == "win32":
        _win_write(text)
    else:
        raise OSError("clipboard is not supported on this system")


def _read():
    if sys.platform == "darwin":
        return _run(["pbpaste"])
    if sys.platform == "win32":
        return _win_read()
    return ""


# --- Windows ---

CF_UNICODETEXT = 13
# Пометки для Windows 10/11 (так же делает KeePassXC): не записывать текст
# в журнал буфера (Win+V), не отправлять в облачный буфер на другие устройства
# и не показывать программам-«наблюдателям» за буфером.
_WIN_PRIVATE_FORMATS = ("ExcludeClipboardContentFromMonitorProcessing",
                        "CanIncludeInClipboardHistory", "CanUploadToCloudClipboard")


def _win_api():
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # типы обязательно: без них 64-битные указатели обрезались бы до 32 бит
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    return ctypes, user32, kernel32


def _win_open(user32):
    # буфер мог на мгновение занять другая программа — пробуем несколько раз
    for _ in range(20):
        if user32.OpenClipboard(None):
            return
        time.sleep(0.025)
    raise OSError("clipboard is busy")


def _win_put(ctypes, user32, kernel32, fmt, data):
    """Кладёт байты data в буфер в формате fmt (буфер уже открыт)."""
    handle = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
    if not handle:
        raise OSError("GlobalAlloc failed")
    pointer = kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)
    if not user32.SetClipboardData(fmt, handle):
        kernel32.GlobalFree(handle)  # память осталась нашей — освобождаем сами
        raise OSError("SetClipboardData failed")
    # после успешного SetClipboardData памятью владеет Windows — не освобождаем


def _win_write(text):
    ctypes, user32, kernel32 = _win_api()
    _win_open(user32)
    try:
        if not user32.EmptyClipboard():
            raise OSError("EmptyClipboard failed")
        if text:
            _win_put(ctypes, user32, kernel32, CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
            for name in _WIN_PRIVATE_FORMATS:
                # значение 0 (4 байта) = «нельзя»; для первой пометки важен сам факт.
                # Не вышло — не страшно: пароль уже в буфере, и если бы мы сообщили
                # «не скопировано», таймер очистки не запустился бы
                try:
                    _win_put(ctypes, user32, kernel32, user32.RegisterClipboardFormatW(name), bytes(4))
                except OSError:
                    pass
    finally:
        user32.CloseClipboard()


def _win_read():
    ctypes, user32, kernel32 = _win_api()
    _win_open(user32)
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


class Clipboard:
    def __init__(self):
        self._timer = None
        self._secret = None
        # таймер очистки работает в отдельном потоке — замок не даёт ему
        # и основной программе менять _secret одновременно
        self._lock = threading.Lock()

    def copy(self, secret):
        """Кладёт пароль в буфер и заводит таймер очистки. False — если не вышло."""
        with self._lock:
            try:
                _write(secret)
            except (OSError, subprocess.SubprocessError):
                return False
            self._cancel_timer()
            self._secret = secret
            self._timer = threading.Timer(CLEAR_AFTER, self.clear)
            self._timer.daemon = True  # не мешать программе завершиться
            self._timer.start()
            return True

    def clear(self):
        """Очищает буфер — но только если там всё ещё наш пароль.

        Если пользователь за это время скопировал что-то своё, не трогаем.
        Возвращает True, если буфер был очищен.
        """
        with self._lock:
            if self._secret is None:
                return False
            cleared = False
            try:
                if _read() == self._secret:
                    _write("")
                    cleared = True
            except (OSError, subprocess.SubprocessError):
                pass
            self._secret = None
            return cleared

    def _cancel_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def clear_now(self):
        """При выходе из программы — не ждать 30 секунд, очистить сразу."""
        with self._lock:
            self._cancel_timer()
        return self.clear()
