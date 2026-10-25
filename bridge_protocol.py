"""Общее для моста между расширением браузера и WhoKey (только стандартная библиотека).

Как устроено:
  расширение ──native messaging──> мост ──локальный сокет──> открытый WhoKey
Браузер сам запускает мост (это тот же WhoKey, но с аргументом
chrome-extension://…/ — см. app.py) и общается с ним через stdin/stdout:
4 байта длины + JSON. Мост пересылает запрос в WhoKey одной строкой JSON
через локальный сокет: на Mac это файл в папке программы, доступный только
владельцу; сеть не используется вообще.

Обе стороны проверяют друг друга (по ревью безопасности): система сообщает,
какой процесс на другом конце сокета, и это должна быть та же программа —
сам WhoKey. Так случайный скрипт не получит пароли из WhoKey, а поддельный
«WhoKey», пока настоящий закрыт, не получит ключ и не подсунет свой пароль.
"""

import ctypes
import ctypes.util
import json
import os
import secrets
import socket
import stat
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from vault import app_data_dir

HOST_NAME = "ru.edu.whokey"                       # имя моста для браузера
EXTENSION_ID = "pchmmhgfnhhkginkifminckbjcojodgl"  # закреплён ключом в extension/manifest.json
MAX_LINE = 64 * 1024                               # больше запрос/ответ быть не может

# Папки, где браузеры на основе Chromium ищут описания мостов (macOS)
BROWSER_DIRS = [
    "Google/Chrome", "Google/Chrome Beta", "Chromium", "Microsoft Edge",
    "BraveSoftware/Brave-Browser", "Vivaldi", "Arc/User Data", "Yandex/YandexBrowser",
    "net.imput.helium",
]


def socket_address():
    """Адрес локального сокета WhoKey (QLocalServer понимает полный путь)."""
    path = app_data_dir() / "bridge.sock"
    if len(str(path)) < 100:  # у Unix-сокета путь не длиннее ~104 символов
        return str(path)
    # личная временная папка (на Mac у каждого пользователя своя, права 700),
    # а не общий /tmp, где другой пользователь мог бы занять имя первым
    return os.path.join(tempfile.gettempdir(), f"whokey-{os.getuid()}.sock")


# --- кто на другом конце сокета ---

def new_key():
    """Ключ для расширения: 256 случайных бит."""
    return secrets.token_urlsafe(32)


def _program_of(pid):
    """Путь к программе процесса pid (macOS, через libproc) или None."""
    try:
        libproc = ctypes.CDLL(ctypes.util.find_library("proc") or "/usr/lib/libproc.dylib")
        buffer = ctypes.create_string_buffer(4096)
        if libproc.proc_pidpath(pid, buffer, ctypes.sizeof(buffer)) <= 0:
            return None
        return os.path.realpath(buffer.value.decode("utf-8"))
    except (OSError, ValueError, AttributeError):
        return None


def own_program():
    """Путь к этой программе — так, как его видит система (у собранного WhoKey — он сам).

    Не sys.executable: системный Python на Mac при запуске подменяет себя
    программой внутри Python.app, и пути не совпали бы.
    """
    if sys.platform == "darwin":
        path = _program_of(os.getpid())
        if path:
            return path
    return os.path.realpath(sys.executable)


def peer_program(sock):
    """Путь к программе процесса на другом конце Unix-сокета (macOS) или None."""
    if sys.platform != "darwin":
        return None
    try:
        pid = sock.getsockopt(0, 0x002)  # SOL_LOCAL, LOCAL_PEERPID
    except OSError:
        return None
    return _program_of(pid)


def trusted_peer(sock):
    """Тот ли процесс на другом конце: та же программа, что и мы (WhoKey ↔ его мост)."""
    if sys.platform != "darwin":
        return True  # на других системах проверки пока нет (Windows — следующим шагом)
    return peer_program(sock) == own_program()


# --- native messaging: как браузер разговаривает с мостом ---

def read_message(stream):
    """Сообщение от браузера или None, если браузер закрыл соединение."""
    header = stream.read(4)
    if len(header) < 4:
        return None
    size = struct.unpack("<I", header)[0]
    if size > MAX_LINE:
        return None
    return json.loads(stream.read(size).decode("utf-8"))


def write_message(stream, message):
    data = json.dumps(message, ensure_ascii=False).encode("utf-8")
    stream.write(struct.pack("<I", len(data)) + data)
    stream.flush()


# --- запрос к открытому WhoKey ---

class PeerError(Exception):
    """На другом конце сокета не WhoKey. Не OSError: мост не должен считать это «WhoKey закрыт»."""


def ask_app(message, timeout=120):
    """Отправляет запрос в WhoKey и ждёт ответа. OSError — если WhoKey не слушает.

    timeout большой: на первый запрос WhoKey может показать окно
    «Разрешить расширению доступ?», и человек думает над ответом.
    """
    address = socket_address()
    info = os.lstat(address)  # не идём по ссылке: это должен быть сокет нашего пользователя
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise ConnectionRefusedError("not our socket")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        conn.connect(address)
        if not trusted_peer(conn):
            raise PeerError("the socket is not served by WhoKey")
        conn.sendall(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
        data = b""
        while b"\n" not in data:
            chunk = conn.recv(4096)
            if not chunk or len(data) > MAX_LINE:
                raise OSError("WhoKey closed the connection")
            data += chunk
    return json.loads(data.split(b"\n", 1)[0].decode("utf-8"))


def launch_app():
    """Открывает WhoKey (если уже открыт — просто выводит его окно вперёд)."""
    exe = Path(sys.executable).resolve()
    bundle = exe.parents[2] if len(exe.parents) > 2 else None
    # stdin/stdout моста — канал к браузеру: запущенной программе он не нужен,
    # а её вывод сломал бы разговор с браузером
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
             "stderr": subprocess.DEVNULL, "start_new_session": True}
    if getattr(sys, "frozen", False) and bundle is not None and bundle.suffix == ".app":
        subprocess.Popen(["open", str(bundle)], **quiet)  # open сам не запустит вторую копию
    else:  # запуск из исходников (разработка)
        subprocess.Popen([sys.executable, str(Path(__file__).resolve().parent / "app.py")], **quiet)


# --- регистрация моста в браузерах ---

def install_native_host(executable):
    """Пишет описание моста во все установленные Chromium-браузеры.

    Браузер запустит executable, когда расширение попросит, и только для
    расширения с нашим ID (allowed_origins). Вызывается при каждом запуске
    WhoKey: если программу перенесли в другую папку, путь обновится.
    Возвращает, в какие браузеры записано.

    Не прописывает временные пути: запуск прямо из установщика (/Volumes/…)
    или из «карантинной» копии macOS (AppTranslocation) — после закрытия
    образа мост бы сломался.
    """
    if str(executable).startswith("/Volumes/") or "/AppTranslocation/" in str(executable):
        return []
    manifest = {
        "name": HOST_NAME,
        "description": "WhoKey password manager bridge",
        "path": str(executable),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"],
    }
    support = Path.home() / "Library" / "Application Support"
    done = []
    for browser in BROWSER_DIRS:
        base = support / browser
        if not base.is_dir():  # браузер не установлен — его папок не трогаем
            continue
        folder = base / "NativeMessagingHosts"
        target = folder / f"{HOST_NAME}.json"
        try:
            folder.mkdir(exist_ok=True)
            text = json.dumps(manifest, indent=2)
            if target.is_symlink() or not target.exists() or target.read_text(encoding="utf-8") != text:
                # через временный файл и подмену: если на месте файла кто-то оставил
                # символическую ссылку, заменится сама ссылка, а не файл, на который она указывает
                fd, tmp = tempfile.mkstemp(dir=folder, prefix=".whokey-", suffix=".json")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(text)
                os.chmod(tmp, 0o644)
                os.replace(tmp, target)
            done.append(browser)
        except OSError:
            pass
    return done
