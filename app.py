"""Менеджер паролей — приложение с окнами (PySide6 / Qt).

То же шифрование, что у консольной версии (manager.py): vault.py, generator.py,
clipboard.py. Окна — в папке gui/.

Хранилище по умолчанию лежит там, где программы Mac держат свои данные:
~/Library/Application Support/EduPasswords/vault.dat (на Windows — в %APPDATA%).
Эта папка не синхронизируется с iCloud. Другой файл можно выбрать в окне входа.

Запуск: ../.venv/bin/python app.py
"""

import signal
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # чтобы найти vault.py и остальные модули рядом

from PySide6.QtCore import QLocale, QSettings, QStandardPaths, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from clipboard import Clipboard
from gui import theme
from gui.login import LANGUAGES, LoginWindow
from gui.main_window import MainWindow
import texts
from texts import set_language, t

APP_NAME = "EduPasswords"


def default_vault_path():
    folder = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    return folder / "vault.dat"


class Controller:
    """Переключает окна: вход -> главное окно."""

    def __init__(self):
        # настройки (язык, последний файл) — не секрет, пароли сюда не попадают
        self.settings = QSettings(APP_NAME, APP_NAME)
        self.clipboard = Clipboard()
        self.state = {}
        self.window = None

        # язык — только из известных: с неизвестным (кто-то поправил настройки
        # вручную) окно входа падало бы при каждом запуске
        system_lang = "ru" if QLocale.system().name().startswith("ru") else "en"
        lang = self.settings.value("language", system_lang)
        set_language(lang if lang in dict(LANGUAGES) else system_lang)

        path = default_vault_path()
        saved = self.settings.value("vault_path")
        if saved and Path(saved).parent.is_dir():
            path = Path(saved)
        elif saved and Path(saved) != path:
            # папка прошлого хранилища недоступна (например, не подключена флешка).
            # Не предлагаем создать новое на её месте — открываем хранилище
            # по умолчанию и прямо говорим, что случилось.
            self.state["notice"] = t("g_folder_missing", folder=Path(saved).parent)
        self.show_login(path)

    def _replace_window(self, window):
        # сначала показываем новое окно, потом закрываем старое — иначе
        # на мгновение не останется окон и программа решит, что пора выйти
        old, self.window = self.window, window
        window.show()
        if old is not None:
            old.close()
            old.deleteLater()

    def show_login(self, path):
        self.settings.setValue("language", texts.LANG)
        window = LoginWindow(path, self.state)
        window.restart.connect(self.show_login)
        window.opened.connect(self.show_main)
        self._replace_window(window)

    def show_main(self, vault):
        self.settings.setValue("vault_path", str(vault.path))
        self._replace_window(MainWindow(vault, self.clipboard))


def main():
    app = QApplication(sys.argv)
    # APP_NAME — имя папки с данными, его не меняем (иначе «потеряется» уже
    # созданное хранилище); видимое название программы — WhoKey
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName("WhoKey")
    app.setWindowIcon(QIcon(str(theme.ICON_FILE)))  # иконка в Dock при запуске без .app
    theme.apply(app)

    # обработчик ошибок ставим ДО создания окон — иначе ошибка при запуске
    # закрыла бы приложение молча, без всякого окна
    def on_error(kind, error, trace):
        # непредвиденная ошибка — понятное окошко вместо молчаливого падения;
        # подробности для разработчика — в Терминал
        traceback.print_exception(kind, error, trace)
        QMessageBox.critical(None, t("g_error_title"),
                             t("unexpected", error=f"{kind.__name__}: {error}"))
    sys.excepthook = on_error

    controller = Controller()

    # что бы ни случилось — при выходе не оставляем пароль в буфере обмена
    app.aboutToQuit.connect(controller.clipboard.clear_now)

    # kill, закрытие Терминала, Ctrl+\ — тоже нормальный выход с очисткой буфера.
    # Qt почти всё время занят своим циклом, и Python замечает сигнал, только
    # когда сам выполняет код, — поэтому таймер «будит» его 3 раза в секунду.
    for name in ("SIGTERM", "SIGHUP", "SIGQUIT", "SIGINT"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: app.quit())
    wake = QTimer()
    wake.timeout.connect(lambda: None)
    wake.start(300)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
