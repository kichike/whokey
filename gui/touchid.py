"""Вход по отпечатку пальца (Touch ID) — только macOS.

Бесплатный вариант, без аккаунта Apple Developer:
  - ключ хранилища (не мастер-пароль) лежит в Связке ключей macOS. Её шифрует
    сама система, и без вопроса она отдаёт запись только программе, которая
    её положила, — WhoKey;
  - перед тем как достать ключ, WhoKey просит приложить палец (LocalAuthentication).
Привязать запись к отпечатку на уровне системы (Secure Enclave) macOS разрешает
только приложениям с платной подписью Apple — поэтому палец проверяет сам WhoKey.

Правила:
  - после перезагрузки Mac первый вход — только по мастер-паролю;
  - при смене мастер-пароля сохранённый ключ стирается;
  - войти по мастер-паролю можно всегда.
Запись в Связке ключей — одна на файл хранилища (имя — отпечаток SHA-256 пути).
"""

import ctypes
import ctypes.util
import hashlib
import sys

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QGuiApplication

SERVICE = "WhoKey Touch ID"

try:  # PyObjC ставится только на Mac (см. requirements.txt)
    import LocalAuthentication
    import Security
    from Foundation import NSData
except ImportError:
    LocalAuthentication = Security = NSData = None


def available():
    """Можно ли пользоваться Touch ID: Mac с датчиком и включённым отпечатком."""
    if sys.platform != "darwin" or LocalAuthentication is None:
        return False
    # в автотестах окна рисуются «без экрана» — настоящее окно с отпечатком там не нужно
    if QGuiApplication.platformName() != "cocoa":
        return False
    context = LocalAuthentication.LAContext.alloc().init()
    ok, _error = context.canEvaluatePolicy_error_(
        LocalAuthentication.LAPolicyDeviceOwnerAuthenticationWithBiometrics, None)
    return bool(ok)


def boot_time():
    """Когда Mac последний раз загружался (секунды) — чтобы после перезагрузки просить пароль."""
    class Timeval(ctypes.Structure):
        _fields_ = [("sec", ctypes.c_long), ("usec", ctypes.c_int32)]
    libc = ctypes.CDLL(ctypes.util.find_library("c"))
    value = Timeval()
    size = ctypes.c_size_t(ctypes.sizeof(value))
    if libc.sysctlbyname(b"kern.boottime", ctypes.byref(value), ctypes.byref(size), None, 0) != 0:
        return 0
    return value.sec


def _query(path):
    account = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()
    return {Security.kSecClass: Security.kSecClassGenericPassword,
            Security.kSecAttrService: SERVICE,
            Security.kSecAttrAccount: account}


def _boot_of_record(path):
    """Отметка «после какой загрузки Mac сохранён ключ» — или None, если ключа нет.

    Читается из открытого поля записи (комментарий), без самого ключа: такое
    чтение macOS разрешает без вопросов. Иначе после каждого обновления WhoKey
    (подпись меняется) macOS спрашивала бы пароль Mac на каждую проверку.
    """
    if Security is None:
        return None
    query = _query(path)
    query[Security.kSecReturnAttributes] = True
    query[Security.kSecMatchLimit] = Security.kSecMatchLimitOne
    status, attributes = Security.SecItemCopyMatching(query, None)
    if status != 0 or attributes is None:
        return None
    try:
        return int(attributes.get(Security.kSecAttrComment) or 0)
    except (TypeError, ValueError):
        return 0


def is_enabled(path):
    """Включён ли вход по Touch ID для этого файла хранилища."""
    return _boot_of_record(path) is not None


def is_fresh(path):
    """Ключ сохранён после последней загрузки Mac (иначе — сначала мастер-пароль)."""
    return _boot_of_record(path) == boot_time()


def load_key(path):
    """Ключ хранилища — звать только после того, как палец подтверждён.

    Единственное чтение самого ключа: если WhoKey обновился, macOS здесь
    один раз спросит пароль Mac («Разрешать всегда» — и больше не спросит).
    """
    if not is_fresh(path):
        return None
    query = _query(path)
    query[Security.kSecReturnData] = True
    query[Security.kSecMatchLimit] = Security.kSecMatchLimitOne
    status, data = Security.SecItemCopyMatching(query, None)
    if status != 0 or data is None:
        return None
    return bytes(data)


def save_key(path, key):
    """Кладёт ключ в Связку ключей (или обновляет). False — если macOS не дала."""
    if Security is None:
        return False
    forget(path)
    item = _query(path)
    item[Security.kSecValueData] = NSData.dataWithBytes_length_(key, len(key))
    item[Security.kSecAttrComment] = str(boot_time())  # открытое поле: без ключа
    item[Security.kSecAttrLabel] = "WhoKey (Touch ID)"
    item[Security.kSecAttrAccessible] = Security.kSecAttrAccessibleWhenUnlockedThisDeviceOnly
    status, _item = Security.SecItemAdd(item, None)
    return status == 0


def forget(path):
    """Выключает вход по Touch ID для этого файла: ключ стирается из Связки ключей."""
    if Security is not None:
        Security.SecItemDelete(_query(path))


def _settings_key(path):
    return "touch_id_asked/" + hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()


def was_offered(path):
    """Спрашивали ли уже «Настроить Touch ID?» для этого файла (ответ — любой)."""
    return QSettings("EduPasswords", "EduPasswords").value(_settings_key(path), False, bool)


def set_offered(path, offered=True):
    QSettings("EduPasswords", "EduPasswords").setValue(_settings_key(path), offered)


class TouchIdPrompt(QObject):
    """Системное окошко «приложите палец». Ответ приходит сигналом finished(успех)."""

    finished = Signal(bool)

    def ask(self, reason):
        self._context = LocalAuthentication.LAContext.alloc().init()  # держим, пока ждём ответ
        self._context.setLocalizedFallbackTitle_("")  # без кнопки «Ввести пароль Mac» — у нас свой пароль

        # ответ macOS присылает из другого потока; сигнал Qt сам доставит его в окно
        def reply(success, _error):
            self.finished.emit(bool(success))

        self._context.evaluatePolicy_localizedReason_reply_(
            LocalAuthentication.LAPolicyDeviceOwnerAuthenticationWithBiometrics, reason, reply)
