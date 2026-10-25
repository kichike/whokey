"""Перевод окон WhoKey через Qt Linguist.

Надписи в коде — на английском: tr("Open"). Русский перевод лежит
в translations/whokey_ru.ts (его правят в программе Qt Linguist:
pyside6-linguist translations/whokey_ru.ts), а приложение читает
собранный из него файл whokey_ru.qm. Собрать: python3 translations/build.py

Консольная версия (manager.py) этим не пользуется: у неё свои тексты в texts.py,
поэтому несколько общих фраз («Неверный мастер-пароль…») записаны дважды.

Надписи с числом («1 запись», «2 записи», «5 записей») — через self.tr окна:
self.tr("%n entries", "", count). Только так lupdate понимает, что у строки
есть формы для разных чисел (их перевод — в разделе с именем класса окна).
"""

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QTranslator

LANGUAGES = [("ru", "Русский"), ("en", "English")]

LANG = "en"  # текущий язык; меняется через set_language()

_installed = []  # переводчики, которые сейчас подключены к приложению


TRANSLATIONS_DIR = Path(__file__).parent.parent / "translations"  # и в собранном приложении тоже


def tr(text):
    """Надпись на текущем языке. Подстановки — после перевода: tr("Code: {code}").format(code=…)"""
    return QCoreApplication.translate("", text)


def set_language(lang):
    """Переключает язык. Окна создаются заново, поэтому подхватят новые надписи."""
    global LANG
    LANG = lang
    app = QCoreApplication.instance()
    for translator in _installed:
        if app is not None:
            app.removeTranslator(translator)
    _installed.clear()
    if app is None:
        return
    files = [(TRANSLATIONS_DIR, f"whokey_{lang}"),
             # стандартные кнопки Qt («Cancel», «Yes» в окнах-вопросах)
             (Path(QLibraryInfo.path(QLibraryInfo.TranslationsPath)), f"qtbase_{lang}")]
    for folder, name in files:
        translator = QTranslator(app)
        if translator.load(name, str(folder)):
            app.installTranslator(translator)
            _installed.append(translator)
