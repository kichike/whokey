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
        if sys.platform != "win32":
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)  # как само хранилище

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


class Redesign(unittest.TestCase):
    """Короткие даты, пустое хранилище, «ничего не найдено»."""

    def test_short_dates(self):
        from PySide6.QtCore import QDateTime
        from gui import i18n
        from gui.dates import full_date, shown_date
        now = QDateTime.currentDateTime()
        stamp = lambda days: now.addDays(-days).toString("yyyy-MM-dd HH:mm")  # noqa: E731
        i18n.set_language("en")
        self.assertTrue(shown_date(stamp(0)).startswith("today, "))
        self.assertEqual(shown_date(stamp(1)), "yesterday")
        self.assertIn(str(now.addYears(-1).date().year()), shown_date(now.addYears(-1).toString("yyyy-MM-dd HH:mm")))
        self.assertEqual(shown_date("не дата"), "не дата")
        self.assertIn(":", full_date(stamp(40)))  # в подсказке — полностью, со временем

    def test_empty_and_nothing_found(self):
        from PySide6.QtWidgets import QPushButton
        folder = Path(tempfile.mkdtemp())
        prefs.use_file(folder / "p.ini")
        vault = Vault.create(folder / "v.dat", "Зелёный-Кит-Летит-2026!")
        window = MW.MainWindow(vault, Clipboard())
        self.assertIs(window.stack.currentWidget(), window.empty)
        buttons = [b.text() for b in window.empty.findChildren(QPushButton)]
        self.assertTrue(any("Add first entry" in t for t in buttons) and any("CSV" in t for t in buttons))
        vault.add("github.com", "egor", "pw")
        window.search.setText("zzz")
        self.assertIs(window.stack.currentWidget(), window.nothing_found)
        self.assertIn("zzz", window.nothing_text.text())
        [b for b in window.nothing_found.findChildren(QPushButton)][0].click()  # «Очистить поиск»
        self.assertEqual(window.search.text(), "")
        self.assertIs(window.stack.currentWidget(), window.table)
        self.assertFalse(window.table.item(0, 0).icon().isNull())  # буква-кружок у названия


class PlainTextLabels(unittest.TestCase):
    """Ревью 1.6: название записи и текст поиска — не HTML (иначе <img width=60000> ронял WhoKey)."""

    HOSTILE = "<img src=x width=30000 height=30000><b>bold</b>"

    def test_entry_name_and_search_are_plain_text(self):
        from PySide6.QtCore import Qt
        folder = Path(tempfile.mkdtemp())
        prefs.use_file(folder / "p.ini")
        vault = Vault.create(folder / "v.dat", "Зелёный-Кит-Летит-2026!")
        vault.add(self.HOSTILE, "egor", "pw")  # как после импорта CSV с таким названием
        window = MW.MainWindow(vault, Clipboard())
        window.resize(960, 600)
        window.search.setText(self.HOSTILE + "zz")
        self.assertEqual(window.nothing_text.textFormat(), Qt.PlainText)
        self.assertLess(window.nothing_text.sizeHint().height(), 200)
        dialog = D.EntryDialog(window, vault.entries[0])
        self.assertEqual(dialog.heading.textFormat(), Qt.PlainText)
        self.assertLess(dialog.sizeHint().width(), 3000)  # окно не раздувается картинкой
        self.assertIn("<img", dialog.heading.text())  # название показано как есть, буквами


class SyncInWindow(unittest.TestCase):
    """Окно WhoKey и второе устройство, пишущее в тот же файл."""

    def setUp(self):
        from unittest import mock
        self.folder = Path(tempfile.mkdtemp())
        prefs.use_file(self.folder / "p.ini")
        self.vault = Vault.create(self.folder / "vault.dat", "Зелёный-Кит-Летит-2026!")
        for site in ("первая", "вторая", "третья"):
            self.vault.add(site, "egor", "пароль-" + site)
        self.other = Vault.open_with_key(self.vault.path, self.vault.key)
        self.window = MW.MainWindow(self.vault, Clipboard())
        self.errors = []
        patcher = mock.patch.object(MW, "show_error", lambda parent, text: self.errors.append(text))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.window.sync_timer.stop)

    def settle(self):
        QApplication.processEvents()

    def row_of(self, site):
        for row in range(self.window.table.rowCount()):
            if self.window.table.item(row, 0).text() == site:
                return row
        return None

    def test_changes_from_another_device_appear_by_themselves(self):
        self.other.add("с-другого", "x", "новый")
        self.window.check_sync()
        self.settle()
        self.assertIsNotNone(self.row_of("с-другого"))
        self.assertTrue(self.window.statusBar().currentMessage())  # человеку сказали, что изменилось

    def test_row_never_points_to_someone_elses_password_after_merge(self):
        """Самое опасное: порядок записей изменился, а на экране старая таблица."""
        copied = []
        self.window.clipboard = type("C", (), {"copy": lambda s, text: copied.append(text) or True})()
        self.window.table.selectRow(self.row_of("третья"))
        self.other.delete(0)  # на другом устройстве удалили первую — номера записей сдвинулись
        self.vault.log_access("site", "egor")  # слияние посреди работы (пароль просит расширение)
        self.settle()
        self.window.copy()
        self.assertEqual(copied, ["пароль-третья"])
        self.assertIsNone(self.row_of("первая"))

    def test_sync_waits_while_a_dialog_is_open(self):
        from unittest import mock
        self.other.add("с-другого", "x", "новый")
        with mock.patch.object(MW.QApplication, "activeModalWidget", return_value=object()):
            self.window.check_sync()
        self.settle()
        self.assertIsNone(self.row_of("с-другого"))

    def test_edit_saved_after_reordering_changes_the_right_entry(self):
        from unittest import mock
        self.window.table.selectRow(self.row_of("третья"))
        other = self.other

        class Dialog:
            def __init__(self, parent, entry, copy_password=None):
                self.entry = entry

            def exec(self):
                other.delete(0)  # пока окно открыто, другое устройство удалило первую запись
                return True

            def values(self):
                return dict(self.entry, password="новый")
        with mock.patch.object(MW, "EntryDialog", Dialog):
            self.window.edit()
        self.settle()
        found = {e["site"]: e["password"] for e in self.vault.entries}
        self.assertEqual(found, {"вторая": "пароль-вторая", "третья": "новый"})

    def test_password_changed_elsewhere_locks_and_keeps_file(self):
        locked = []
        self.window.lock_requested.connect(lambda: locked.append(True))
        self.other.change_password("Новый-Длинный-Пароль-2026!")
        before = self.vault.path.read_bytes()
        self.window.check_sync()
        self.assertEqual(locked, [True])
        self.assertEqual(len(self.errors), 1)
        self.assertEqual(self.vault.path.read_bytes(), before)
        self.window.check_sync()  # спрашиваем один раз
        self.assertEqual(len(self.errors), 1)

    def test_saving_after_password_change_elsewhere_locks_too(self):
        locked = []
        self.window.lock_requested.connect(lambda: locked.append(True))
        self.other.change_password("Новый-Длинный-Пароль-2026!")
        self.assertFalse(self.window._save(lambda: self.vault.add("своё", "x", "1")))
        self.assertEqual(locked, [True])

    def test_half_downloaded_file_waits_silently_and_blocks_save(self):
        self.vault.path.write_text("{ ещё докачивается")
        self.window.check_sync()
        self.assertEqual(self.errors, [])
        self.assertFalse(self.window._save(lambda: self.vault.add("своё", "x", "1")))
        self.assertEqual(len(self.errors), 1)
        self.assertEqual(self.vault.path.read_text(), "{ ещё докачивается")

    def test_cloud_copy_is_offered_once_merged_and_trashed(self):
        from unittest import mock
        self.other.add("в-копии", "x", "пароль-копии")
        copy = self.folder / "vault (conflicted copy).dat"
        copy.write_bytes(self.vault.path.read_bytes())
        self.vault.save()  # основной файл снова без неё
        self.other = None
        asked = []
        with mock.patch.object(MW, "ask_yes", lambda *a, **k: asked.append(a) or True), \
                mock.patch.object(MW.QFile, "moveToTrash", return_value=True) as trash:
            self.window.check_sync()
            self.window.check_sync()
        self.assertEqual(len(asked), 1)
        trash.assert_called_once()
        self.assertIn("пароль-копии", {e["password"] for e in self.vault.entries})

    def test_foreign_file_with_similar_name_is_not_offered(self):
        from unittest import mock
        Vault.create(self.folder / "vault 2.dat", "Совсем-Другой-Пароль-2026!")
        with mock.patch.object(MW, "ask_yes") as ask:
            self.window.check_sync()
        ask.assert_not_called()

    def _pick_folder(self, folder):
        from unittest import mock
        return mock.patch.object(MW.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(folder)))

    def test_move_to_cloud_folder(self):
        moved = []
        self.window.vault_moved.connect(moved.append)
        cloud = Path(tempfile.mkdtemp())
        old = self.vault.path
        with self._pick_folder(cloud):
            self.assertTrue(self.window.move_vault())
        self.assertEqual(moved, [cloud / "vault.dat"])
        self.assertFalse(old.exists())
        self.assertFalse(MW.backup_path(old).exists())
        self.assertEqual(len(Vault.open(cloud / "vault.dat", "Зелёный-Кит-Летит-2026!").entries), 3)

    def test_move_never_overwrites_a_file_already_there(self):
        cloud = Path(tempfile.mkdtemp())
        (cloud / "vault.dat").write_text("хранилище с другого устройства")
        old = self.vault.path
        with self._pick_folder(cloud):
            self.assertFalse(self.window.move_vault())
        self.assertEqual((cloud / "vault.dat").read_text(), "хранилище с другого устройства")
        self.assertEqual(self.vault.path, old)
        self.assertTrue(old.exists())
        self.assertEqual(len(self.errors), 1)

    def test_failed_move_keeps_the_old_file(self):
        from unittest import mock
        cloud = Path(tempfile.mkdtemp())
        old = self.vault.path
        with self._pick_folder(cloud), mock.patch.object(MW.Vault, "open_with_key", side_effect=OSError(5, "сбой")):
            self.assertFalse(self.window.move_vault())
        self.assertEqual(self.vault.path, old)
        self.assertTrue(old.exists())
        self.assertFalse((cloud / "vault.dat").exists())


class RealDialogs(unittest.TestCase):
    """Настоящие окна, а не заглушки: окно кода сопряжения падало, а тесты моста его подменяли."""

    def test_pairing_code_dialog_opens_and_returns_the_code(self):
        from unittest import mock
        from PySide6.QtWidgets import QLineEdit, QMessageBox
        from gui import widgets

        def type_code(box):  # «человек» вводит код и нажимает «Разрешить»
            field = box.findChild(QLineEdit)
            field.setText("4821")
            box.show()
            QApplication.processEvents()
            allow = [b for b in box.buttons() if box.buttonRole(b) == QMessageBox.AcceptRole][0]
            self.assertLess(field.geometry().bottom(), allow.mapTo(box, allow.rect().topLeft()).y())  # поле — над кнопками
            allow.click()
            return 0
        with mock.patch.object(QMessageBox, "exec", type_code):
            self.assertEqual(widgets.ask_code(None, "Заголовок", "Текст"), "4821")

    def test_long_name_does_not_stretch_the_entry_dialog(self):
        dialog = D.EntryDialog(None, {"site": "x" * 20000, "login": "", "password": "", "note": ""})
        self.assertLess(dialog.sizeHint().width(), 1200)


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
