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
from gui import prefs  # noqa: E402
from vault import Vault  # noqa: E402

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
