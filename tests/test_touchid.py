"""Вход по Touch ID: то, что можно проверить без пальца (python3 -m unittest discover tests)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gui import touchid  # noqa: E402
from vault import Vault, WrongPassword  # noqa: E402


class OpenWithKey(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "t.dat"
        self.vault = Vault.create(self.path, "Зелёный-Кит-Летит-2026!")
        self.vault.add("github.com", "egor", "pw")

    def test_right_key_opens(self):
        self.assertEqual(len(Vault.open_with_key(self.path, self.vault.key).entries), 1)

    def test_wrong_or_broken_key_is_wrong_password(self):
        for bad in (b"A" * 44, b"short", "not bytes", b""):
            with self.subTest(key=bad):
                with self.assertRaises(WrongPassword):
                    Vault.open_with_key(self.path, bad)

    def test_old_key_stops_working_after_master_change(self):
        old = self.vault.key
        self.vault.change_password("Новый-Мастер-Пароль-77")
        with self.assertRaises(WrongPassword):
            Vault.open_with_key(self.path, old)


class Availability(unittest.TestCase):
    def test_off_without_real_screen(self):
        """В автотестах (окна «без экрана») настоящее окно Touch ID не всплывает."""
        QApplication.instance() or QApplication([])
        self.assertFalse(touchid.available())

    @unittest.skipUnless(sys.platform == "darwin", "время загрузки — только macOS")
    def test_boot_time(self):
        self.assertGreater(touchid.boot_time(), 1_600_000_000)


if __name__ == "__main__":
    unittest.main()
