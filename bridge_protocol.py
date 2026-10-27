"""Общее для моста между расширением браузера и WhoKey (только стандартная библиотека).

Как устроено:
  расширение ──native messaging──> мост ──локальный сокет──> открытый WhoKey
Браузер сам запускает мост (это тот же WhoKey, но с аргументом
chrome-extension://…/ — см. app.py) и общается с ним через stdin/stdout:
4 байта длины + JSON. Мост пересылает запрос в WhoKey одной строкой JSON
через локальный сокет: на Mac это файл в папке программы, доступный только
владельцу, на Windows — именованный канал (named pipe), открытый только для
текущего пользователя; сеть не используется вообще.

Обе стороны проверяют друг друга (по ревью безопасности): система сообщает,
какой процесс на другом конце сокета, и это должна быть та же программа —
сам WhoKey. Так случайный скрипт не получит пароли из WhoKey, а поддельный
«WhoKey», пока настоящий закрыт, не получит ключ и не подсунет свой пароль.
"""

import ctypes
import ctypes.util
import hashlib
import json
import os
import secrets
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from vault import app_data_dir

HOST_NAME = "ru.edu.whokey"                       # имя моста для браузера
EXTENSION_ID = "pchmmhgfnhhkginkifminckbjcojodgl"  # закреплён ключом в extension/manifest.json
MAX_LINE = 64 * 1024                               # больше запрос/ответ быть не может

WINDOWS = sys.platform == "win32"

# Папки, где браузеры на основе Chromium ищут описания мостов (macOS)
BROWSER_DIRS = [
    "Google/Chrome", "Google/Chrome Beta", "Chromium", "Microsoft Edge",
    "BraveSoftware/Brave-Browser", "Vivaldi", "Arc/User Data", "Yandex/YandexBrowser",
    "net.imput.helium",
]


# Ключи реестра, где их ищут на Windows (в HKEY_CURRENT_USER\Software\…)
WINDOWS_BROWSER_KEYS = [
    "Google\\Chrome", "Chromium", "Microsoft\\Edge", "BraveSoftware\\Brave-Browser",
    "Vivaldi", "Yandex\\YandexBrowser",
]


def _user_tag():
    """Метка пользователя для имён каналов. На Windows — из SID учётной записи
    (переменные окружения USERNAME может подделать кто угодно)."""
    name = (current_sid() or "") if WINDOWS else str(os.getuid())
    return hashlib.sha256(name.lower().encode("utf-8")).hexdigest()[:16]


def socket_address():
    """Адрес локального сокета WhoKey (QLocalServer понимает полный путь).

    На Windows — имя именованного канала (\\\\.\\pipe\\…): своё у каждого пользователя.
    """
    if WINDOWS:
        return "whokey-" + _user_tag()
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
    if WINDOWS:
        return _windows_own_program()
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
        return True  # Windows проверяет по-своему (trusted_pipe_client, WinPipe.server_program)
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
    if WINDOWS:
        return _ask_app_windows(message, timeout)
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
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if WINDOWS:
        command = [sys.executable] if getattr(sys, "frozen", False) else \
            [sys.executable, str(Path(__file__).resolve().parent / "app.py")]
        # без окна консоли, отдельно от моста: браузер держит мост в «задании» Windows
        # и при выходе моста закрыл бы всё, что тот запустил, — поэтому просим выйти из него
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen(command, creationflags=flags | 0x01000000, **quiet)  # CREATE_BREAKAWAY_FROM_JOB
        except OSError:  # задание не разрешает выходить — запускаем как есть
            subprocess.Popen(command, creationflags=flags, **quiet)
        return  # вторую копию WhoKey не откроет: она передаст окно первой (app.py)
    quiet["start_new_session"] = True
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
    if WINDOWS:
        return _install_native_host_windows(executable)
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


# --- Windows: именованный канал, проверка собеседника, реестр ---
# Только стандартная библиотека (ctypes): мост запускается без Qt.

if WINDOWS:
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                 wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
    _k32.GetNamedPipeServerProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
    _k32.GetNamedPipeClientProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
    _k32.PeekNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                                   ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    _k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                              ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    _k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    _k32.GetNamedPipeClientSessionId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
    _k32.GetNamedPipeClientComputerNameW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.ULONG]
    _k32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    _k32.GetCurrentProcess.restype = wintypes.HANDLE
    _k32.LocalFree.argtypes = [ctypes.c_void_p]
    _adv = ctypes.WinDLL("advapi32", use_last_error=True)
    _adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    _adv.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.POINTER(wintypes.DWORD)]
    _adv.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    _adv.GetSecurityInfo.restype = wintypes.DWORD
    _adv.GetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
                                     ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                     ctypes.POINTER(ctypes.c_void_p)]
    _INVALID = wintypes.HANDLE(-1).value
    _ERROR_PIPE_BUSY, _ERROR_BROKEN_PIPE = 231, 109


def _windows_program_of(pid):
    """Путь к программе процесса pid (Windows) или None."""
    handle = _k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not _k32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return os.path.normcase(os.path.realpath(buffer.value))
    finally:
        _k32.CloseHandle(handle)


def _windows_own_program():
    # программа процесса так, как её видит система: в виртуальном окружении
    # Scripts\python.exe лишь запускает настоящий python.exe, и пути не совпали бы
    return _windows_program_of(os.getpid()) or os.path.normcase(os.path.realpath(sys.executable))


def _sid_string(sid_pointer):
    text = wintypes.LPWSTR()
    if not _adv.ConvertSidToStringSidW(sid_pointer, ctypes.byref(text)):
        return None
    try:
        return text.value
    finally:
        _k32.LocalFree(text)


def current_sid():
    """SID учётной записи, от которой запущены (Windows), строкой «S-1-5-…»."""
    token = wintypes.HANDLE()
    if not _adv.OpenProcessToken(_k32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
        return None
    try:
        size = wintypes.DWORD()
        _adv.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))  # TokenUser — узнать размер
        buffer = ctypes.create_string_buffer(size.value)
        if not _adv.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            return None
        return _sid_string(ctypes.c_void_p.from_buffer(buffer).value)  # TOKEN_USER начинается с указателя на SID
    finally:
        _k32.CloseHandle(token)


def pipe_owner_sid(handle):
    """Чей канал: SID владельца (Windows). Чужой пользователь не может создать канал
    с нашим SID владельцем — так отсекаем каналы, занятые другой учётной записью."""
    owner, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
    # SE_KERNEL_OBJECT (6), OWNER_SECURITY_INFORMATION (1)
    if _adv.GetSecurityInfo(handle, 6, 1, ctypes.byref(owner), None, None, None, ctypes.byref(descriptor)) != 0:
        return None
    try:
        return _sid_string(owner)
    finally:
        _k32.LocalFree(descriptor)


def trusted_pipe_client(handle):
    """Сервер WhoKey: на другом конце канала — наш мост (та же программа)? (Windows)

    Номер процесса собеседника Windows сообщает со слов клиента, и программа того же
    пользователя может его подделать (Project Zero, 2019) — поэтому это лишь одна из
    преград. Настоящая защита — ключ сопряжения и разрешение человека в окне WhoKey.
    Дополнительно: только с этого же компьютера и из этого же сеанса Windows.
    """
    handle = wintypes.HANDLE(int(handle))
    computer = ctypes.create_unicode_buffer(256)
    if _k32.GetNamedPipeClientComputerNameW(handle, computer, ctypes.sizeof(computer)):
        return False  # подключились по сети — только для удалённых клиентов это удаётся
    session, own_session = wintypes.ULONG(), wintypes.DWORD()
    if (not _k32.GetNamedPipeClientSessionId(handle, ctypes.byref(session))
            or not _k32.ProcessIdToSessionId(os.getpid(), ctypes.byref(own_session))
            or session.value != own_session.value):
        return False
    pid = wintypes.ULONG()
    if not _k32.GetNamedPipeClientProcessId(handle, ctypes.byref(pid)):
        return False
    return _windows_program_of(pid.value) == _windows_own_program()


class WinPipe:
    """Клиентский конец именованного канала WhoKey (Windows): то, что на Mac — Unix-сокет."""

    def __init__(self, name):
        path = "\\\\.\\pipe\\" + name
        for _attempt in range(3):
            # SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION: чужой сервер на этом канале
            # не сможет действовать от имени моста (только узнать, кто подключился)
            self.handle = _k32.CreateFileW(path, 0x80000000 | 0x40000000, 0, None, 3, 0x00110000, None)
            if self.handle != _INVALID:
                return
            error = ctypes.get_last_error()
            if error != _ERROR_PIPE_BUSY:
                break
            _k32.WaitNamedPipeW(path, 1000)  # все «линии» заняты — подождать свободную
        raise ConnectionRefusedError(f"WhoKey is not listening (Windows error {error})")

    def server_program(self):
        pid = wintypes.ULONG()
        if not _k32.GetNamedPipeServerProcessId(self.handle, ctypes.byref(pid)):
            return None
        return _windows_program_of(pid.value)

    def write(self, data):
        while data:
            done = wintypes.DWORD()
            if not _k32.WriteFile(self.handle, data, len(data), ctypes.byref(done), None):
                raise OSError("WhoKey closed the connection")
            data = data[done.value:]

    def read_available(self):
        """Что уже пришло (b"" — пока ничего). OSError — если WhoKey закрыл канал."""
        waiting = wintypes.DWORD()
        if not _k32.PeekNamedPipe(self.handle, None, 0, None, ctypes.byref(waiting), None):
            raise OSError("WhoKey closed the connection")
        if not waiting.value:
            return b""
        buffer = ctypes.create_string_buffer(waiting.value)
        done = wintypes.DWORD()
        if not _k32.ReadFile(self.handle, buffer, waiting.value, ctypes.byref(done), None):
            raise OSError("WhoKey closed the connection")
        return buffer.raw[:done.value]

    def close(self):
        if self.handle not in (None, _INVALID):
            _k32.CloseHandle(self.handle)
            self.handle = None


def _ask_app_windows(message, timeout):
    pipe = WinPipe(socket_address())
    try:
        # пока WhoKey закрыт, канал с таким именем могла открыть чужая программа
        if pipe_owner_sid(pipe.handle) != current_sid() or pipe.server_program() != _windows_own_program():
            raise PeerError("the pipe is not served by WhoKey")
        pipe.write(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
        data, deadline = b"", time.monotonic() + timeout
        while b"\n" not in data:
            if len(data) > MAX_LINE:
                raise OSError("reply too long")
            chunk = pipe.read_available()
            if not chunk:
                if time.monotonic() > deadline:
                    raise socket.timeout("timed out")
                time.sleep(0.03)
            data += chunk
    finally:
        pipe.close()
    return json.loads(data.split(b"\n", 1)[0].decode("utf-8"))


def pipe_alive(handle):
    """Мост: браузер ещё держит канал stdin? (Windows) False — браузер закрыл соединение."""
    waiting = wintypes.DWORD()
    if _k32.PeekNamedPipe(wintypes.HANDLE(handle), None, 0, None, ctypes.byref(waiting), None):
        return True
    return ctypes.get_last_error() != _ERROR_BROKEN_PIPE


def _install_native_host_windows(executable):
    """Windows: описание моста — файлом в папке программы, путь к нему — в реестре браузеров."""
    import winreg
    temp = os.path.normcase(os.path.realpath(tempfile.gettempdir()))
    exe = os.path.normcase(os.path.realpath(str(executable)))
    try:
        inside_temp = os.path.commonpath([temp, exe]) == temp
    except ValueError:  # разные диски
        inside_temp = False
    if inside_temp:
        return []  # запуск из временной папки (например, из архива) — путь скоро пропадёт
    manifest = {
        "name": HOST_NAME,
        "description": "WhoKey password manager bridge",
        "path": str(executable),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"],
    }
    folder = app_data_dir() / "native-host"
    target = folder / f"{HOST_NAME}.json"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        text = json.dumps(manifest, indent=2)
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            fd, tmp = tempfile.mkstemp(dir=folder, prefix=".whokey-", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, target)
    except OSError:
        return []
    done = []
    for browser in WINDOWS_BROWSER_KEYS:
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  f"Software\\{browser}\\NativeMessagingHosts\\{HOST_NAME}") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(target))
            done.append(browser)
        except OSError:
            pass
    return done
