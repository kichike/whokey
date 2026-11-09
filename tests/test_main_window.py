"""Главное окно и окно записи: клавиатура, выделение, замена пароля генератором."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

import gui.dialogs as D  # noqa: E402
import gui.main_window as MW  # noqa: E402
from gui import prefs, sound, theme  # noqa: E402
from vault import Vault, VaultTooLarge  # noqa: E402


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

    def test_failed_save_reopens_the_entry_window(self):
        """Хранилище переполнено: введённое (и пароль, уже вписанный на сайте) не пропадает."""
        answers, errors = [1, 0], []

        class Dialog:
            def __init__(self, *args, **kwargs):
                pass

            def exec(self):
                return answers.pop(0)

            def values(self):
                return {"site": "x", "login": "", "password": "p" * 500, "note": "", "url": ""}

        def full(*args, **kwargs):
            raise VaultTooLarge("full")
        real = MW.EntryDialog, MW.show_error, self.vault.add
        MW.EntryDialog, MW.show_error, self.vault.add = Dialog, (lambda parent, text: errors.append(text)), full
        try:
            self.window.add()
        finally:
            MW.EntryDialog, MW.show_error, self.vault.add = real
        self.assertEqual(answers, [])  # окно показано второй раз
        self.assertEqual(len(errors), 1)
        self.assertIn("10 MB", errors[0])

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


class EasterEgg(unittest.TestCase):
    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        prefs.use_file(folder / "p.ini")
        self.vault = Vault.create(folder / "v.dat", "Зелёный-Кит-Летит-2026!")
        self.vault.add("github.com", "egor", "pw")
        self.window = MW.MainWindow(self.vault, Clipboard())
        self.window.show()
        self.usual = (theme.BG, theme.ACC, theme.STYLE)
        self.sounds = []  # настоящий звук в тестах не играем
        self.addCleanup(setattr, MW, "play_fart", MW.play_fart)
        MW.play_fart = lambda: self.sounds.append(1)
        self.addCleanup(theme.set_egg, False)

    def finish_wave(self):
        wave = self.window._wave
        self.assertIsNotNone(wave)
        wave.animation.setCurrentTime(wave.DURATION)  # сразу в конец
        self.assertIsNone(self.window._wave)

    def test_three_clicks_on_and_one_click_off(self):
        self.window._logo_clicked()
        self.window._logo_clicked()
        self.assertFalse(theme.egg)
        self.assertEqual(self.sounds, [])
        self.window._logo_clicked()
        self.assertTrue(theme.egg)
        self.assertEqual(len(self.sounds), 1)  # звук — на третье нажатие
        self.assertEqual((theme.BG, theme.ACC), ("#140a03", "#ffe600"))
        self.assertIn("255, 230, 0", theme.GLASS_ACC)  # производные цвета тоже новые
        self.assertIn("#140a03", APP.styleSheet())
        self.window._logo_clicked()  # пока идёт волна, нажатия не считаются
        self.assertTrue(theme.egg)
        self.finish_wave()
        self.window._logo_clicked()
        self.assertFalse(theme.egg)
        self.assertEqual(len(self.sounds), 1)  # обратно — без звука
        self.finish_wave()
        self.assertEqual((theme.BG, theme.ACC, theme.STYLE), self.usual)

    def test_sound_file_is_valid_and_player_is_safe(self):
        import wave
        with wave.open(str(sound.FART_FILE)) as audio:
            self.assertGreater(audio.getnframes() / audio.getframerate(), 0.3)
        real = sound.FART_FILE
        sound.FART_FILE = Path(tempfile.mkdtemp()) / "нет такого.wav"
        self.addCleanup(setattr, sound, "FART_FILE", real)
        sound.play_fart()  # файла нет — тишина, а не ошибка

    def test_hidden_password_does_not_stay_on_the_snapshot(self):
        self.window.refresh(select=0)
        self.window.toggle_reveal()
        self.window._toggle_egg()
        self.assertIsNotNone(self.window._wave)
        self.window._auto_hide()
        self.assertIsNone(self.window._wave)
        self.window._toggle_egg()
        self.window.search.setText("ничего такого нет")  # и любое другое обновление таблицы
        self.assertIsNone(self.window._wave)

    def test_letters_and_glow_come_back_with_usual_colors(self):
        add = [b for b in self.window.findChildren(MW.QPushButton) if b.property("kind") == "primary"][0]
        usual_glow = add.graphicsEffect().color().name()
        letter = self.window._monogram("github").pixmap(24).toImage()
        self.window._toggle_egg()
        self.assertNotEqual(self.window._monogram("github").pixmap(24).toImage(), letter)
        self.finish_wave()
        self.window._toggle_egg()
        self.finish_wave()
        self.assertEqual(add.graphicsEffect().color().name(), usual_glow)
        self.assertEqual(self.window._monogram("github").pixmap(24).toImage(), letter)

    def test_poop_is_always_a_colored_picture(self):
        """На сборке для Windows без цветного шрифта вместо эмодзи вышел пустой квадрат."""
        self.assertTrue(theme._has_color(theme._drawn_poop(36)))
        self.assertTrue(theme._has_color(theme._poop_pixmap(36)))
        tofu = theme.QPixmap(36, 36)
        tofu.fill(theme.QColor("#000000"))
        self.assertFalse(theme._has_color(tofu))

    def test_slow_clicks_do_not_count(self):
        for _ in range(3):
            self.window._logo_clicked()
            self.window._last_logo_click -= MW.EGG_CLICK_GAP + 1
        self.assertFalse(theme.egg)

    def test_logo_changes_and_real_mouse_clicks_work(self):
        key = self.window.logo.pixmap().toImage()
        for _ in range(3):
            QTest.mouseClick(self.window.logo, Qt.LeftButton)
        self.assertTrue(theme.egg)
        self.assertNotEqual(self.window.logo.pixmap().toImage(), key)
        self.finish_wave()
        QTest.mouseDClick(self.window.logo, Qt.LeftButton)  # и двойное нажатие не ломает
        self.finish_wave()

    def test_wave_paints_at_every_stage(self):
        self.window._toggle_egg()
        wave = self.window._wave
        for value in (0.0, 0.5, 1.0):
            wave._advance(value)
            self.assertFalse(wave.grab().isNull())
        self.finish_wave()

    def test_egg_does_not_touch_the_vault_or_settings(self):
        before = self.vault.path.read_bytes()
        self.window._toggle_egg()
        self.finish_wave()
        self.assertEqual(self.vault.path.read_bytes(), before)


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
