"""Расширение браузера: мост, сервер внутри WhoKey и атаки из ревью безопасности.

Запуск: python -m unittest discover tests
Тесты с сокетом macOS и с каналом Windows идут каждый на своей системе
(Windows — на машине GitHub Actions). Настоящее хранилище,
настройки и сокет WhoKey не трогаются: всё во временных папках.
"""

import hashlib
import io
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEventLoop, QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

import bridge_host as H  # noqa: E402
import bridge_protocol as P  # noqa: E402
import gui.bridge as B  # noqa: E402
from gui.autolock import AutoLock  # noqa: E402
from vault import Vault  # noqa: E402

APP = QApplication.instance() or QApplication([])
MAC = sys.platform == "darwin"
WINDOWS = sys.platform == "win32"
PASSWORD = "Зелёный-Кит-Летит-2026!"


def make_server(answer=True, delay_ms=0):
    """Сервер с тестовым хранилищем; окно «разрешить?» отвечает само (через delay_ms)."""
    folder = Path(tempfile.mkdtemp())
    vault = Vault.create(folder / "v.dat", PASSWORD)
    vault.add("Почта", "egor@mail.ru", "PASS-mail", "", url="mail.ru")
    vault.add("Почта 2", "second@mail.ru", "PASS-mail-2", "", url="mail.ru")
    vault.add("GitHub", "egor", "PASS-github", "", url="github.com")
    dialogs = []

    def ask(parent, title, text):
        dialogs.append(text)
        if delay_ms:  # «человек думает» — свой цикл событий, как у настоящего окна
            loop = QEventLoop()
            QTimer.singleShot(delay_ms, loop.quit)
            loop.exec()
        return answer
    B.ask_yes = ask
    settings = QSettings(str(folder / "s.ini"), QSettings.IniFormat)
    return B.BridgeServer(vault, QMainWindow(), settings), vault, settings, dialogs


class Requests(unittest.TestCase):
    """Логика запросов сервера — без сокета, работает на любой системе."""

    def setUp(self):
        self.server, self.vault, self.settings, self.dialogs = make_server()
        self.key = self.server.handle({"type": "pair", "code": "4821"})["key"]

    def ask(self, **request):
        return self.server.handle({"key": self.key, **request})

    def test_pairing_shows_code_and_needs_it(self):
        self.assertIn("4821", self.dialogs[0])
        self.assertEqual(self.server.handle({"type": "pair"})["status"], "error")
        self.assertEqual(self.server.handle({"type": "pair", "code": "12a4"})["status"], "error")

    def test_without_key_nothing(self):
        for key in (None, "", "угадал"):
            r = self.server.handle({"type": "logins", "url": "https://mail.ru", "key": key})
            self.assertEqual(r, {"status": "pair_required"})

    def test_key_injected_into_settings_does_not_work(self):
        # ревью: дописать свой отпечаток в открытые настройки — получить пароли без диалога
        self.settings.setValue("bridge/keys", [hashlib.sha256(b"my-own-key").hexdigest()])
        r = self.server.handle({"type": "fill", "url": "https://mail.ru", "key": "my-own-key",
                                "index": 0, "login": "egor@mail.ru"})
        self.assertEqual(r, {"status": "pair_required"})

    def test_key_lives_in_encrypted_vault(self):
        again = Vault.open(self.vault.path, PASSWORD)
        self.assertEqual(again.bridge_keys, [hashlib.sha256(self.key.encode()).hexdigest()])
        self.assertNotIn(again.bridge_keys[0], self.vault.path.read_text())

    def test_logins_without_passwords(self):
        r = self.ask(type="logins", url="https://e.mail.ru")
        self.assertEqual([i["login"] for i in r["items"]], ["egor@mail.ru", "second@mail.ru"])
        self.assertNotIn("PASS", json.dumps(r))

    def test_fill_right_entry(self):
        r = self.ask(type="fill", url="https://e.mail.ru", index=1, login="second@mail.ru")
        self.assertEqual(r, {"status": "ok", "login": "second@mail.ru", "password": "PASS-mail-2"})

    def test_phishing_and_wrong_site(self):
        for url in ("https://mail.ru.evil.com", "https://evilmail.ru", "https://github.com.mail.ru.xyz"):
            self.assertEqual(self.ask(type="logins", url=url), {"status": "ok", "items": []})
        self.assertEqual(self.ask(type="fill", url="https://mail.ru.evil.com", index=0, login="egor@mail.ru")["status"],
                         "not_found")
        self.assertEqual(self.ask(type="fill", url="https://github.com", index=0, login="egor@mail.ru")["status"],
                         "not_found")
        self.assertEqual(self.ask(type="logins", url="http://mail.ru")["status"], "bad_page")

    def test_strange_requests(self):
        for request in ({"type": "fill", "url": "https://mail.ru", "index": "0", "login": "egor@mail.ru"},
                        {"type": "fill", "url": "https://mail.ru", "index": 99, "login": "x"},
                        {"type": "fill", "url": ["x"]}, {"type": "???", "url": "https://mail.ru"}):
            self.assertIn(self.ask(**request)["status"], ("not_found", "bad_page", "error"))

    def test_rate_limit(self):
        statuses = [self.ask(type="fill", url="https://mail.ru", index=0, login="egor@mail.ru")["status"]
                    for _ in range(12)]
        self.assertEqual(statuses.count("ok"), B.RATE_LIMIT["fill"])
        self.assertIn("busy", statuses)

    def test_no_dialog_flood_after_denial(self):
        server, _, _, dialogs = make_server(answer=False)
        self.assertEqual(server.handle({"type": "pair", "code": "1111"})["status"], "denied")
        self.assertEqual(server.handle({"type": "pair", "code": "2222"})["status"], "denied")
        self.assertEqual(len(dialogs), 1)

    def test_disconnect_extension(self):
        self.server.forget_all()
        self.assertEqual(self.ask(type="logins", url="https://mail.ru"), {"status": "pair_required"})


@unittest.skipUnless(MAC, "сокет и проверка собеседника — пока только macOS")
class Socket(unittest.TestCase):
    """Настоящий сокет: проверка собеседника, отказ в обслуживании, «медленный человек»."""

    def setUp(self):
        self.address = os.path.join(tempfile.mkdtemp(dir="/tmp"), "s.sock")  # коротко: путь сокета ≤ 104
        self._real = P.socket_address
        P.socket_address = lambda: self.address

    def tearDown(self):
        P.socket_address = self._real

    def pump(self, seconds):
        """Даёт серверу поработать (он в этом же процессе)."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            QCoreApplication.processEvents(QEventLoop.AllEvents, 50)

    def request(self, raw, wait=3.0):
        conn = socket.socket(socket.AF_UNIX)
        conn.setblocking(False)
        conn.connect(self.address)
        while raw:  # сервер в этом же процессе — отправляем порциями, давая ему читать
            try:
                raw = raw[conn.send(raw):]
            except BlockingIOError:
                self.pump(0.05)
        data, end = b"", time.monotonic() + wait
        while b"\n" not in data and time.monotonic() < end:
            self.pump(0.05)
            try:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            except BlockingIOError:
                pass
        conn.close()
        return json.loads(data.split(b"\n")[0]) if data.strip() else None

    def test_own_program_is_trusted_and_others_are_not(self):
        server, *_ = make_server()
        self.assertTrue(server.start())
        self.assertEqual(self.request(b'{"type": "ping"}\n'), {"status": "ok"})
        # чужая программа (nc) получает только «не доверяю»
        with subprocess.Popen(["nc", "-U", self.address], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as nc:
            nc.stdin.write(b'{"type": "ping"}\n')
            nc.stdin.flush()
            self.pump(1.0)
            nc.stdin.close()
            out = nc.stdout.read()
        self.assertIn(b"untrusted", out)
        server.stop()

    def test_deep_json_and_many_connections(self):
        server, *_ = make_server()
        server.start()
        self.assertEqual(self.request(b"[" * 30000 + b"\n"), {"status": "error"})
        conns = []
        for _ in range(100):
            try:
                c = socket.socket(socket.AF_UNIX)
                c.connect(self.address)
                c.sendall(b'{"type":')
                conns.append(c)
            except OSError:
                break
        self.pump(1.0)
        for c in conns:
            c.close()
        self.pump(2.5)
        self.assertEqual(self.request(b'{"type": "ping"}\n'), {"status": "ok"})
        server.stop()

    def test_slow_human_over_pair_dialog(self):
        # ревью-исправление «тайм-аут 5 с» роняло WhoKey, если человек думал дольше
        server, *_ = make_server(delay_ms=B.REQUEST_TIMEOUT_MS + 1500)
        server.start()
        r = self.request(b'{"type": "pair", "code": "4821"}\n', wait=10)
        self.assertEqual(r["status"], "ok")
        server.stop()

    def test_fake_whokey_gets_nothing(self):
        # ревью: пока WhoKey закрыт, чужая программа слушает его сокет
        with subprocess.Popen(["nc", "-lU", self.address], stdout=subprocess.PIPE) as rogue:
            for _ in range(50):
                if os.path.exists(self.address):
                    break
                time.sleep(0.1)
            with self.assertRaises(P.PeerError):
                P.ask_app({"type": "fill", "key": "REAL-KEY", "url": "https://mail.ru"}, timeout=3)
            rogue.terminate()
            self.assertNotIn(b"REAL-KEY", rogue.stdout.read())


class Host(unittest.TestCase):
    def test_bad_message_from_browser(self):
        messages = struct.pack("<I", 5) + b"nojso" + struct.pack("<I", 2) + b"[]"
        out = io.BytesIO()
        launched = []
        real_launch, P.launch_app = P.launch_app, lambda: launched.append(1)
        real_stdin, real_stdout = sys.stdin, sys.stdout
        sys.stdin = types.SimpleNamespace(buffer=io.BufferedReader(io.BytesIO(messages)))
        sys.stdout = types.SimpleNamespace(buffer=out)  # мост пишет только в sys.stdout.buffer
        try:
            H.main()
        finally:
            sys.stdin, sys.stdout, P.launch_app = real_stdin, real_stdout, real_launch
        data = out.getvalue()
        replies = []
        while data:
            size = struct.unpack("<I", data[:4])[0]
            replies.append(json.loads(data[4:4 + size]))
            data = data[4 + size:]
        self.assertEqual(replies, [{"status": "error"}, {"status": "error"}])
        self.assertEqual(launched, [])  # мусор никуда не пересылается и WhoKey не открывает

    def test_timeout_does_not_relaunch(self):
        launched = []
        real_ask, real_launch = P.ask_app, P.launch_app
        P.ask_app = lambda message, timeout=120: (_ for _ in ()).throw(socket.timeout("timed out"))
        P.launch_app = lambda: launched.append(1)
        try:
            r = H.forward({"type": "pair", "code": "1234"}, io.BytesIO(), io.BytesIO(), "x")
        finally:
            P.ask_app, P.launch_app = real_ask, real_launch
        self.assertEqual((r, launched), ({"status": "timeout"}, []))


@unittest.skipUnless(MAC, "описание моста в браузерах — пока только macOS (и ссылки на Windows требуют особых прав)")
class NativeHost(unittest.TestCase):
    def test_symlink_and_temporary_paths(self):
        home = Path(tempfile.mkdtemp())
        folder = home / "Library/Application Support/Google/Chrome/NativeMessagingHosts"
        folder.mkdir(parents=True)
        victim = home / "victim.txt"
        victim.write_text("не трогать")
        (folder / f"{P.HOST_NAME}.json").symlink_to(victim)
        real_home = Path.home
        Path.home = classmethod(lambda cls: home)
        try:
            self.assertEqual(P.install_native_host("/Users/x/Applications/WhoKey.app/Contents/MacOS/WhoKey"),
                             ["Google/Chrome"])
            self.assertEqual(P.install_native_host("/Volumes/WhoKey Installer/WhoKey.app/Contents/MacOS/WhoKey"), [])
        finally:
            Path.home = real_home
        self.assertEqual(victim.read_text(), "не трогать")
        manifest = json.loads((folder / f"{P.HOST_NAME}.json").read_text())
        self.assertEqual(manifest["allowed_origins"], [f"chrome-extension://{P.EXTENSION_ID}/"])


def pump(seconds):
    """Даёт серверу поработать (он в этом же процессе)."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 50)


@unittest.skipUnless(WINDOWS, "именованный канал — только Windows")
class WindowsPipe(unittest.TestCase):
    """Настоящий канал Windows: проверка собеседника в обе стороны, тайм-ауты, отказ в обслуживании."""

    def setUp(self):
        self.name = "whokey-test-" + os.urandom(6).hex()
        self._real = P.socket_address
        P.socket_address = lambda: self.name

    def tearDown(self):
        P.socket_address = self._real

    def request(self, raw, wait=3.0):
        pipe = P.WinPipe(self.name)
        # пишем из отдельного потока: сервер в этом же процессе и читает, только пока мы его «качаем»
        writer = threading.Thread(target=pipe.write, args=(raw,), daemon=True)
        writer.start()
        data, end = b"", time.monotonic() + wait
        try:
            while b"\n" not in data and time.monotonic() < end:
                pump(0.05)
                try:
                    data += pipe.read_available()
                except OSError:
                    break
        finally:
            pipe.close()
        return json.loads(data.split(b"\n")[0]) if data.strip() else None

    def powershell(self, script):
        return subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_own_program_is_trusted_and_others_are_not(self):
        server, *_ = make_server()
        self.assertTrue(server.start())
        self.assertEqual(self.request(b'{"type": "ping"}\n'), {"status": "ok"})
        # чужая программа (PowerShell) получает только «не доверяю»
        client = self.powershell(
            f"$p = New-Object System.IO.Pipes.NamedPipeClientStream('.', '{self.name}', 'InOut'); "
            "$p.Connect(5000); $w = New-Object System.IO.StreamWriter($p); $w.AutoFlush = $true; "
            "$w.WriteLine('{\"type\": \"ping\"}'); $r = New-Object System.IO.StreamReader($p); "
            "Write-Output $r.ReadLine()")
        end = time.monotonic() + 20
        while client.poll() is None and time.monotonic() < end:
            pump(0.1)
        out = client.communicate(timeout=5)[0]
        self.assertIn(b"untrusted", out)
        self.assertNotIn(b"ok", out.replace(b"untrusted", b""))
        server.stop()

    def test_fake_whokey_gets_nothing(self):
        # пока WhoKey закрыт, чужая программа открыла канал с его именем
        rogue = self.powershell(
            f"$s = New-Object System.IO.Pipes.NamedPipeServerStream('{self.name}', 'InOut'); "
            "$s.WaitForConnection(); $r = New-Object System.IO.StreamReader($s); "
            "Write-Output ('got: ' + $r.ReadLine())")
        path = "\\\\.\\pipe\\" + self.name
        for _ in range(100):  # ждём, пока канал появится (не подключаясь к нему)
            if P._k32.WaitNamedPipeW(path, 100):
                break
            time.sleep(0.1)
        with self.assertRaises(P.PeerError):
            P.ask_app({"type": "fill", "key": "REAL-KEY", "url": "https://mail.ru"}, timeout=3)
        out = rogue.communicate(timeout=20)[0]
        self.assertNotIn(b"REAL-KEY", out)

    def test_slow_human_over_pair_dialog(self):
        server, *_ = make_server(delay_ms=B.REQUEST_TIMEOUT_MS + 1500)
        server.start()
        r = self.request(b'{"type": "pair", "code": "4821"}\n', wait=10)
        self.assertEqual(r["status"], "ok")
        server.stop()

    def test_deep_json_and_many_connections(self):
        server, *_ = make_server()
        server.start()
        self.assertEqual(self.request(b"[" * 30000 + b"\n"), {"status": "error"})
        pipes = []
        for _ in range(30):
            try:
                pipes.append(P.WinPipe(self.name))
            except OSError:
                break
            pump(0.02)
        pump(1.0)
        for pipe in pipes:
            pipe.close()
        pump(2.5)
        self.assertEqual(self.request(b'{"type": "ping"}\n'), {"status": "ok"})
        server.stop()

    def test_browser_left_is_noticed(self):
        # мост ждёт мастер-пароль, а браузер закрыл соединение — мост не должен висеть 90 секунд
        read_end, write_end = os.pipe()
        stdin = os.fdopen(read_end, "rb")
        start = time.monotonic()
        self.assertFalse(H.browser_left(stdin, 0.5))  # браузер ещё на связи
        os.close(write_end)
        self.assertTrue(H.browser_left(stdin, 5))
        self.assertLess(time.monotonic() - start, 3)
        stdin.close()

    def test_registry_and_temporary_paths(self):
        import winreg
        exe = Path(sys.executable)
        try:
            done = P.install_native_host(exe)
            self.assertIn("Google\\Chrome", done)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                f"Software\\Google\\Chrome\\NativeMessagingHosts\\{P.HOST_NAME}") as key:
                manifest_path = winreg.QueryValueEx(key, "")[0]
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["path"], str(exe))
            self.assertEqual(manifest["allowed_origins"], [f"chrome-extension://{P.EXTENSION_ID}/"])
            self.assertEqual(P.install_native_host(Path(tempfile.gettempdir()) / "WhoKey.exe"), [])
        finally:
            for browser in P.WINDOWS_BROWSER_KEYS:
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
                                     f"Software\\{browser}\\NativeMessagingHosts\\{P.HOST_NAME}")
                except OSError:
                    pass


class Autolock(unittest.TestCase):
    def test_sleep_detected(self):
        events = []
        lock = AutoLock()
        lock.lock.connect(lambda: events.append(1))
        lock._clocks = (time.time() - 3, time.monotonic() - 3)
        lock._check()
        self.assertEqual(events, [])
        lock._clocks = (time.time() - 100, time.monotonic() - 1)
        lock._check()
        self.assertEqual(events, [1])


if __name__ == "__main__":
    unittest.main()
