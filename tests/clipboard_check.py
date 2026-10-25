"""Проверка буфера обмена приложения на НАСТОЯЩЕМ системном буфере (не offscreen).

smoke_test.py запускает Qt без экрана, а там у Qt свой буфер в памяти — пометки
Windows и macOS в нём не проверить. Поэтому эта проверка — отдельной программой
с обычной платформой Qt. Печатает строки OK/FAIL, код выхода 1 — если что-то не так.

    python tests/clipboard_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
from gui.secure_clipboard import SecureClipboard  # noqa: E402

results = []


def check(ok, text):
    results.append(bool(ok))
    print(("OK   " if ok else "FAIL ") + text, flush=True)


def windows_flags():
    """Какие пометки лежат в системном буфере Windows и с какими значениями."""
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    found = {}
    user32.OpenClipboard(None)
    try:
        for name in ("ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory",
                     "CanUploadToCloudClipboard"):
            fmt = user32.RegisterClipboardFormatW(name)
            if not user32.IsClipboardFormatAvailable(fmt):
                continue
            handle = user32.GetClipboardData(fmt)
            pointer = kernel32.GlobalLock(handle) if handle else None
            found[name] = ctypes.c_uint32.from_address(pointer).value if pointer else None
            if pointer:
                kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
    return found


print("платформа Qt:", QApplication.platformName())
secret = "Пароль-Ж ü #42"
board = SecureClipboard()
check(board.copy(secret), "пароль скопирован")
check(QApplication.clipboard().text() == secret, "в системном буфере ровно тот пароль")
if sys.platform == "win32":
    flags = windows_flags()
    print("пометки в буфере Windows:", flags)
    check("ExcludeClipboardContentFromMonitorProcessing" in flags, "пометка ExcludeClipboardContentFromMonitorProcessing")
    check(flags.get("CanIncludeInClipboardHistory") == 0, "пометка CanIncludeInClipboardHistory = 0 (не в журнал Win+V)")
    check(flags.get("CanUploadToCloudClipboard") == 0, "пометка CanUploadToCloudClipboard = 0 (не в облачный буфер)")
check(board.clear_now() and QApplication.clipboard().text() == "", "буфер очищен")
sys.exit(0 if all(results) else 1)
