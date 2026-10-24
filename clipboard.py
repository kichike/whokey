"""Копирование пароля в буфер обмена с автоочисткой.

Используются встроенные команды системы: pbcopy/pbpaste на Mac,
PowerShell на Windows. Пароль передаётся им через стандартный ввод,
а не в командной строке — иначе его было бы видно в списке процессов.

Риск, о котором стоит помнить: пока пароль в буфере, его может прочитать
любая программа, а на Mac буфер может синхронизироваться на iPhone/iPad
(«Универсальный буфер обмена»). Поэтому буфер очищается через 30 секунд
и при выходе из программы.
"""

import os
import subprocess
import sys
import threading

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
        # Set-Clipboard корректно понимает русские буквы, в отличие от clip
        _run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"], text)
    else:
        raise OSError("clipboard is not supported on this system")


def _read():
    if sys.platform == "darwin":
        return _run(["pbpaste"])
    if sys.platform == "win32":
        return _run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"]).rstrip("\r\n")
    return ""


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
