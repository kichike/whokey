"""Настройки, которые человек меняет в окне «Настройки» (и запомненный выбор в генераторе).

Хранятся в обычных настройках программы (QSettings «EduPasswords») — это не секреты.
Тесты подменяют файл настроек через use_file(), чтобы не трогать настоящие.
"""

from PySide6.QtCore import QSettings

# варианты в окне «Настройки»; первое значение в списке — не по умолчанию, по умолчанию — DEFAULTS
CLEAR_CHOICES = [15, 30, 60, 90]        # секунд: через сколько пароль стирается из буфера
REVEAL_CHOICES = [5, 15, 30, 60]        # секунд: сколько виден показанный пароль
IDLE_CHOICES = [0, 1, 5, 10, 30]        # минут без действий до автоблокировки; 0 — не блокировать
DEFAULTS = {"clear_after": 30, "reveal_seconds": 15, "idle_lock_minutes": 10}

_settings = None


def use_file(path):
    """Для тестов: настройки из отдельного файла, а не настоящие."""
    global _settings
    _settings = QSettings(str(path), QSettings.IniFormat)


def _store():
    global _settings
    if _settings is None:
        _settings = QSettings("EduPasswords", "EduPasswords")
    return _settings


def _number(name, choices):
    try:
        value = int(_store().value("prefs/" + name, DEFAULTS[name]))
    except (TypeError, ValueError):
        return DEFAULTS[name]
    return value if value in choices else DEFAULTS[name]  # ручная правка файла — не повод падать


def clear_after():
    return _number("clear_after", CLEAR_CHOICES)


def reveal_seconds():
    return _number("reveal_seconds", REVEAL_CHOICES)


def idle_lock_minutes():
    return _number("idle_lock_minutes", IDLE_CHOICES)


def set_value(name, value):
    _store().setValue("prefs/" + name, value)


def generator_options():
    """Запомненные длина и наборы символов генератора: (длина, {"lower": True, …}) или None."""
    store = _store()
    length = store.value("generator/length")
    if length is None:
        return None
    try:
        kinds = {kind: store.value("generator/" + kind, "true") in (True, "true")
                 for kind in ("lower", "upper", "digits", "symbols")}
        return int(length), kinds
    except (TypeError, ValueError):
        return None


def remember_generator(length, kinds):
    store = _store()
    store.setValue("generator/length", length)
    for kind, on in kinds.items():
        store.setValue("generator/" + kind, bool(on))
