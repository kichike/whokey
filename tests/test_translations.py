"""Проверки перевода окон (Qt Linguist): python3 -m unittest discover tests"""

import ast
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "translations"))

import build  # noqa: E402  translations/build.py
from PySide6.QtCore import QCoreApplication  # noqa: E402

from gui import i18n  # noqa: E402

PLACEHOLDER = re.compile(r"\{\w*\}")


def messages(ts_file):
    """(раздел, исходная надпись, элемент перевода) для каждой строки .ts"""
    for context in ET.parse(ts_file).getroot().iter("context"):
        name = context.findtext("name") or ""
        for message in context.iter("message"):
            yield name, message.findtext("source"), message


class Translations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def tearDown(self):
        i18n.set_language("en")

    def test_every_text_is_translated_to_russian(self):
        for context, source, message in messages(build.HERE / "whokey_ru.ts"):
            translation = message.find("translation")
            with self.subTest(source=source):
                self.assertNotIn(translation.get("type"), ("unfinished", "vanished", "obsolete"))
                forms = translation.findall("numerusform") or [translation]
                for form in forms:
                    self.assertTrue((form.text or "").strip(), "пустой перевод")
                    # {code}, {path}… должны остаться — иначе .format() упадёт или потеряет данные
                    self.assertEqual(sorted(PLACEHOLDER.findall(source)), sorted(PLACEHOLDER.findall(form.text)))

    def test_ts_files_match_the_code(self):
        """Все надписи из кода есть в .ts — никто не забыл запустить build.py --update."""
        with tempfile.TemporaryDirectory() as folder:
            fresh = Path(folder) / "fresh.ts"
            subprocess.run([build.tool("pyside6-lupdate"), *build.sources(), "-ts", str(fresh)],
                           cwd=ROOT, check=True, capture_output=True)
            in_code = {(c, s) for c, s, _ in messages(fresh)}
        for lang in build.LANGUAGES:
            with self.subTest(lang=lang):
                in_ts = {(c, s) for c, s, _ in messages(build.HERE / f"whokey_{lang}.ts")}
                self.assertEqual(in_code, in_ts)

    def test_no_tr_inside_f_strings(self):
        """lupdate молча пропускает tr() внутри f"…" — такая надпись осталась бы без перевода."""
        for source in build.sources():
            tree = ast.parse((ROOT / source).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.JoinedStr):
                    calls = [c for c in ast.walk(node) if isinstance(c, ast.Call)
                             and getattr(c.func, "id", getattr(c.func, "attr", None)) in ("tr", "translate")]
                    self.assertFalse(calls, f"{source}:{node.lineno}: tr() внутри f-строки")

    def test_qm_files_are_built_from_current_ts(self):
        with tempfile.TemporaryDirectory() as folder:
            for lang in build.LANGUAGES:
                fresh = Path(folder) / f"{lang}.qm"
                subprocess.run([build.tool("pyside6-lrelease"), str(build.HERE / f"whokey_{lang}.ts"), "-qm", str(fresh)],
                               check=True, capture_output=True)
                with self.subTest(lang=lang):
                    self.assertEqual(fresh.read_bytes(), (build.HERE / f"whokey_{lang}.qm").read_bytes(),
                                     "запустите python3 translations/build.py")

    def test_switching_language(self):
        i18n.set_language("ru")
        self.assertEqual(i18n.tr("Open"), "Открыть")
        self.assertEqual(i18n.tr("Close"), "Закрыть")
        i18n.set_language("en")
        self.assertEqual(i18n.tr("Open"), "Open")

    def test_entry_count_in_both_languages(self):
        def count(n):
            return QCoreApplication.translate("MainWindow", "%n entries", "", n)
        i18n.set_language("ru")
        self.assertEqual([count(n) for n in (1, 2, 5, 11, 21, 22)],
                         ["1 запись", "2 записи", "5 записей", "11 записей", "21 запись", "22 записи"])
        i18n.set_language("en")
        self.assertEqual([count(n) for n in (0, 1, 2)], ["0 entries", "1 entry", "2 entries"])


if __name__ == "__main__":
    unittest.main()
