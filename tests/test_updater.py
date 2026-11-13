"""Обновление по кнопке: подпись, разбор релиза, скачивание, распаковка, скрипты-помощники, кнопка.

Сеть — только свой сервер на 127.0.0.1 (настоящий GitHub в тестах не трогается),
ключ подписи — тестовый, настройки — во временном файле.
"""

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from gui import prefs, updater as U  # noqa: E402

prefs.use_file(Path(tempfile.mkdtemp()) / "p.ini")

KEY = Ed25519PrivateKey.generate()
PUBLIC = KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
PACKAGE = U.asset_name() or "WhoKey-linux-x86_64.tar.gz"


def sign(version, sums, key=KEY):
    return base64.b64encode(key.sign(U.signed_message(version, sums))).decode()


def sums_for(files):
    return "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in files.items()).encode()


class Offline(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(U.parse_version("v1.10.0"), (1, 10, 0))
        self.assertEqual(U.parse_version("1.9.0"), (1, 9, 0))
        for bad in ("", "v1.9", "1.9.0-beta", "v1.9.0\n", "../1.2.3", None):
            self.assertIsNone(U.parse_version(bad), bad)
        self.assertTrue(U.is_newer("1.10.0", "1.9.0"))  # не по буквам: 10 > 9
        self.assertFalse(U.is_newer("1.9.0", "1.9.0"))
        self.assertFalse(U.is_newer("1.8.9", "1.9.0"))

    def test_signature(self):
        sums = b"abc  WhoKey.Installer.dmg\n"
        good = sign("1.10.0", sums)
        self.assertTrue(U.signature_ok("1.10.0", sums, good, PUBLIC))
        self.assertFalse(U.signature_ok("1.10.0", sums + b"x", good, PUBLIC))   # суммы подменили
        self.assertFalse(U.signature_ok("1.11.0", sums, good, PUBLIC))          # старый релиз под новым номером
        self.assertFalse(U.signature_ok("1.10.0", sums, good))                  # чужой ключ — не ключ автора
        self.assertFalse(U.signature_ok("1.10.0", sums, sign("1.10.0", sums, Ed25519PrivateKey.generate()), PUBLIC))
        for junk in ("", "не base64", "AAAA"):
            self.assertFalse(U.signature_ok("1.10.0", sums, junk, PUBLIC))

    def test_expected_hash(self):
        digest = "a" * 64
        self.assertEqual(U.expected_hash(f"{digest}  WhoKey.Installer.dmg\n".encode(), "WhoKey.Installer.dmg"), digest)
        self.assertEqual(U.expected_hash(f"{digest} *x.exe\n".encode(), "x.exe"), digest)
        self.assertIsNone(U.expected_hash(f"{digest}  x\n{'b' * 64}  x\n".encode(), "x"))  # две строки — не верим
        self.assertIsNone(U.expected_hash(b"zz  x\n", "x"))
        self.assertIsNone(U.expected_hash(f"{digest}  y\n".encode(), "x"))

    def test_release_is_taken_only_from_this_repository(self):
        tag = "v1.10.0"

        def release(**changes):
            assets = [{"name": n, "browser_download_url": U.DOWNLOAD_PREFIX + tag + "/" + n}
                      for n in (PACKAGE, U.SUMS_NAME, U.SIGNATURE_NAME)]
            data = {"tag_name": tag, "assets": assets}
            data.update(changes)
            return data

        version, urls = U.read_release(release(), PACKAGE)
        self.assertEqual(version, "1.10.0")
        self.assertEqual(set(urls), {PACKAGE, U.SUMS_NAME, U.SIGNATURE_NAME})
        foreign = release()
        foreign["assets"][0]["browser_download_url"] = "https://evil.example/" + PACKAGE
        self.assertIsNone(U.read_release(foreign, PACKAGE))
        other_tag = release()
        other_tag["assets"][0]["browser_download_url"] = U.DOWNLOAD_PREFIX + "v1.0.0/" + PACKAGE
        self.assertIsNone(U.read_release(other_tag, PACKAGE))
        unsigned = release()
        unsigned["assets"] = unsigned["assets"][:2]
        self.assertIsNone(U.read_release(unsigned, PACKAGE))  # 1.9.0 и старше — без подписи
        self.assertIsNone(U.read_release(release(prerelease=True), PACKAGE))
        self.assertIsNone(U.read_release(release(tag_name="1.10.0"), PACKAGE))
        self.assertIsNone(U.read_release(["не словарь"], PACKAGE))

    def test_not_supported_when_running_from_source(self):
        self.assertFalse(U.supported())  # тесты — не собранная программа: в сеть они не ходят

    def test_public_key_is_real(self):
        self.assertEqual(len(U.PUBLIC_KEY), 32)
        self.assertNotEqual(U.PUBLIC_KEY, bytes(32))


def make_tar(entries):
    """entries: [(имя, содержимое | ("link", цель) | ("hard", цель))] → байты .tar.gz"""
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as tar:
        for name, content in entries:
            info = tarfile.TarInfo(name)
            if isinstance(content, tuple):
                info.type = tarfile.SYMTYPE if content[0] == "link" else tarfile.LNKTYPE
                info.linkname = content[1]
                tar.addfile(info)
            else:
                info.size = len(content)
                info.mode = 0o755
                tar.addfile(info, io.BytesIO(content))
    return data.getvalue()


class LinuxArchive(unittest.TestCase):
    def extract(self, entries):
        folder = Path(tempfile.mkdtemp())
        archive = folder / "a.tar.gz"
        archive.write_bytes(make_tar(entries))
        return U.extract_linux(archive, folder / "out"), folder

    def test_normal_archive(self):
        install, folder = self.extract([("WhoKey/install.sh", b"#!/bin/sh\n"), ("WhoKey/WhoKey", b"x"),
                                        ("WhoKey/_internal/lib.so", b"y"), ("WhoKey/lib.so", ("link", "_internal/lib.so"))])
        self.assertEqual(install, folder / "out" / "WhoKey" / "install.sh")

    def test_files_cannot_escape(self):
        for entries in ([("WhoKey/install.sh", b""), ("WhoKey/../../evil", b"x")],
                        [("WhoKey/install.sh", b""), ("/tmp/evil", b"x")],
                        [("WhoKey/install.sh", b""), ("Other/evil", b"x")],
                        [("WhoKey/install.sh", b""), ("WhoKey/l", ("link", "../../../etc/passwd"))],
                        [("WhoKey/install.sh", b""), ("WhoKey/l", ("link", "/etc/passwd"))],
                        [("WhoKey/install.sh", b""), ("WhoKey/h", ("hard", "/etc/passwd"))],
                        [("WhoKey/WhoKey", b"x")]):  # нет install.sh
            with self.assertRaises(U.UpdateError, msg=str(entries)):
                self.extract(entries)


@unittest.skipIf(sys.platform == "win32", "скрипты-помощники — для macOS и Linux")
class Helpers(unittest.TestCase):
    def finished_pid(self):
        process = subprocess.Popen(["/bin/sh", "-c", "exit 0"])
        process.wait()
        return str(process.pid)

    def test_mac_swap_replaces_the_app_and_starts_it(self):
        folder = Path(tempfile.mkdtemp())
        app, new = folder / "WhoKey.app", folder / ".WhoKey-update.app"
        (app / "old").mkdir(parents=True)
        (new / "new").mkdir(parents=True)
        marker = folder / "started"
        launcher = folder / "open.sh"
        launcher.write_text(f'#!/bin/sh\necho "$1" > "{marker}"\n')
        launcher.chmod(0o755)
        script = folder / "swap.sh"
        script.write_text(U.MAC_SWAP)
        subprocess.run(["/bin/sh", str(script), self.finished_pid(), str(new), str(app), str(launcher)], check=True, timeout=30)
        self.assertTrue((app / "new").is_dir())
        self.assertFalse(new.exists())
        self.assertFalse((folder / "WhoKey.app.old").exists())
        self.assertEqual(marker.read_text().strip(), str(app))

    def test_mac_swap_waits_for_whokey_to_close(self):
        folder = Path(tempfile.mkdtemp())
        app, new = folder / "WhoKey.app", folder / ".WhoKey-update.app"
        app.mkdir()
        (new / "new").mkdir(parents=True)
        running = subprocess.Popen(["/bin/sleep", "1"])
        # закрывшийся процесс должен убрать его родитель (у WhoKey это система) — иначе «зомби» живёт вечно
        threading.Thread(target=running.wait, daemon=True).start()
        script = folder / "swap.sh"
        script.write_text(U.MAC_SWAP)
        started = time.monotonic()
        subprocess.run(["/bin/sh", str(script), str(running.pid), str(new), str(app), "/usr/bin/true"], check=True, timeout=30)
        self.assertGreater(time.monotonic() - started, 0.5)
        self.assertTrue((app / "new").is_dir())

    def test_linux_swap_runs_install_then_starts_the_program(self):
        folder = Path(tempfile.mkdtemp())
        log = folder / "log"
        install = folder / "install.sh"
        install.write_text(f'echo "install $WHOKEY_UPDATING" >> "{log}"\n')
        program = folder / "WhoKey"
        program.write_text(f'#!/bin/sh\necho started >> "{log}"\n')
        program.chmod(0o755)
        script = folder / "swap.sh"
        script.write_text(U.LINUX_SWAP)
        subprocess.run(["/bin/sh", str(script), self.finished_pid(), str(install), str(program)], check=True, timeout=30)
        for _ in range(50):  # программа запускается в фоне
            if "started" in log.read_text():
                break
            time.sleep(0.05)
        self.assertEqual(log.read_text().split("\n")[:2], ["install 1", "started"])


KEEP = []


class FakeGitHub:
    """Свой «GitHub» на 127.0.0.1: ответ о релизе и файлы релиза."""

    def __init__(self, files, tag="v99.0.0", tamper=None):
        self.files = files
        self.tag = tag
        self.tamper = tamper or {}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == "/api":
                    assets = [{"name": n, "browser_download_url": U.DOWNLOAD_PREFIX + owner.tag + "/" + n} for n in owner.files]
                    body = json.dumps({"tag_name": owner.tag, "assets": assets}).encode()
                elif self.path.startswith("/dl/" + owner.tag + "/"):
                    name = self.path.rsplit("/", 1)[1]
                    body = owner.tamper.get(name, owner.files.get(name))
                    if body is None:
                        self.send_error(404)
                        return
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Download(unittest.TestCase):
    def setUp(self):
        self.package = b"WhoKey " * 50000
        sums = sums_for({PACKAGE: self.package, "other.zip": b"z"})
        self.files = {PACKAGE: self.package, U.SUMS_NAME: sums, U.SIGNATURE_NAME: sign("99.0.0", sums).encode()}

    def start(self, **kwargs):
        github = FakeGitHub(self.files, **kwargs)
        self.addCleanup(github.close)
        patches = [mock.patch.object(U, "API_URL", github.base + "/api"),
                   mock.patch.object(U, "DOWNLOAD_PREFIX", github.base + "/dl/"),
                   mock.patch.object(U, "PUBLIC_KEY", PUBLIC),
                   mock.patch.object(U, "asset_name", lambda: PACKAGE),
                   mock.patch.object(U.Updater, "insecure_for_tests", True)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        updater = U.Updater()
        KEEP.append(updater)  # как в программе: живёт до конца (Qt не удаляет его посреди событий сети)
        self.addCleanup(updater._cleanup)
        self.events = []
        for name in ("found", "checked", "ready", "failed"):
            getattr(updater, name).connect(lambda *args, n=name: self.events.append((n,) + args))
        return updater

    def wait(self, kinds, seconds=20):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            QCoreApplication.processEvents()
            if any(event[0] in kinds for event in self.events):
                return
            time.sleep(0.01)
        self.fail(f"не дождался {kinds}: {self.events}")

    def test_finds_downloads_and_checks_a_new_version(self):
        updater = self.start()
        updater.check()
        self.wait({"found"})
        self.assertIn(("found", "99.0.0"), self.events)
        self.assertGreater(float(prefs.last_update_check()), 0)
        updater.download()
        self.wait({"ready", "failed"})
        ready = [event for event in self.events if event[0] == "ready"]
        self.assertTrue(ready, self.events)
        path = Path(ready[0][1])
        self.assertEqual(path.read_bytes(), self.package)
        if sys.platform != "win32":  # на Windows временная папка и так у каждого пользователя своя
            self.assertEqual(oct(Path(updater.work).stat().st_mode & 0o777), oct(0o700))  # только для владельца

    def test_same_version_is_not_offered(self):
        updater = self.start(tag="v" + U.VERSION)
        self.files[U.SIGNATURE_NAME] = sign(U.VERSION, self.files[U.SUMS_NAME]).encode()
        updater.check()
        self.wait({"checked"})
        self.assertIn(("checked", "latest"), self.events)
        self.assertIsNone(updater.version)

    def test_replaced_package_is_not_installed(self):
        updater = self.start(tamper={PACKAGE: b"evil" * 1000})
        updater.check()
        self.wait({"found"})
        updater.download()
        self.wait({"ready", "failed"})
        self.assertEqual([e[0] for e in self.events if e[0] in ("ready", "failed")], ["failed"])
        self.assertIsNone(updater.work)  # скачанное удалено

    def test_foreign_signature_is_not_accepted(self):
        sums = self.files[U.SUMS_NAME]
        updater = self.start(tamper={U.SIGNATURE_NAME: sign("99.0.0", sums, Ed25519PrivateKey.generate()).encode()})
        updater.check()
        self.wait({"found"})
        updater.download()
        self.wait({"ready", "failed"})
        failed = [e for e in self.events if e[0] == "failed"]
        self.assertTrue(failed and "signed" in failed[0][1] or "подпис" in failed[0][1], self.events)

    def test_too_big_answer_is_cut_off(self):
        updater = self.start()
        with mock.patch.object(U, "MAX_INFO", 10):
            updater.check()
            self.wait({"checked"})
        self.assertIn(("checked", "error"), self.events)
        self.assertIsNone(updater.version)

    def test_github_error(self):
        updater = self.start()
        with mock.patch.object(U, "API_URL", U.API_URL.replace("/api", "/missing")):  # сервер отвечает 404
            updater.check()
            self.wait({"checked"})
        self.assertIn(("checked", "error"), self.events)
        self.assertFalse(updater.busy)

    def test_only_https_without_the_test_switch(self):
        updater = self.start()
        with mock.patch.object(U.Updater, "insecure_for_tests", False):
            updater.check()
            self.wait({"checked"})
        self.assertIn(("checked", "error"), self.events)

    def test_quiet_check_once_a_day_and_can_be_turned_off(self):
        updater = self.start()
        with mock.patch.object(updater, "check") as check:
            prefs.set_value("last_update_check", time.time())
            updater.check_due()
            check.assert_not_called()
            prefs.set_value("last_update_check", time.time() - U.CHECK_EVERY - 1)
            updater.check_due()
            check.assert_called_once()
            prefs.set_value("update_check", False)
            self.addCleanup(prefs.set_value, "update_check", True)
            updater.check_due()
            check.assert_called_once()


class Button(unittest.TestCase):
    def setUp(self):
        from gui import main_window as MW
        from gui.secure_clipboard import SecureClipboard
        from vault import Vault
        folder = Path(tempfile.mkdtemp())
        self.vault = Vault.create(folder / "v.dat", "Зелёный-Кит-Летит-2026!")
        self.window = MW.MainWindow(self.vault, SecureClipboard())
        self.window.show()
        self.addCleanup(self.window.close)

    def test_button_appears_only_when_there_is_an_update(self):
        w = self.window
        self.assertFalse(w.update_button.isVisible())
        w.offer_update("1.10.0")
        self.assertTrue(w.update_button.isVisible())
        self.assertIn("1.10.0", w.update_button.text())
        asked = []
        w.update_requested.connect(lambda: asked.append(1))
        w.update_button.click()
        self.assertEqual(asked, [1])
        self.assertFalse(w.update_button.isEnabled())  # второй раз не нажать, пока качается
        w.update_progress(42)
        self.assertIn("42", w.update_button.text())
        w.update_failed("нет сети")
        self.assertTrue(w.update_button.isEnabled())
        self.assertIn("нет сети", w.statusBar().currentMessage())
        w.offer_restart("1.10.0")
        self.assertTrue(w.update_button.isEnabled())

    def test_about_shows_the_check_result(self):
        from PySide6.QtCore import QObject, Signal
        from gui.dialogs import AboutDialog

        class FakeUpdater(QObject):
            checked = Signal(str)
            version = None
            busy = False

            def check(self):
                self.version = "1.10.0"
                self.checked.emit("found")

        fake = FakeUpdater()
        about = AboutDialog(self.window, fake)
        about.check_button.click()
        self.assertIn("1.10.0", about.update_status.text())
        fake.checked.emit("latest")
        self.assertNotIn("1.10.0", about.update_status.text())
        about.done(0)
        fake.checked.emit("error")  # окно закрыто — не падает
        self.assertIn("Updates by button", AboutDialog(self.window).update_status.text() + "Updates by button")


if __name__ == "__main__":
    unittest.main()
