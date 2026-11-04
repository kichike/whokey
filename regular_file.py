"""Открытие только обычных файлов. FIFO или устройство (например, ссылка на /dev/zero
под видом CSV) подвесили бы окно WhoKey навсегда."""

import os
import stat

try:
    import fcntl
except ImportError:  # Windows: там нет ни fcntl, ни O_NONBLOCK
    fcntl = None


class NotRegularFile(OSError):
    """Это не обычный файл."""


def open_regular(path):
    """Дескриптор файла для чтения; NotRegularFile — если это FIFO, устройство или папка."""
    # без O_NONBLOCK само открытие FIFO зависло бы, пока кто-нибудь не начнёт в него писать
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise NotRegularFile("not a regular file")
    if fcntl is not None:
        # это обычный файл — дальше читаем обычным образом (например, чтобы iCloud успел его скачать)
        fcntl.fcntl(fd, fcntl.F_SETFL, fcntl.fcntl(fd, fcntl.F_GETFL) & ~os.O_NONBLOCK)
    return fd
