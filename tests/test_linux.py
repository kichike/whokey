"""Linux: проверка собеседника через /proc, блокировка экрана, описание моста, вторая копия, установка."""

import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

LINUX = sys.platform.startswith("linux")


@unittest.skipUnless(LINUX, "только Linux")
class Peer(unittest.TestCase):
    def test_other_user_is_not_trusted(self):
        import bridge_protocol as P
        fake = mock.Mock()
        fake.getsockopt.return_value = struct.pack("3i", os.getpid(), os.getuid() + 1, os.getgid())
        self.assertIsNone(P.peer_program(fake))
        self.assertFalse(P.trusted_peer(fake))

    def test_broken_socket_is_not_trusted(self):
        import bridge_protocol as P
        fake = mock.Mock()
        fake.getsockopt.side_effect = OSError
        self.assertFalse(P.trusted_peer(fake))

    def test_own_process_over_a_real_socket(self):
        import bridge_protocol as P
        left, right = socket.socketpair()
        with left, right:
            self.assertEqual(P.peer_program(left), P.own_program())
            self.assertTrue(P.trusted_peer(left))

    def test_other_program_and_replaced_program(self):
        import bridge_protocol as P
        folder = Path(tempfile.mkdtemp(dir="/tmp"))
        program = folder / "other"
        shutil.copy("/bin/sleep", program)
        process = subprocess.Popen([str(program), "30"])
        try:
            time.sleep(0.2)
            self.assertEqual(P._program_of(process.pid), str(program))
            self.assertNotEqual(P._program_of(process.pid), P.own_program())
            program.unlink()  # файл заменили: путь уже не тот, что был, совпасть не может
            self.assertTrue(P._program_of(process.pid).endswith(" (deleted)"))
        finally:
            process.kill()
            process.wait()

    def test_gone_process(self):
        import bridge_protocol as P
        self.assertIsNone(P._program_of(2 ** 22 + 1))


@unittest.skipUnless(LINUX, "только Linux")
class Addresses(unittest.TestCase):
    def test_long_path_goes_to_the_private_runtime_folder(self):
        import bridge_protocol as P
        with mock.patch.object(P, "app_data_dir", lambda: Path("/x" * 60)), \
                mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": "/run/user/1000"}):
            self.assertTrue(P.socket_address().startswith("/run/user/1000/"))
            self.assertNotEqual(P.socket_address(), P.instance_address())

    def test_without_runtime_folder_the_socket_is_in_a_private_temp_folder(self):
        import bridge_protocol as P
        temp = tempfile.mkdtemp()
        env = {k: v for k, v in os.environ.items() if k != "XDG_RUNTIME_DIR"}
        with mock.patch.object(P, "app_data_dir", lambda: Path("/x" * 60)), \
                mock.patch.dict(os.environ, env, clear=True), mock.patch.object(P.tempfile, "gettempdir", lambda: temp):
            address = P.socket_address()
        folder = Path(address).parent
        self.assertEqual(folder, Path(temp) / f"whokey-{os.getuid()}")
        self.assertEqual(folder.stat().st_mode & 0o777, 0o700)

    def test_taken_temp_folder_name_is_skipped(self):
        import bridge_protocol as P
        temp = tempfile.mkdtemp()
        elsewhere = tempfile.mkdtemp()
        os.symlink(elsewhere, os.path.join(temp, f"whokey-{os.getuid()}"))  # имя занято ссылкой
        self.assertEqual(P._private_temp_folder(temp), os.path.join(temp, f"whokey-{os.getuid()}-1"))

    def test_config_folder_and_temporary_paths(self):
        import bridge_protocol as P
        config = Path(tempfile.mkdtemp())
        (config / "chromium").mkdir()
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(config)}):
            self.assertEqual(P.install_native_host("/home/x/.local/opt/WhoKey/WhoKey"), ["chromium"])
            for temporary in ("/tmp/WhoKey", "/var/tmp/WhoKey", "/dev/shm/WhoKey", "/run/user/1000/WhoKey"):
                self.assertEqual(P.install_native_host(temporary), [])
        self.assertFalse((config / "google-chrome").exists())  # браузера нет — его папку не создаём
        target = config / "chromium" / "NativeMessagingHosts" / f"{P.HOST_NAME}.json"
        self.assertIn("/home/x/.local/opt/WhoKey/WhoKey", target.read_text())


@unittest.skipUnless(LINUX, "только Linux")
class PrivateSettings(unittest.TestCase):
    def test_settings_folder_is_closed_to_other_users(self):
        import app
        folder = Path(tempfile.mkdtemp()) / "EduPasswords"
        folder.mkdir(mode=0o755)
        (folder / "EduPasswords.conf").write_text("[General]\nvault_path=/home/x/vault.dat\n")
        os.chmod(folder / "EduPasswords.conf", 0o644)
        settings = mock.Mock()
        settings.fileName.return_value = str(folder / "EduPasswords.conf")
        app.keep_settings_private(settings)
        self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
        self.assertEqual((folder / "EduPasswords.conf").stat().st_mode & 0o777, 0o600)


@unittest.skipUnless(LINUX, "только Linux")
class ScreenLock(unittest.TestCase):
    def test_locker_process_is_noticed(self):
        from gui import autolock
        folder = Path(tempfile.mkdtemp(dir="/tmp"))
        program = folder / "hyprlock"
        shutil.copy("/bin/sleep", program)
        process = subprocess.Popen([str(program), "30"])
        try:
            time.sleep(0.2)
            self.assertTrue(autolock._locker_running())
            self.assertTrue(autolock.screen_locked())
        finally:
            process.kill()
            process.wait()

    def test_property_wrapped_in_a_variant_counts(self):
        # ревью 1.7.0: logind отдаёт LockedHint завёрнутым — сравнение «is True» не срабатывало
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.instance() or QCoreApplication([])
        from PySide6.QtDBus import QDBusMessage, QDBusVariant
        from gui import autolock
        reply = mock.Mock()
        reply.type.return_value = QDBusMessage.ReplyMessage
        reply.arguments.return_value = [QDBusVariant(True)]
        bus = mock.Mock()
        bus.call.return_value = reply
        self.assertIs(autolock._dbus_answer(bus, "s", "/p", "i", "m"), True)

    def test_dbus_without_services_does_not_break(self):
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.instance() or QCoreApplication([])
        from gui import autolock
        with mock.patch.object(autolock, "_locker_running", lambda: False):
            self.assertIn(autolock.screen_locked(), (True, False))


@unittest.skipUnless(LINUX, "только Linux")
class PrimarySelection(unittest.TestCase):
    def test_revealed_password_leaves_the_selection(self):
        from PySide6.QtGui import QClipboard
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from gui import widgets
        board = mock.Mock()
        board.supportsSelection.return_value = True
        board.text.return_value = "Secret-1"
        edit = widgets.SecretEdit()
        edit.setText("Secret-1")
        edit.selectAll()
        with mock.patch.object(widgets.QGuiApplication, "clipboard", lambda: board):
            widgets.forget_selection(edit)
            board.clear.assert_called_once_with(QClipboard.Selection)
            board.clear.reset_mock()
            board.text.return_value = "чужой текст"
            widgets.forget_selection(edit)
            board.clear.assert_not_called()


@unittest.skipUnless(LINUX, "только Linux")
class CapsLock(unittest.TestCase):
    def test_lock_bit_of_a_key_event(self):
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from gui import theme, widgets
        theme.apply(QApplication.instance())
        field = widgets.PasswordField(master=True)

        def press(native):
            return QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier, 30, 97, native)
        field.eventFilter(field.edit, press(2))
        self.assertTrue(widgets.caps_lock_on())
        field.eventFilter(field.edit, press(0))
        self.assertFalse(widgets.caps_lock_on())


CHILD = """
import sys, time
sys.path.insert(0, {here!r})
from PySide6.QtCore import QCoreApplication, QEventLoop
from PySide6.QtWidgets import QApplication
qt = QApplication([])
import app
if app.hand_over_to_running():
    print("second", flush=True)
    sys.exit(0)
print("first", flush=True)
class Window:
    def showNormal(self):
        print("shown", flush=True)
    def raise_(self):
        pass
    def activateWindow(self):
        pass
class Controller:
    window = Window()
server = app.listen_for_second_copy(Controller())
end = time.monotonic() + 6
while time.monotonic() < end:
    qt.processEvents(QEventLoop.AllEvents, 50)
"""


@unittest.skipUnless(LINUX, "только Linux")
class SecondCopy(unittest.TestCase):
    def test_second_copy_asks_the_first_and_leaves(self):
        home = tempfile.mkdtemp(dir="/tmp")
        env = dict(os.environ, HOME=home, XDG_DATA_HOME=home + "/data", XDG_CONFIG_HOME=home + "/config")
        code = CHILD.format(here=str(HERE))
        first = subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(first.stdout.readline().strip(), "first")
            time.sleep(1)
            second = subprocess.run([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE, text=True, timeout=30)
            self.assertIn("second", second.stdout)
            self.assertEqual(first.stdout.readline().strip(), "shown")
        finally:
            first.kill()
            first.wait()
        # первая копия упала — замок снят сам, старый сокет не мешает новой
        third = subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(third.stdout.readline().strip(), "first")
        finally:
            third.kill()
            third.wait()


@unittest.skipUnless(LINUX, "только Linux")
class Install(unittest.TestCase):
    def test_install_and_uninstall_keep_the_vault(self):
        home = Path(tempfile.mkdtemp(prefix="who key "))  # пробел в пути — частая причина поломок
        package = Path(tempfile.mkdtemp()) / "WhoKey"
        package.mkdir()
        (package / "WhoKey").write_text("#!/bin/sh\n")
        os.chmod(package / "WhoKey", 0o755)
        for name in ("install.sh", "uninstall.sh", "whokey.desktop"):
            shutil.copy(HERE / "linux" / name, package / name)
        (package / "whokey.png").write_bytes(b"png")
        env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
        empty = Path(tempfile.mkdtemp())  # в папке без программы установка ничего не удаляет
        shutil.copy(HERE / "linux" / "install.sh", empty / "install.sh")
        self.assertNotEqual(subprocess.run(["sh", str(empty / "install.sh")], env=dict(env, HOME=str(home)),
                                           capture_output=True).returncode, 0)
        env["HOME"] = str(home)
        vault = home / ".local/share/EduPasswords/vault.dat"
        vault.parent.mkdir(parents=True)
        vault.write_text("секрет")
        browser = home / ".config/chromium/NativeMessagingHosts"
        browser.mkdir(parents=True)
        (browser / "ru.edu.whokey.json").write_text("{}")

        subprocess.run(["sh", str(package / "install.sh")], env=env, check=True, capture_output=True)
        program = home / ".local/opt/WhoKey/WhoKey"
        self.assertTrue(os.access(program, os.X_OK))
        self.assertEqual((home / ".local/bin/whokey").resolve(), program.resolve())
        desktop = (home / ".local/share/applications/whokey.desktop").read_text()
        self.assertIn(f'Exec="{program}"', desktop)
        self.assertTrue((home / ".local/share/icons/hicolor/512x512/apps/whokey.png").exists())

        subprocess.run(["sh", str(package / "install.sh")], env=env, check=True, capture_output=True)  # обновление
        subprocess.run(["sh", str(home / ".local/opt/WhoKey/uninstall.sh")], env=env, check=True, capture_output=True)
        self.assertFalse(program.exists())
        self.assertFalse((home / ".local/bin/whokey").exists())
        self.assertFalse((browser / "ru.edu.whokey.json").exists())
        self.assertEqual(vault.read_text(), "секрет")


if __name__ == "__main__":
    unittest.main()
