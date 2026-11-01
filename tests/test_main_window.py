"""Главное окно и окно записи: клавиатура, выделение, замена пароля генератором."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

import gui.dialogs as D  # noqa: E402
import gui.main_window as MW  # noqa: E402
from gui import prefs  # noqa: E402
from vault import Vault  # noqa: E402


class Clipboard:
    def copy(self, text):
        return True


class MainWindow(unittest.TestCase):
    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        prefs.use_file(folder / "p.ini")
        self.vault = Vault.create(folder / "v.dat", "Зелёный-Кит-Летит-2026!")
        for site in ("github.com", "mail.ru", "steam"):
            self.vault.add(site, "egor", "pw-" + site)
        self.window = MW.MainWindow(self.vault, Clipboard())

    def test_tab_leaves_the_table(self):
        self.assertFalse(self.window.table.tabKeyNavigation())

    def test_selection_survives_search_without_results(self):
        self.window.refresh(select=1)
        self.window.search.setText("ничего такого нет")
        self.assertIsNone(self.window.selected_index())
        self.window.search.clear()
        self.assertEqual(self.window.selected_index(), 1)

    def test_delete_asks_with_red_button(self):
        asked = []
        real, MW.ask_yes = MW.ask_yes, lambda *args, **kw: asked.append(kw) or False
        try:
            self.window.refresh(select=0)
            self.window.delete()
        finally:
            MW.ask_yes = real
        self.assertEqual(asked[0]["danger"], "Delete")
        self.assertEqual(len(self.vault.entries), 3)  # «Отмена» — ничего не удалено


class CopyAboutVersion(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        prefs.use_file(self.folder / "p.ini")
        self.vault = Vault.create(self.folder / "v.dat", "Зелёный-Кит-Летит-2026!")
        self.vault.add("github.com", "egor", "pw")
        self.window = MW.MainWindow(self.vault, Clipboard())
        self.shown = []
        self._real = MW.QFileDialog.getSaveFileName, MW.show_info, MW.show_error
        MW.show_info = lambda parent, title, text: self.shown.append(text)
        MW.show_error = lambda parent, text: self.shown.append("ERROR " + text)

    def tearDown(self):
        MW.QFileDialog.getSaveFileName, MW.show_info, MW.show_error = self._real

    def test_encrypted_copy_opens_with_same_password(self):
        target = self.folder / "copy.dat"
        MW.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(target), ""))
        self.window.save_copy()
        self.assertEqual(Vault.open(target, "Зелёный-Кит-Летит-2026!").entries[0]["password"], "pw")
        self.assertNotIn(b"github.com", target.read_bytes())  # внутри — только шифр

    def test_copy_onto_itself_is_refused(self):
        MW.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(self.vault.path), ""))
        self.window.save_copy()
        self.assertTrue(self.shown[0].startswith("ERROR"))
        self.assertEqual(len(Vault.open(self.vault.path, "Зелёный-Кит-Летит-2026!").entries), 1)

    def test_about_and_version(self):
        import re
        import version
        from PySide6.QtWidgets import QLabel
        dialog = D.AboutDialog(self.window)
        text = " ".join(label.text() for label in dialog.findChildren(QLabel))
        for part in (version.VERSION, "github.com/kichike/whokey", ">kichike<"):
            self.assertIn(part, text)
        # версия одна на всё: установщик Windows собирается с той же
        iss = (Path(__file__).resolve().parent.parent / "installer.iss").read_text(encoding="utf-8")
        self.assertEqual(re.search(r'#define AppVersion "(.*)"', iss).group(1), version.VERSION)


class GenerateInSavedEntry(unittest.TestCase):
    def setUp(self):
        self.asked = []
        self.answer = False
        self._real = D.ask_yes
        D.ask_yes = lambda *args, **kw: self.asked.append(args[1]) or self.answer

    def tearDown(self):
        D.ask_yes = self._real

    def test_saved_password_is_not_replaced_silently(self):
        entry = {"site": "github.com", "login": "egor", "password": "старый", "note": "", "created": "x"}
        dialog = D.EntryDialog(None, entry)
        dialog.generator.generate()
        self.assertEqual(dialog.password.text(), "старый")  # «Нет» — пароль на месте
        self.answer = True
        dialog.generator.generate()
        self.assertNotEqual(dialog.password.text(), "старый")
        asked = len(self.asked)
        dialog.generator.generate()  # уже заменён — второй раз не спрашиваем
        self.assertEqual(len(self.asked), asked)

    def test_new_entry_is_not_asked(self):
        dialog = D.EntryDialog(None)
        dialog.generator.generate()
        self.assertTrue(dialog.password.text())
        self.assertEqual(self.asked, [])


if __name__ == "__main__":
    unittest.main()
