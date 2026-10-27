"""Путь человека через контроллер приложения: смена языка, блокировка, повторное «открыто».

Настройки — во временном файле, сокет расширения — во временной папке:
настоящие настройки, хранилище и сокет WhoKey не трогаются.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

import app as A  # noqa: E402
import bridge_protocol as P  # noqa: E402
from gui import prefs  # noqa: E402
from gui.login import LoginWindow  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from vault import Vault  # noqa: E402


def settle():
    """Выполнить отложенные удаления окон (deleteLater) и события."""
    for _ in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QCoreApplication.processEvents()


class ControllerFlow(unittest.TestCase):
    def setUp(self):
        folder = Path(tempfile.mkdtemp(dir="/tmp" if sys.platform != "win32" else None))
        ini = str(folder / "s.ini")
        self._real = (A.QSettings, P.socket_address, A.default_vault_path)
        A.QSettings = lambda *a: QSettings(ini, QSettings.IniFormat)
        prefs.use_file(folder / "prefs.ini")
        A.default_vault_path = lambda: folder / "default.dat"
        address = ("whokey-test-" + os.urandom(6).hex()) if P.WINDOWS else str(folder / "b.sock")
        P.socket_address = lambda: address
        self.vault = Vault.create(folder / "v.dat", "Зелёный-Кит-Летит-2026!")
        self.vault.add("GitHub", "egor", "pw", url="github.com")
        self.controller = A.Controller()

    def tearDown(self):
        self.controller.stop_bridge()
        A.QSettings, P.socket_address, A.default_vault_path = self._real

    def test_language_change_keeps_extension_and_lock_works(self):
        c = self.controller
        c.show_main(self.vault)
        c.change_language(self.vault, "en")
        settle()  # старое окно удалено
        self.assertTrue(c.bridge.server.isListening(), "сервер расширения пережил смену языка")
        c.lock()  # раньше падал на удалённом сервере, и хранилище оставалось открытым
        settle()
        self.assertIsNone(c.bridge)
        self.assertIsInstance(c.window, LoginWindow)

    def test_old_copy_of_the_file_is_noticed(self):
        """Ревью безопасности: подменённая старая копия возвращала отозванный доступ расширения."""
        import shutil
        warnings = []
        real_error, A.show_error = A.show_error, lambda parent, text: warnings.append(text)
        try:
            c = self.controller
            old_copy = self.vault.path.with_suffix(".old")
            shutil.copy(self.vault.path, old_copy)  # кто-то сохранил копию «на потом»
            c.show_main(self.vault)
            self.vault.set_bridge_keys(["отпечаток"])  # потом подключили расширение...
            self.vault.set_bridge_keys([])            # ...и отключили его
            c.lock()
            settle()
            shutil.copy(old_copy, self.vault.path)    # файл подменили старой копией
            c.show_main(Vault.open(self.vault.path, "Зелёный-Кит-Летит-2026!"))
            self.assertEqual(len(warnings), 1)
            c.lock()
            settle()
            c.show_main(Vault.open(self.vault.path, "Зелёный-Кит-Летит-2026!"))
            self.assertEqual(len(warnings), 1, "предупреждаем один раз, а не при каждом открытии")
        finally:
            A.show_error = real_error

    def test_second_open_is_ignored(self):
        c = self.controller
        c.show_main(self.vault)
        first_window, first_bridge = c.window, c.bridge
        c.show_main(self.vault)  # отпечаток и пароль почти одновременно
        self.assertIs(c.window, first_window)
        self.assertIs(c.bridge, first_bridge)
        self.assertIsInstance(c.window, MainWindow)


if __name__ == "__main__":
    unittest.main()
