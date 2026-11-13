"""Обновление по кнопке: WhoKey сам находит новый релиз на GitHub, скачивает его,
проверяет подпись и ставит, перезапускаясь.

Почему так строго. Для менеджера паролей подменённое обновление — худшее, что может быть:
чужая программа получила бы все пароли. Поэтому:
  • Каждый релиз подписан ключом автора (sign_release.py, Ed25519). Открытая половина ключа —
    здесь, PUBLIC_KEY; секретная — только у автора, на GitHub её нет. Подписаны контрольные суммы
    файлов (SHA256SUMS) вместе с номером версии — старый релиз нельзя выдать за новый.
  • Скачанный файл ставится, только если его SHA-256 совпал с подписанным.
  • На Mac новая программа должна быть подписана тем же сертификатом, что и установленная
    (codesign), и иметь ту самую версию.
  • Только https, только релизы этого репозитория, ограничение размера ответов.
  • Ничего не уходит в сеть, кроме обычного запроса к GitHub (без данных пользователя).

Сеть — через QtNetwork (системные сертификаты на любой системе), окна не замирают.
Ставить можно только собранную программу (supported()); из исходников обновлений нет.
"""

import base64
import binascii
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from PySide6.QtCore import QObject, QProcess, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from gui import prefs
from gui.i18n import tr
from version import VERSION

# открытая половина ключа подписи релизов (sign_release.py init)
PUBLIC_KEY = bytes.fromhex("d4414d2647b11890086021fe331f1bdf73b92480817556605c42d125804dbd6a")

API_URL = "https://api.github.com/repos/kichike/whokey/releases/latest"
DOWNLOAD_PREFIX = "https://github.com/kichike/whokey/releases/download/"
SUMS_NAME = "SHA256SUMS"
SIGNATURE_NAME = "WhoKey-release.sig"
ASSETS = {"darwin": "WhoKey.Installer.dmg", "win32": "WhoKey.Installer.exe", "linux": "WhoKey-linux-x86_64.tar.gz"}

MAX_INFO = 2 * 1024 * 1024        # ответ GitHub о релизе
MAX_SMALL = 64 * 1024             # SHA256SUMS и подпись
MAX_PACKAGE = 600 * 1024 * 1024   # сам установщик
CHECK_EVERY = 20 * 3600           # тихая проверка — не чаще раза в сутки (с запасом)


class UpdateError(Exception):
    """Обновление не поставилось; текст — для человека."""


# --- без сети: версии, подпись, контрольные суммы ---

def platform_key():
    return "linux" if sys.platform.startswith("linux") else sys.platform


def asset_name():
    return ASSETS.get(platform_key())


def parse_version(text):
    """«1.10.0» или «v1.10.0» → (1, 10, 0); всё остальное — None."""
    match = re.fullmatch(r"v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})", text or "")
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(version, current=VERSION):
    new, old = parse_version(version), parse_version(current)
    return new is not None and old is not None and new > old


def signed_message(version, sums):
    """Что именно подписывается: версия и контрольные суммы всех файлов релиза."""
    return b"WhoKey release " + version.encode("ascii") + b"\n" + sums


def signature_ok(version, sums, signature_text, public_key=None):
    try:
        signature = base64.b64decode(signature_text.strip(), validate=True)
        key = Ed25519PublicKey.from_public_bytes(public_key or PUBLIC_KEY)
        key.verify(signature, signed_message(version, sums))
        return True
    except (InvalidSignature, ValueError, binascii.Error, UnicodeError):
        return False


def expected_hash(sums, name):
    """SHA-256 файла name из SHA256SUMS. Нет строки или их две — None."""
    found = []
    for line in sums.decode("ascii", "replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            found.append(parts[0])
    return found[0] if len(found) == 1 else None


def read_release(data, package=None):
    """Из ответа GitHub — (версия, {имя файла: адрес}) или None, если релиз не подходит."""
    package = package or asset_name()
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease") or not package:
        return None
    tag = data.get("tag_name")
    if not isinstance(tag, str) or parse_version(tag) is None or not tag.startswith("v"):
        return None
    prefix = DOWNLOAD_PREFIX + tag + "/"
    urls = {}
    for asset in data.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        name, url = asset.get("name"), asset.get("browser_download_url")
        if name in (package, SUMS_NAME, SIGNATURE_NAME) and url == prefix + name:
            urls[name] = url  # только файлы этого релиза этого репозитория
    if len(urls) != 3:
        return None  # старый релиз без подписи или нет файла для этой системы
    return tag[1:], urls


# --- установка ---

def supported():
    """Обновлять можно только собранную программу (не запуск из исходников)."""
    if not getattr(sys, "frozen", False) or asset_name() is None:
        return False
    if sys.platform == "darwin":
        return _current_app() is not None
    return True


def _current_app():
    """Mac: папка WhoKey.app, из которой запущена программа."""
    app = Path(sys.executable).resolve().parents[2]
    return app if app.suffix == ".app" else None


def _run(args, timeout=120):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        raise UpdateError(tr("Could not install the update ({step}).").format(step=Path(args[0]).name)) from error


# Скрипт-помощник (macOS): ждёт, пока WhoKey закроется, меняет программу на новую и запускает её.
# Если поменять не вышло — возвращает старую. Пути — аргументами, в текст скрипта ничего не подставляется.
MAC_SWAP = """#!/bin/sh
n=0
while kill -0 "$1" 2>/dev/null; do
    n=$((n + 1)); [ "$n" -gt 600 ] && exit 1
    sleep 0.1
done
old="$3.old"
rm -rf "$old"
if mv "$3" "$old"; then
    if mv "$2" "$3"; then rm -rf "$old"; else mv "$old" "$3"; fi
fi
"$4" "$3"
"""

# То же для Linux: install.sh из нового архива ставит программу на место старой, потом — запуск.
LINUX_SWAP = """#!/bin/sh
n=0
while kill -0 "$1" 2>/dev/null; do
    n=$((n + 1)); [ "$n" -gt 600 ] && exit 1
    sleep 0.1
done
WHOKEY_UPDATING=1 /bin/sh "$2" >/dev/null 2>&1
"$3" >/dev/null 2>&1 &
"""


def prepare_mac(dmg, version, work):
    """Достаёт WhoKey.app из образа рядом с установленной и проверяет её подпись и версию."""
    current = _current_app()
    if current is None:
        raise UpdateError(tr("WhoKey is not running from an installed app."))
    requirement = ""
    shown = _run(["/usr/bin/codesign", "-d", "-r-", str(current)])
    for line in (shown.stdout + shown.stderr).splitlines():
        if line.startswith("designated => "):
            requirement = line[len("designated => "):].strip()
    if "certificate leaf" not in requirement:
        raise UpdateError(tr("This copy of WhoKey has no permanent signature, so an update can't be checked. Install it from GitHub by hand."))
    mount = Path(work) / "mnt"
    mount.mkdir()
    _run(["/usr/bin/hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", str(mount), str(dmg)])
    staged = current.with_name(".WhoKey-update.app")
    try:
        source = mount / "WhoKey.app"
        if source.is_symlink() or not source.is_dir():
            raise UpdateError(tr("The downloaded update is damaged."))
        shutil.rmtree(staged, ignore_errors=True)
        _run(["/usr/bin/ditto", str(source), str(staged)], timeout=300)
    finally:
        subprocess.run(["/usr/bin/hdiutil", "detach", str(mount), "-force"], capture_output=True, timeout=60)
    try:
        # тот же сертификат, что у установленной программы, и никаких изменённых файлов
        _run(["/usr/bin/codesign", "--verify", "--deep", "--strict", "-R", "=" + requirement, str(staged)])
        with open(staged / "Contents" / "Info.plist", "rb") as plist:
            if plistlib.load(plist).get("CFBundleShortVersionString") != version:
                raise UpdateError(tr("The downloaded update is damaged."))
    except Exception:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    return staged, current


def extract_linux(archive, dest):
    """Распаковывает архив Linux, не выпуская ни один файл за пределы dest. Возвращает путь к install.sh."""
    dest = Path(dest)
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            parts = Path(member.name).parts
            if member.name.startswith("/") or ".." in parts or not parts or parts[0] != "WhoKey":
                raise UpdateError(tr("The downloaded update is damaged."))
            if not (member.isfile() or member.isdir() or member.issym()):
                raise UpdateError(tr("The downloaded update is damaged."))
            if member.issym():  # ссылка внутри архива — только на файл внутри той же папки
                target = os.path.normpath(os.path.join(str(dest), os.path.dirname(member.name), member.linkname))
                if os.path.isabs(member.linkname) or not target.startswith(str(dest / "WhoKey") + os.sep):
                    raise UpdateError(tr("The downloaded update is damaged."))
        tar.extractall(dest, members=members)
    install = dest / "WhoKey" / "install.sh"
    if not install.is_file():
        raise UpdateError(tr("The downloaded update is damaged."))
    return install


def _helper(work, text):
    script = Path(work) / "update.sh"
    script.write_text(text)
    return str(script)


def launch_installer(package, version, work, pid):
    """Готовит обновление и запускает помощника, который поставит его, когда WhoKey закроется.
    После этого WhoKey должен выйти сам. Не вышло — UpdateError, и ничего не поменялось."""
    if sys.platform == "darwin":
        staged, current = prepare_mac(package, version, work)
        command = ("/bin/sh", [_helper(work, MAC_SWAP), str(pid), str(staged), str(current), "/usr/bin/open"])
    elif sys.platform == "win32":
        # установщик Inno Setup без окон: сам закроет мост расширения, поставит и запустит WhoKey
        command = (str(package), ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH"])
    else:
        install = extract_linux(package, Path(work) / "unpacked")
        program = Path.home() / ".local" / "opt" / "WhoKey" / "WhoKey"
        command = ("/bin/sh", [_helper(work, LINUX_SWAP), str(pid), str(install), str(program)])
    if not QProcess.startDetached(*command):
        raise UpdateError(tr("Could not install the update ({step}).").format(step=Path(command[0]).name))


# --- сеть ---

class Updater(QObject):
    """Проверка и скачивание. Живёт всё время работы программы (app.Controller), а не в окне."""

    found = Signal(str)          # есть новая версия
    checked = Signal(str)        # итог проверки для «О программе»: "latest", "found" или "error"
    progress = Signal(int)       # скачано, %
    ready = Signal(str, str)     # (путь к проверенному установщику, версия)
    failed = Signal(str)         # не скачалось или не прошло проверку — текст для человека

    insecure_for_tests = False   # тесты гоняют всё через свой сервер на 127.0.0.1 без https

    def __init__(self, parent=None):
        super().__init__(parent)
        self.net = QNetworkAccessManager(self)
        self.version = None      # найденная новая версия
        self.urls = {}
        self.busy = False        # идёт проверка или скачивание
        self.work = None         # временная папка скачивания (только для владельца)
        self._reply = None

    # проверка

    def check_due(self):
        """Тихая проверка: если включена в настройках и прошли сутки с прошлой."""
        try:
            last = float(prefs.last_update_check())
        except (TypeError, ValueError):
            last = 0.0
        if prefs.update_check() and not (0 <= time.time() - last < CHECK_EVERY):
            self.check()

    def check(self):
        if self.busy:
            return
        self.busy = True
        prefs.set_value("last_update_check", time.time())
        self._get(API_URL, MAX_INFO, self._got_release, error=lambda: self._check_failed())

    def _check_failed(self):
        self.busy = False
        self.checked.emit("error")

    def _got_release(self, body):
        self.busy = False
        try:
            release = read_release(json.loads(body.decode("utf-8")))
        except ValueError:
            release = None
        if release is None or not is_newer(release[0]):
            self.checked.emit("found" if self.version else "latest")  # нет новее (или релиз без подписи)
            return
        self.version, self.urls = release
        self.checked.emit("found")
        self.found.emit(self.version)

    # скачивание

    def download(self):
        if self.busy or self.version is None:
            return
        self.busy = True
        self._cleanup()
        self.work = tempfile.mkdtemp(prefix="whokey-update-")  # права 700: только этот пользователь
        version, urls = self.version, dict(self.urls)
        package = asset_name()

        def got_sums(sums):
            self._get(urls[SIGNATURE_NAME], MAX_SMALL, lambda signature: got_signature(sums, signature))

        def got_signature(sums, signature):
            if not signature_ok(version, sums, signature.decode("ascii", "replace")):
                return self._fail(tr("The update is not signed by the WhoKey author. It was not installed."))
            want = expected_hash(sums, package)
            if want is None:
                return self._fail(tr("The downloaded update is damaged."))
            target = Path(self.work) / package
            self._get(urls[package], MAX_PACKAGE, lambda digest: got_package(target, want, digest), save_to=target)

        def got_package(target, want, digest):
            self.busy = False
            if digest != want:
                return self._fail(tr("The downloaded update is damaged."))
            self.ready.emit(str(target), version)

        self._get(urls[SUMS_NAME], MAX_SMALL, got_sums)

    def install(self, package, version, pid):
        launch_installer(package, version, self.work, pid)

    def _fail(self, message):
        self.busy = False
        self._cleanup()
        self.failed.emit(message)

    def _cleanup(self):
        if self.work:
            shutil.rmtree(self.work, ignore_errors=True)
            self.work = None

    def _get(self, url, limit, done, save_to=None, error=None):
        """Скачивает url (не больше limit байт). done получает тело ответа, а с save_to —
        SHA-256 сохранённого файла."""
        error = error or (lambda: self._fail(tr("Could not download the update. Check the internet connection.")))
        if not (url.startswith("https://") or self.insecure_for_tests):
            error()
            return
        request = QNetworkRequest(QUrl(url))
        # на https и только на https: GitHub отдаёт файлы через переадресацию на свой сервер
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.NoLessSafeRedirectPolicy)
        request.setHeader(QNetworkRequest.UserAgentHeader, "WhoKey")
        request.setRawHeader(b"Accept", b"application/vnd.github+json" if url == API_URL else b"application/octet-stream")
        request.setTransferTimeout(60000)
        reply = self.net.get(request)
        self._reply = reply
        state = {"size": 0, "body": bytearray(), "hash": hashlib.sha256(), "file": None, "over": False}
        if save_to is not None:
            state["file"] = open(save_to, "wb")

        def read():
            chunk = bytes(reply.readAll())
            state["size"] += len(chunk)
            if state["size"] > limit:
                state["over"] = True
                reply.abort()
                return
            if state["file"] is not None:
                state["file"].write(chunk)
                state["hash"].update(chunk)
            else:
                state["body"] += chunk

        def progress(received, total):
            if save_to is not None and total > 0:
                self.progress.emit(int(received * 100 / total))

        def finished():
            read()
            if state["file"] is not None:
                state["file"].close()
            failed = reply.error() != QNetworkReply.NoError or state["over"]
            reply.deleteLater()
            if self._reply is reply:
                self._reply = None
            if failed:
                error()
            elif save_to is not None:
                done(state["hash"].hexdigest())
            else:
                done(bytes(state["body"]))

        reply.readyRead.connect(read)
        reply.downloadProgress.connect(progress)
        reply.finished.connect(finished)
