"""Импорт и экспорт CSV, окна записи и экспорта. Всё — во временной папке."""

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

import csv_io  # noqa: E402
import gui.dialogs as D  # noqa: E402
import gui.login as L  # noqa: E402
import gui.widgets as W  # noqa: E402
from gui import prefs, theme, touchid  # noqa: E402
import vault as V  # noqa: E402
from vault import SaveError, Vault, VaultTooLarge  # noqa: E402

PASSWORD = "Зелёный-Кит-Летит-2026!"

# заголовки и строки так, как их выгружают сами программы
CHROME = 'name,url,username,password,note\ngithub.com,https://github.com/login,egor,"p,1""x",\n'
FIREFOX = ('"url","username","password","httpRealm","formActionOrigin","guid","timeCreated"\n'
           '"https://mail.ru","egor@mail.ru","p2",,"https://mail.ru","{1}","1"\n')
BITWARDEN = ("folder,favorite,type,name,notes,fields,reprompt,login_uri,login_username,login_password,login_totp\n"
             ",,login,Почта,строка 1,,0,https://e.mail.ru,egor,p3,\n"
             ",,note,Просто заметка,текст,,0,,,,\n")
KEEPASSXC = ('"Group","Title","Username","Password","URL","Notes","TOTP","Icon","Last Modified","Created"\n'
             '"Root","Банк","egor","p4","https://bank.ru","",,"0","",""\n')


class Import(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())

    def read(self, text, encoding="utf-8"):
        path = self.folder / "in.csv"
        path.write_bytes(text.encode(encoding))
        return csv_io.read(path)

    def test_programs(self):
        self.assertEqual(self.read(CHROME), [{"site": "github.com", "login": "egor", "password": 'p,1"x',
                                              "note": "", "url": "github.com"}])
        firefox = self.read(FIREFOX)[0]  # у Firefox нет названия — берём адрес
        self.assertEqual((firefox["site"], firefox["login"], firefox["password"]), ("mail.ru", "egor@mail.ru", "p2"))
        bitwarden = self.read(BITWARDEN)  # заметка без пароля пропущена
        self.assertEqual([(e["site"], e["note"], e["url"]) for e in bitwarden], [("Почта", "строка 1", "e.mail.ru")])
        self.assertEqual(self.read(KEEPASSXC)[0]["site"], "Банк")

    def test_excel_bom_and_bad_files(self):
        self.assertEqual(len(self.read("﻿" + CHROME)), 1)
        for text, reason in (("", "format"), ("a,b\n1,2\n", "columns"), ("name,user\nx,y\n", "columns")):
            with self.assertRaises(csv_io.CsvError) as caught:
                self.read(text)
            self.assertEqual(str(caught.exception), reason)
        with self.assertRaises(csv_io.CsvError):
            self.read("name,password\nПочта,пароль\n", encoding="cp1251")

    def test_short_rows_do_not_crash(self):
        self.assertEqual(self.read("name,url,username,password\nx\ny,,,p\n")[0]["site"], "y")

    def test_repeated_import_adds_nothing(self):
        vault = Vault.create(self.folder / "v.dat", PASSWORD)
        entries = self.read(CHROME + "github.com,https://github.com,egor,\"p,1\"\"x\",\n")
        self.assertEqual(len(entries), 2)
        fresh = csv_io.new_only(entries, vault.entries)
        self.assertEqual(len(fresh), 1)  # второй такой же — дубль внутри файла
        vault.add_many(fresh)
        self.assertEqual(csv_io.new_only(entries, vault.entries), [])
        again = Vault.open(vault.path, PASSWORD)
        self.assertEqual(again.entries[0]["password"], 'p,1"x')
        self.assertIn("created", again.entries[0])


class Export(unittest.TestCase):
    def test_round_trip_and_private_file(self):
        folder = Path(tempfile.mkdtemp())
        entries = [{"site": "Почта", "login": "egor", "password": '=1+2,"x"', "note": "две\nстроки", "url": "mail.ru"},
                   {"site": "Старая", "login": "", "password": "p", "note": ""}]  # у старых записей нет url
        path = folder / "out.csv"
        path.write_text("старое содержимое")
        os.chmod(path, 0o644)
        csv_io.write(path, entries)
        back = csv_io.read(path)
        self.assertEqual([(e["site"], e["password"], e["note"]) for e in back],
                         [(e["site"], e["password"], e["note"]) for e in entries])
        if sys.platform != "win32":
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)


class ImportWhenCreating(unittest.TestCase):
    """Кнопка импорта в окне создания: CSV выбран до того, как хранилище появилось."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        prefs.use_file(self.folder / "s.ini")
        self.path = self.folder / "v.dat"
        self.csv = self.folder / "chrome.csv"
        self.csv.write_text(CHROME + "github.com,https://github.com/login,egor,\"p,1\"\"x\",\n", encoding="utf-8")  # второй — дубль
        self.infos, self.errors, self.windows = [], [], []
        for name, value in (("show_info", lambda parent, title, text: self.infos.append(text)),
                            ("show_error", lambda parent, text: self.errors.append(text)),
                            ("ask_yes", lambda *args, **kwargs: False)):
            self.addCleanup(setattr, L, name, getattr(L, name))
            setattr(L, name, value)
        self.addCleanup(setattr, W, "show_error", W.show_error)
        W.show_error = lambda parent, text: self.errors.append(text)
        self.addCleanup(setattr, W.QFileDialog, "getOpenFileName", W.QFileDialog.getOpenFileName)
        self.pick(self.csv)
        # замки и Связка ключей — не настоящие
        self.addCleanup(setattr, V, "app_data_dir", V.app_data_dir)
        V.app_data_dir = lambda: self.folder
        self.addCleanup(setattr, touchid, "state", touchid.state)
        self.addCleanup(setattr, touchid, "available", touchid.available)
        touchid.state, touchid.available = (lambda path: None), (lambda: False)

    def pick(self, path):
        W.QFileDialog.getOpenFileName = staticmethod(lambda *args, **kwargs: (str(path), ""))

    def window(self, state=None):
        window = L.LoginWindow(self.path, {} if state is None else state)
        window.opened.connect(self.windows.append)
        return window

    def create(self, window):
        window.master.edit.setText(PASSWORD)
        window.repeat.edit.setText(PASSWORD)
        window.on_create()

    def test_entries_land_in_the_new_vault(self):
        window = self.window()
        window._toggle_import()
        self.assertFalse(self.path.exists())  # без мастер-пароля на диск ничего не попало
        self.assertIn("chrome.csv", window.import_note.text())
        self.create(window)
        self.assertEqual(len(self.windows), 1)
        self.assertEqual(self.windows[0].entries[0]["password"], 'p,1"x')
        reopened = Vault.open(self.path, PASSWORD)
        self.assertEqual(len(reopened.entries), 1)  # дубль внутри файла не добавлен
        self.assertEqual(len(self.infos), 1)
        self.assertIn("delete", self.infos[0])  # напомнили удалить незашифрованный файл
        self.assertNotIn('p,1"x', self.path.read_text(encoding="latin-1"))

    def test_note_does_not_squeeze_the_window(self):
        window = self.window()
        window.show()
        before = window.height()
        window._toggle_import()
        for _ in range(3):
            APP.processEvents()
        self.assertGreater(window.height(), before)
        for label in window.findChildren(L.QLabel):  # подпись появилась — ни одна строка не обрезана
            if label.isVisible() and label.wordWrap():
                self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()), label.text())
        window._toggle_import()
        for _ in range(3):
            APP.processEvents()
        self.assertEqual(window.height(), before)
        window.close()

    def test_changed_mind(self):
        window = self.window()
        window._toggle_import()
        window._toggle_import()
        self.assertTrue(window.import_note.isHidden())
        self.create(window)
        self.assertEqual(Vault.open(self.path, PASSWORD).entries, [])
        self.assertEqual(self.infos, [])

    def test_bad_file_is_reported_and_not_kept(self):
        self.csv.write_text("name,password\n", encoding="utf-8")  # столбцы есть, паролей нет
        window = self.window()
        window._toggle_import()
        self.assertEqual(len(self.errors), 1)
        self.assertIsNone(window._import)
        self.assertTrue(window.import_note.isHidden())

    def test_cancelled_file_dialog_keeps_the_choice_empty(self):
        self.pick("")
        window = self.window()
        window._toggle_import()
        self.assertIsNone(window._import)
        self.assertEqual(self.errors, [])

    def test_failed_save_keeps_the_vault(self):
        window = self.window()
        window._toggle_import()
        self.addCleanup(setattr, Vault, "add_many", Vault.add_many)

        def broken(vault, entries):
            raise SaveError("disk full")
        Vault.add_many = broken
        self.create(window)
        self.assertEqual(len(self.windows), 1)  # хранилище открылось, импорт можно повторить
        self.assertIn("disk full", self.infos[0])

    def test_choice_survives_another_vault_file(self):
        state = {}
        window = self.window(state)
        window._toggle_import()
        self.addCleanup(setattr, L.QFileDialog, "getSaveFileName", L.QFileDialog.getSaveFileName)
        L.QFileDialog.getSaveFileName = staticmethod(lambda *args, **kwargs: (str(self.path), ""))
        window._choose_file()
        again = self.window(state)
        self.assertFalse(again.import_note.isHidden())
        self.assertNotIn("import", state)  # пароли не задерживаются в общих данных окон

    def test_existing_vault_has_no_button(self):
        Vault.create(self.path, PASSWORD)
        self.assertFalse(hasattr(self.window(), "import_button"))

    def test_existing_vault_drops_the_choice_and_says_so(self):
        Vault.create(self.path, PASSWORD)
        state = {"import": ("chrome.csv", [{"site": "x", "login": "", "password": "секрет", "note": "", "url": ""}])}
        window = self.window(state)
        self.assertIsNone(window._import)
        self.assertIn("cancelled", window.notice.text())
        self.assertNotIn("import", state)

    def test_vault_appearing_meanwhile_is_not_mixed_with_the_csv(self):
        state = {}
        window = self.window(state)
        window._toggle_import()
        Vault.create(self.path, PASSWORD)
        self.create(window)
        self.assertEqual(Vault.open(self.path, PASSWORD).entries, [])
        again = self.window(state)
        self.assertIn("cancelled", again.notice.text())
        self.assertIsNone(again._import)

    def test_too_big_import_keeps_the_new_vault_openable(self):
        window = self.window()
        # меньше предела CSV по отдельности, но вместе с шифрованием больше предела хранилища
        row = {"site": "s", "login": "", "password": "p" * 500, "note": "", "url": ""}
        window._import = ("big.csv", [row] * 15000)
        self.create(window)
        self.assertEqual(Vault.open(self.path, PASSWORD).entries, [])
        self.assertIn("10 MB", self.infos[0])
        self.assertNotIn("delete it", self.infos[0])


class Limits(unittest.TestCase):
    """Ревью 1.6.2: большой импорт делал хранилище и копию неоткрываемыми, спецфайлы вешали окно."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())

    def test_vault_never_writes_what_it_cannot_open(self):
        path = self.folder / "v.dat"
        vault = Vault.create(path, PASSWORD)
        vault.add("Почта", "egor", "p")
        big = [{"site": "s", "login": "", "password": "p" * 500, "note": "", "url": ""}] * 15000
        with self.assertRaises(VaultTooLarge):
            vault.add_many(big)
        self.assertEqual(len(vault.entries), 1)
        self.assertEqual(len(Vault.open(path, PASSWORD).entries), 1)
        self.assertEqual(len(Vault.open(V.backup_path(path), PASSWORD).entries), 1)

    def test_csv_limits(self):
        path = self.folder / "big.csv"
        path.write_text("name,password\n" + "x" * csv_io.MAX_SIZE, encoding="utf-8")
        with self.assertRaises(csv_io.CsvError) as caught:
            csv_io.read(path)
        self.assertEqual(str(caught.exception), "too_big")
        path.write_text("name,password\n" + "a,b\n" * (csv_io.MAX_ROWS + 1), encoding="utf-8")
        with self.assertRaises(csv_io.CsvError) as caught:
            csv_io.read(path)
        self.assertEqual(str(caught.exception), "too_big")

    @unittest.skipIf(sys.platform == "win32", "FIFO и /dev/zero — только Mac и Linux")
    def test_special_files_do_not_hang(self):
        fifo = self.folder / "pipe.csv"
        os.mkfifo(fifo)
        zero = self.folder / "zero.csv"
        zero.symlink_to("/dev/zero")
        for path in (fifo, zero):
            with self.assertRaises(csv_io.CsvError):
                csv_io.read(path)
            with self.assertRaises(V.VaultError):
                V._read_header(path)

    def test_export_over_open_file_narrows_rights_first(self):
        path = self.folder / "o.csv"
        path.write_text("")
        os.chmod(path, 0o644)
        seen = []
        real = csv_io.csv.writer
        csv_io.csv.writer = lambda f: seen.append(stat.S_IMODE(os.stat(path).st_mode)) or real(f)
        self.addCleanup(setattr, csv_io.csv, "writer", real)
        csv_io.write(path, [])
        if sys.platform != "win32":
            self.assertEqual(seen, [0o600])

    def test_every_written_vault_can_be_saved_again(self):
        self.assertLess(V.MAX_WRITE_SIZE, V.MAX_FILE_SIZE)
        path = self.folder / "v.dat"
        vault = Vault.create(path, PASSWORD)
        low, high = 0, V.MAX_WRITE_SIZE
        while high - low > 64:  # самая длинная заметка, которая ещё записывается
            middle = (low + high) // 2
            try:
                vault._write([{"site": "s", "login": "", "password": "p", "note": "x" * middle, "created": "2026-01-01", "updated": "2026-01-01"}], vault._key, vault._salt, vault._params)
                low = middle
            except VaultTooLarge:
                high = middle
        vault._write([{"site": "s", "login": "", "password": "p", "note": "x" * low, "created": "2026-01-01", "updated": "2026-01-01"}], vault._key, vault._salt, vault._params)
        again = Vault.open(path, PASSWORD)
        self.assertEqual(len(again.entries[0]["note"]), low)
        again.save()
        Vault.open(path, PASSWORD)

    def test_regular_file_is_read_in_blocking_mode(self):
        if sys.platform == "win32":
            return
        import fcntl
        from regular_file import open_regular
        path = self.folder / "f.csv"
        path.write_text("x")
        fd = open_regular(path)
        self.addCleanup(os.close, fd)
        self.assertFalse(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_NONBLOCK)

    def test_empty_tooltip_stays_empty(self):
        self.assertEqual(theme.plain_tip(""), "")

    def test_tooltip_is_not_html(self):
        tip = theme.plain_tip("<img src=x width=60000> a & b\nстрока")
        self.assertNotIn("<img", tip)
        self.assertIn("&lt;img", tip)
        self.assertIn("<br>", tip)


class Dialogs(unittest.TestCase):
    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        prefs.use_file(folder / "s.ini")
        self.vault = Vault.create(folder / "v.dat", PASSWORD)
        self.asked = []
        self._ask = D.ask_yes
        D.ask_yes = lambda parent, title, text: self.asked.append(text) or False

    def tearDown(self):
        D.ask_yes = self._ask

    def test_unsaved_changes_are_asked_about(self):
        dialog = D.EntryDialog(None)
        dialog.reject()  # ничего не меняли — закрывается без вопроса
        self.assertEqual(self.asked, [])
        dialog = D.EntryDialog(None)
        dialog.note.setPlainText("коды\nвосстановления")
        dialog.reject()
        self.assertEqual(len(self.asked), 1)
        self.assertTrue(dialog.isVisible() or dialog.result() == 0)
        self.assertEqual(dialog.values()["note"], "коды\nвосстановления")

    def test_invalid_field_is_marked(self):
        dialog = D.EntryDialog(None)
        dialog.accept()
        self.assertEqual(dialog.site.property("invalid"), True)
        dialog.site.setText("Почта")
        dialog.accept()
        self.assertFalse(dialog.site.property("invalid"))
        self.assertEqual(dialog.password.edit.property("invalid"), True)

    def test_prefilled_from_extension_is_new(self):
        dialog = D.EntryDialog(None, {"site": "github.com", "login": "", "password": "", "note": "", "url": "github.com"})
        self.assertEqual(dialog.windowTitle(), "New entry")
        dialog.reject()  # только адрес — закрывается без вопроса
        self.assertEqual(self.asked, [])
        # пароль из «Сгенерировать» на сайте уже вписан там — молча закрыть нельзя (ревью 1.5.1)
        dialog = D.EntryDialog(None, {"site": "github.com", "login": "egor", "password": "Gen-1!", "note": "", "url": "github.com"})
        dialog.reject()
        self.assertEqual(len(self.asked), 1)

    def test_export_needs_master_password(self):
        dialog = D.ExportDialog(None, self.vault)
        dialog.master.setText("не тот")
        dialog.accept()
        self.assertEqual(dialog.result(), 0)
        self.assertTrue(dialog.error.text())
        dialog.master.setText(PASSWORD)
        dialog.accept()
        self.assertEqual(dialog.result(), 1)

    def test_change_master_checks_match_before_weakness(self):
        dialog = D.ChangeMasterDialog(None, self.vault)
        dialog.current.setText(PASSWORD)
        dialog.new.setText("aaaaaaaaaaaaaaaa")
        dialog.repeat.setText("другой")
        dialog.accept()
        self.assertEqual(self.asked, [])  # о слабости не спросили — сначала несовпадение
        self.assertIn("match", dialog.error.text())


if __name__ == "__main__":
    unittest.main()
