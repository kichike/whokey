"""Зашифрованное хранилище паролей.

Как это устроено:
1. Мастер-пароль + случайная «соль» -> функция Argon2id -> ключ 32 байта.
   Argon2id специально медленная и требует много памяти: для владельца это
   доли секунды при входе, а перебор миллионов паролей становится очень дорогим.
   Её рекомендует официальная документация cryptography для паролей с Fernet.
2. Ключом шифруются все записи (Fernet = AES + проверка подлинности HMAC).
   Если пароль неверный или в файле изменён хоть один байт — расшифровка
   не удастся, подделать файл незаметно нельзя.
3. Мастер-пароль нигде не сохраняется. Соль и настройки Argon2id лежат
   в файле открыто — это не секрет, они нужны, чтобы получить тот же ключ.

Служебные файлы:
  .vault.dat.bak — резервная копия (тоже зашифрована) на случай порчи основного.
                   Скрытая, лежит рядом с хранилищем — так она переезжает вместе
                   с ним, а пользователь видит в папке один файл.
  замок          — пустой файл, не даёт открыть хранилище в двух окнах сразу.
                   Лежит в папке программы (locks/), пользователю не нужен.

Своей криптографии здесь нет — только проверенная библиотека cryptography.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

import sync

FORMAT = "edu-password-vault"
VERSION = 1

# Настройки Argon2id — второй рекомендованный вариант из RFC 9106
# (64 МБ памяти, 3 прохода, 4 потока). Первый вариант требует 2 ГБ памяти
# при каждом входе — хранилище могло бы не открыться на слабом компьютере.
# Настройки пишутся в файл, поэтому их можно усилить, не ломая старые файлы.
KDF_PARAMS = {"iterations": 3, "lanes": 4, "memory_cost": 2 ** 16}  # memory_cost — в КБ
SALT_SIZE = 16  # 128 бит — как в документации cryptography

# Допустимые настройки при открытии чужого/старого файла. Без проверки
# подменённый файл мог бы уронить программу (lanes = 0) или заставить её
# занять всю память. Верхний предел памяти — 256 МБ.
KDF_LIMITS = {"iterations": (1, 10), "lanes": (1, 16), "memory_cost": (2 ** 13, 2 ** 18)}
ACCESS_LOG_SIZE = 200  # столько последних выдач паролей расширению помнит журнал
REPLACE_ATTEMPTS, REPLACE_PAUSE = 10, 0.2  # файл занят другой программой: ждём до 2 секунд
MAX_FILE_SIZE = 10 * 1024 * 1024  # хранилище больше 10 МБ (~25 000 записей) — точно не наше

ENTRY_FIELDS = ["site", "login", "password", "note", "created", "updated"]


class VaultError(Exception):
    """Файл не похож на хранилище или повреждён так, что его не прочитать."""


class WrongPassword(Exception):
    """Неверный мастер-пароль (или зашифрованная часть файла изменена)."""


class VaultLocked(Exception):
    """Хранилище уже открыто другой копией программы."""


class SaveError(Exception):
    """Не удалось записать файл (диск полон, нет прав...). Изменение не применено."""


class PasswordChangedElsewhere(SaveError):
    """Файл зашифрован другим ключом: мастер-пароль сменили на другом устройстве.
    Записывать нельзя — старый ключ перезаписал бы чужие изменения. Нужно войти заново."""


class FileBusy(SaveError):
    """Файл сейчас не прочитать (облако ещё докачивает его или он повреждён) — перезаписывать
    вслепую нельзя, вдруг там чужие изменения. Обычно проходит за несколько секунд."""


def derive_key(password, salt, params):
    """Мастер-пароль -> ключ для Fernet."""
    # Одинаково выглядящий пароль может прийти в разной форме: «й» одним
    # символом или «и» + значок краткости. Приводим к одной форме (NFC),
    # иначе получились бы разные ключи и пароль «перестал бы подходить».
    password = unicodedata.normalize("NFC", password)
    kdf = Argon2id(salt=salt, length=32, **params)
    key = kdf.derive(password.encode("utf-8"))
    return base64.urlsafe_b64encode(key)  # Fernet хочет ключ в таком виде


def backup_path(path):
    """Резервная копия — скрытый файл рядом с хранилищем: .vault.dat.bak."""
    return Path(path).with_name("." + Path(path).name + ".bak")


def _set_hidden(path, hidden):
    """На Windows точка в начале имени файл не прячет — нужна пометка «скрытый».
    На Mac и Linux ничего не делает: там скрывает сама точка."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x2 if hidden else 0x80)  # HIDDEN / NORMAL


def app_data_dir():
    """Папка программы для служебных файлов (та же, где хранилище по умолчанию)."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "EduPasswords"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "EduPasswords"
    return Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "EduPasswords"


def lock_path(path):
    """Файл-замок для хранилища — в папке программы, имя — отпечаток пути к хранилищу."""
    key = unicodedata.normalize("NFC", str(Path(path).resolve()))
    if sys.platform in ("darwin", "win32"):
        key = key.lower()  # там «Vault.dat» и «vault.dat» — обычно один и тот же файл
    return app_data_dir() / "locks" / (hashlib.sha256(key.encode("utf-8")).hexdigest()[:32] + ".lock")


def tidy_old_files(path):
    """Файлы от прежних версий программы, которые лежали рядом с хранилищем:
    копию vault.dat.bak переименовываем в скрытую .vault.dat.bak, пустой
    замок vault.dat.lock удаляем (замок теперь в папке программы).
    Вызывать до любых проверок «есть ли копия». Ошибки не страшны — тогда
    старые файлы просто остаются как были."""
    path = Path(path)
    old_backup, new_backup = path.with_name(path.name + ".bak"), backup_path(path)
    try:
        if old_backup.is_file() and not new_backup.exists():
            os.rename(old_backup, new_backup)
            _set_hidden(new_backup, True)
    except OSError:
        pass
    old_lock = path.with_name(path.name + ".lock")
    try:
        if old_lock.is_file() and old_lock.stat().st_size == 0:
            os.remove(old_lock)
    except OSError:
        pass


def in_icloud_folder(path):
    """Лежит ли файл в «Рабочем столе» или «Документах», которые macOS
    синхронизирует с iCloud (если эта настройка включена)."""
    cloud = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    for name in ("Desktop", "Documents"):
        if (cloud / name).exists():
            try:
                Path(path).resolve().relative_to((Path.home() / name).resolve())
                return True
            except ValueError:
                pass
    return False


def cloud_folders():
    """Папки облаков, которые есть на этом компьютере: (название, папка). Для кнопки переноса."""
    home = Path.home()
    known = [("iCloud Drive", home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"),
             ("Dropbox", home / "Dropbox"), ("Google Drive", home / "Google Drive"),
             ("OneDrive", home / "OneDrive"), ("Яндекс Диск", home / "Yandex.Disk.localized"),
             ("Яндекс Диск", home / "YandexDisk"), ("Яндекс Диск", home / "Yandex.Disk")]
    storage = home / "Library" / "CloudStorage"  # новое место облаков на macOS
    if storage.is_dir():
        for folder in sorted(storage.iterdir()):
            known.append((folder.name.split("-")[0], folder))
    return [(name, folder) for name, folder in known if folder.is_dir()]


def cloud_name(path):
    """Название облака, в папке которого лежит файл, или None."""
    try:
        resolved = Path(path).resolve()
    except OSError:
        return None
    for name, folder in cloud_folders():
        try:
            resolved.relative_to(folder.resolve())
            return name
        except (ValueError, OSError):
            continue
    # папку облака можно выбрать при установке: узнаём и по названию в пути
    parts = " ".join(resolved.parts[:-1]).lower()
    for mark, name in (("yandex", "Яндекс Диск"), ("яндекс", "Яндекс Диск"), ("dropbox", "Dropbox"),
                       ("onedrive", "OneDrive"), ("google drive", "Google Drive"), ("googledrive", "Google Drive")):
        if mark in parts:
            return name
    return "iCloud Drive" if in_icloud_folder(path) else None


def lock(path):
    """Запрещает второй копии программы открыть то же хранилище.

    Возвращает номер открытого файла-замка — его держим до выхода
    (при выходе система снимет замок сама). VaultLocked — если занято.
    """
    lock_file = lock_path(path)
    lock_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # O_NOFOLLOW — не идти по символической ссылке, если её подсунули вместо замка
    fd = os.open(lock_file, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise VaultLocked()
    return fd


# --- Чтение файла ---

def _short_int(text):
    """Число из миллионов цифр Python 3.9 разбирает очень долго (программа
    «зависает» на подделанном файле) — такие сразу отвергаем."""
    if len(text) > 20:
        raise ValueError("number too long")
    return int(text)


def _no_constant(name):
    """JSON в Python понимает Infinity и NaN — в хранилище им не место."""
    raise ValueError(f"{name} is not allowed")


def _kdf_params(kdf):
    """Настройки Argon2id из словаря — только известные и в разумных пределах."""
    params = {}
    for name, (low, high) in KDF_LIMITS.items():
        value = kdf[name]
        # именно целое число: JSON пропускает и Infinity, и true/false
        if type(value) is not int or not low <= value <= high:
            raise VaultError(f"bad kdf parameter {name}")
        params[name] = value
    return params


def _read_header(path):
    """Проверяет открытую часть файла и возвращает (соль, настройки, шифровку)."""
    try:
        if os.path.getsize(path) > MAX_FILE_SIZE:
            raise VaultError("file too large")
        with open(path, encoding="utf-8") as f:
            header = json.load(f, parse_int=_short_int, parse_constant=_no_constant)
        if header.get("format") != FORMAT:
            raise VaultError("not a vault")
        if header.get("version") != VERSION:
            raise VaultError("unsupported version")
        kdf = header["kdf"]
        if kdf.get("name") != "argon2id":
            raise VaultError("unknown kdf")
        params = _kdf_params(kdf)
        salt = base64.b64decode(header["salt"], validate=True)
        if len(salt) < SALT_SIZE:
            raise VaultError("salt too short")
        token = header["data"].encode("ascii")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        # ValueError включает и ошибку разбора JSON, и битый base64;
        # RecursionError — файл вида [[[[...]]]] с огромной вложенностью
        raise VaultError(str(error))
    return salt, params, token


def backup_is_relevant(path):
    """Стоит ли предлагать восстановление из резервной копии.

    Основной файл и копия пишутся вместе и имеют одну и ту же соль.
    Если соль разная — копия осталась от прежнего мастер-пароля (однажды
    не обновилась), и сказать «основной файл повреждён» было бы неправдой:
    человек просто ввёл старый пароль. Восстановление откатило бы хранилище
    к старой версии.
    """
    try:
        main_salt = _read_header(path)[0]
    except VaultError:
        return True  # основного файла нет или он не читается — копия нужна
    try:
        return _read_header(backup_path(path))[0] == main_salt
    except VaultError:
        return False


def is_readable(path):
    """Похож ли файл на целое хранилище (открытая часть читается) — без пароля."""
    try:
        _read_header(path)
        return True
    except VaultError:
        return False


def open_backup(path, password):
    """Открывает резервную копию, если её стоит предлагать. None — нет/не подошла."""
    if not backup_path(path).exists() or not backup_is_relevant(path):
        return None
    try:
        return Vault.open(backup_path(path), password)
    except (WrongPassword, VaultError):
        return None


def _valid_entry(entry):
    # url (адрес сайта для расширения браузера) появился позже — у старых записей его нет,
    # как и полей синхронизации: id, modified, prevs (sync.upgrade добавит их при открытии)
    if not (isinstance(entry, dict) and all(isinstance(entry.get(f), str) for f in ENTRY_FIELDS)
            and isinstance(entry.get("url", ""), str)):
        return False
    if "id" not in entry:
        return True
    return isinstance(entry["id"], str) and type(entry.get("modified")) is int \
        and isinstance(entry.get("prevs"), list) and all(type(v) is int for v in entry["prevs"])


def _valid_deleted(deleted):
    return isinstance(deleted, dict) and all(
        isinstance(mark, dict) and type(mark.get("at")) is int and isinstance(mark.get("seen"), list)
        and all(type(v) is int for v in mark["seen"]) for mark in deleted.values())


def _digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_state(path):
    """Что сейчас за файл: (отпечаток, (время, размер)) или (None, None), если его не прочитать.
    Снимать ДО чтения содержимого: если файл изменится между этими шагами, мы лишь прочитаем
    его ещё раз. А снятый после чтения отпечаток выдал бы неувиденную версию за увиденную."""
    try:
        stat = os.stat(path)
        return _digest(path), (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None, None


# --- Запись файла ---

def _full_sync(fd):
    """Дождаться, пока данные реально окажутся на диске."""
    # На Mac обычный fsync не сбрасывает кэш самого диска — для этого есть F_FULLFSYNC
    if sys.platform == "darwin":
        import fcntl
        try:
            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
            return
        except OSError:
            pass
    os.fsync(fd)


def _sync_folder(folder):
    """Чтобы сама подмена файла (запись в папке) тоже точно попала на диск."""
    if sys.platform == "win32":
        return
    fd = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _replace(tmp, path):
    """Подмена файла. На Windows её не дают, пока файл открыт другой программой, а программа
    синхронизации (Яндекс Диск) открывает его для отправки в облако: это длится мгновения."""
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(REPLACE_PAUSE)


def _write_file(path, text):
    """Безопасная запись: временный файл -> подмена.

    Если программа упадёт посреди записи, старый файл останется целым.
    Временный файл создаётся через mkstemp: всегда НОВЫЙ, со случайным именем,
    с правами «только владелец» (0600) и без перехода по символическим ссылкам.
    """
    folder = path.parent
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + path.name + ".", suffix=".tmp")
    try:
        # newline="\n": на Windows Python иначе заменил бы \n на \r\n, и в файле оказалось бы не то,
        # что мы считаем записанным: WhoKey принимал бы собственное сохранение за чужие изменения
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            _full_sync(f.fileno())
        _replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _sync_folder(folder)


class Vault:
    """Открытое хранилище: записи в памяти + ключ для сохранения."""

    def __init__(self, path, key, salt, params, entries):
        self.path = Path(path)
        self._key = key
        self._salt = salt
        self._params = params
        self.entries = entries  # список словарей: site, login, password, note, ...
        # отпечатки (SHA-256) ключей расширений браузера, которым разрешён доступ.
        # Лежат внутри зашифрованных данных: подменить их можно, только зная мастер-пароль
        self.bridge_keys = []
        self.backup_error = None  # почему не обновилась резервная копия (если так)
        self.header_repaired = False  # открытый заголовок не совпал с копией внутри шифровки
        # кому и когда расширение браузера получило пароль: [{"time", "site", "login"}], новые в конце
        self.access_log = []
        # номер сохранения (растёт при каждой записи) — чтобы заметить подмену файла старой копией
        self.generation = 0
        self.on_saved = None  # вызывается с номером после каждой записи (WhoKey запоминает его)
        # записи изменились при слиянии с файлом, порядок мог стать другим: окно должно перерисовать
        # таблицу, иначе строка на экране указывала бы на чужую запись
        self.on_merged = None
        self.old_backup = None    # куда отложена чужая старая копия при создании
        self.deleted = {}         # что удалено: номер записи -> какие её версии (см. sync.py)
        self.bridge_keys_at = 0   # когда менялся список расширений: новый список заменяет старый целиком
        self.access_log_cleared = ""  # когда очищали журнал (чтобы старые строки не вернулись с другого устройства)
        self._seen = None         # отпечаток файла, который мы читали или записали последним
        self._stat = None         # время и размер этого файла: дешёвая проверка «не менялся ли»

    # --- создание и открытие ---

    @classmethod
    def create(cls, path, password):
        """Новое пустое хранилище. SaveError — если файл не записать."""
        salt = secrets.token_bytes(SALT_SIZE)
        vault = cls(path, derive_key(password, salt, KDF_PARAMS), salt, dict(KDF_PARAMS), [])
        # Если рядом лежит резервная копия прежнего хранилища — НЕ затираем её:
        # в ней могут быть все пароли (например, основной файл случайно удалили).
        backup = backup_path(path)
        if backup.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            vault.old_backup = backup.with_name(f"{backup.name}.old-{stamp}")
            try:
                backup.rename(vault.old_backup)
            except OSError as error:
                raise SaveError(error.strerror or str(error))
        vault.save()
        return vault

    @classmethod
    def open(cls, path, password):
        """Открывает хранилище. WrongPassword — если пароль не подошёл."""
        state = _file_state(path)
        salt, params, token = _read_header(path)
        vault = cls._decrypt(path, derive_key(password, salt, params), salt, params, token)
        vault._seen, vault._stat = state
        return vault

    @classmethod
    def open_with_key(cls, path, key):
        """Открывает хранилище готовым ключом (вход по Touch ID: ключ хранится в Связке ключей).
        WrongPassword — если ключ не подошёл (например, мастер-пароль сменили)."""
        state = _file_state(path)
        salt, params, token = _read_header(path)
        vault = cls._decrypt(path, key, salt, params, token)
        vault._seen, vault._stat = state
        return vault

    @classmethod
    def _decrypt(cls, path, key, salt, params, token):
        try:
            data = Fernet(key).decrypt(token)
        except (InvalidToken, ValueError, TypeError):  # ValueError, TypeError — ключ не того вида
            raise WrongPassword()
        try:
            content = json.loads(data.decode("utf-8"))
            entries = content["entries"]
            if not isinstance(entries, list) or not all(_valid_entry(e) for e in entries):
                raise ValueError("bad entries")
            bridge_keys = content.get("bridge_keys", [])  # у хранилищ до расширения браузера его нет
            if not isinstance(bridge_keys, list) or not all(isinstance(k, str) for k in bridge_keys):
                raise ValueError("bad bridge keys")
            # журнал выдач паролей расширению и номер сохранения (с версии 1.4.2)
            access_log = content.get("access_log", [])
            if not isinstance(access_log, list) or not all(
                    isinstance(item, dict) and all(isinstance(item.get(k), str) for k in ("time", "site", "login"))
                    for item in access_log):
                raise ValueError("bad access log")
            generation = content.get("generation", 0)
            if type(generation) is not int or generation < 0:
                raise ValueError("bad generation")
            # поля синхронизации (с версии 1.7)
            deleted = content.get("deleted", {})
            bridge_keys_at = content.get("bridge_keys_at", 0)
            log_cleared = content.get("access_log_cleared", "")
            if not _valid_deleted(deleted) or type(bridge_keys_at) is not int or not isinstance(log_cleared, str):
                raise ValueError("bad sync fields")
            # Копия соли и настроек Argon2id внутри шифровки (с версии 1.4.2). Открытый
            # заголовок может испортить или подменить кто угодно: тогда хранилище открылось бы
            # ключом из Touch ID, при сохранении соль из заголовка ушла бы в файл и копию —
            # и мастер-пароль перестал бы подходить навсегда. Верим копии внутри шифровки.
            inner = content.get("kdf")
            repaired = False
            if inner is not None:
                inner_salt = base64.b64decode(inner["salt"], validate=True)
                inner_params = _kdf_params(inner["params"])
                if len(inner_salt) < SALT_SIZE:
                    raise ValueError("salt too short")
                repaired = (inner_salt, inner_params) != (salt, params)
                salt, params = inner_salt, inner_params
        except (ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
            raise VaultError(str(error))
        vault = cls(path, key, salt, params, sync.upgrade(entries))
        vault.deleted = deleted
        vault.bridge_keys_at = bridge_keys_at
        vault.access_log_cleared = log_cleared
        vault.bridge_keys = bridge_keys
        vault.access_log = access_log[-ACCESS_LOG_SIZE:]
        vault.generation = generation
        vault.header_repaired = repaired  # заголовок не совпал с копией — исправится при сохранении
        return vault

    @property
    def key(self):
        """Ключ шифрования — чтобы положить его в Связку ключей для входа по Touch ID."""
        return self._key

    def check_password(self, password):
        """Верный ли мастер-пароль — без повторного чтения файла."""
        key = derive_key(password, self._salt, self._params)
        # compare_digest сравнивает за одинаковое время, не выдавая, где отличие
        return hmac.compare_digest(key, self._key)

    # --- сохранение ---

    def _write(self, entries, key, salt, params, bridge_keys=None, access_log=None, deleted=None):
        """Шифрует записи и сохраняет файл + резервную копию. SaveError — если не вышло."""
        generation = self.generation + 1
        deleted = self.deleted if deleted is None else deleted
        content = {"entries": entries,
                   "kdf": {"salt": base64.b64encode(salt).decode("ascii"), "params": params},
                   "generation": generation}
        if deleted:
            content["deleted"] = deleted
        if self.bridge_keys_at:
            content["bridge_keys_at"] = self.bridge_keys_at
        if self.access_log_cleared:
            content["access_log_cleared"] = self.access_log_cleared
        bridge_keys = self.bridge_keys if bridge_keys is None else bridge_keys
        if bridge_keys:
            content["bridge_keys"] = bridge_keys
        access_log = self.access_log if access_log is None else access_log
        if access_log:
            content["access_log"] = access_log
        data = json.dumps(content, ensure_ascii=False).encode("utf-8")
        header = {
            "format": FORMAT,
            "version": VERSION,
            "kdf": {"name": "argon2id", **params},
            "salt": base64.b64encode(salt).decode("ascii"),
            # при каждом сохранении Fernet берёт новый случайный вектор,
            # поэтому даже одинаковые данные шифруются по-разному
            "data": Fernet(key).encrypt(data).decode("ascii"),
        }
        text = json.dumps(header, indent=2)
        try:
            _write_file(self.path, text)
        except OSError as error:
            raise SaveError(error.strerror or str(error))
        self.generation = generation
        # отпечаток — того, что записали мы, а не того, что лежит в файле сейчас
        self._seen = hashlib.sha256(text.encode("utf-8")).hexdigest()
        try:
            stat = os.stat(self.path)
            self._stat = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            self._stat = None
        if self.on_saved is not None:
            self.on_saved(generation)
        # Резервная копия — та же зашифрованная версия. Если не записалась,
        # это не повод отменять уже сохранённое изменение, но человек должен
        # об этом узнать (менеджер покажет предупреждение).
        self.backup_error = None
        backup = backup_path(self.path)
        try:
            if backup.exists():
                _set_hidden(backup, False)  # Windows может не дать подменить скрытый файл
            _write_file(backup, text)
            _set_hidden(backup, True)
        except OSError as error:
            self.backup_error = error.strerror or str(error)

    def save(self):
        """Сохраняет текущие записи как есть, без слияния с файлом: для нового хранилища,
        восстановления из копии и переноса в другую папку."""
        self._write(self.entries, self._key, self._salt, self._params)

    # --- синхронизация с файлом (его могло изменить другое устройство), см. sync.py ---

    def _read_other(self):
        """Версия хранилища из файла, если он изменился с прошлого раза. None — не менялся или его нет."""
        try:
            stat = os.stat(self.path)
            digest = _digest(self.path)
        except FileNotFoundError:
            return None  # облако сейчас его перекладывает, а наша версия цела
        except PermissionError:
            raise FileBusy("the vault file is held by another program")  # на Windows: программа синхронизации
        except OSError as error:
            raise SaveError(error.strerror or str(error))
        if digest == self._seen:
            self._stat = (stat.st_mtime_ns, stat.st_size)  # время изменилось, содержимое то же
            return None
        try:
            salt, params, token = _read_header(self.path)
            other = self._decrypt(self.path, self._key, salt, params, token)
        except WrongPassword:
            raise PasswordChangedElsewhere("the master password was changed on another device")
        except VaultError:
            raise FileBusy("the vault file cannot be read right now")
        other._seen, other._stat = digest, (stat.st_mtime_ns, stat.st_size)
        return other

    def _absorb(self, other):
        """Слить чужую версию с нашей. Память теперь — итог. True, если в файле не всё, что есть у нас."""
        entries, deleted = sync.merge_entries(self.entries, self.deleted, other.entries, other.deleted)
        # весь список целиком: иначе отключённое расширение вернулось бы с другого устройства
        ours, theirs = (self.bridge_keys_at, sorted(self.bridge_keys)), (other.bridge_keys_at, sorted(other.bridge_keys))
        keys = other.bridge_keys if theirs > ours else self.bridge_keys
        keys_at = max(other.bridge_keys_at, self.bridge_keys_at)
        cleared = max(other.access_log_cleared, self.access_log_cleared)
        log = sync.merge_log(self.access_log, other.access_log, cleared, ACCESS_LOG_SIZE)
        behind = (not sync.same_entries(entries, other.entries) or set(deleted) != set(other.deleted)
                  or keys_at != other.bridge_keys_at or sorted(keys) != sorted(other.bridge_keys)
                  or sorted(map(str, log)) != sorted(map(str, other.access_log[-ACCESS_LOG_SIZE:]))
                  or cleared != other.access_log_cleared)
        changed = [e["id"] for e in self.entries] != [e["id"] for e in entries] or not sync.same_entries(self.entries, entries)
        self.entries, self.deleted, self.bridge_keys = entries, deleted, keys
        self.bridge_keys_at, self.access_log, self.access_log_cleared = keys_at, log, cleared
        self.generation = max(self.generation, other.generation)
        self._seen, self._stat = other._seen, other._stat
        if self.on_saved is not None:
            self.on_saved(self.generation)
        if changed and self.on_merged is not None:
            self.on_merged()
        return behind

    def _pull(self):
        """Перед любым изменением: забрать то, что записало другое устройство."""
        other = self._read_other()
        if other is not None:
            self._absorb(other)

    def file_changed(self):
        """Дешёвая проверка «файл изменился?»: только время и размер, без чтения."""
        try:
            stat = os.stat(self.path)
        except OSError:
            return False
        return (stat.st_mtime_ns, stat.st_size) != self._stat

    def sync(self):
        """Подхватить изменения с другого устройства. True — записи в памяти изменились.
        Если у нас есть то, чего нет в файле (облако затёрло его чужой версией), дописывает файл."""
        other = self._read_other()
        if other is None:
            return False
        before = self.entries
        behind = self._absorb(other)
        changed = not sync.same_entries(before, self.entries)
        if behind:
            self._write(self.entries, self._key, self._salt, self._params)
        return changed

    def merge_copy(self, path):
        """Влить копию, которую создало облако при конфликте («vault (1).dat»).
        False — это другое хранилище или другой пароль: её не трогаем."""
        try:
            other = Vault.open_with_key(path, self._key)
        except (WrongPassword, VaultError, OSError):
            return False
        self._pull()
        seen, stat = self._seen, self._stat
        self._absorb(other)
        self._seen, self._stat = seen, stat  # наш файл эта копия не меняла
        self._write(self.entries, self._key, self._salt, self._params)
        return True

    def is_own_copy(self, path):
        """Расшифровывается ли файл нашим ключом: только тогда это копия именно этого хранилища."""
        try:
            Vault.open_with_key(path, self._key)
            return True
        except (WrongPassword, VaultError, OSError):
            return False

    def conflict_copies(self):
        """Файлы рядом с хранилищем, похожие на копии от облака: «vault (Egor's conflicted copy).dat»,
        «vault 2.dat», «vault-DESKTOP.dat». Своя ли это копия, решает merge_copy: чужую не расшифровать."""
        stem, suffix = self.path.stem, self.path.suffix
        try:
            names = os.listdir(self.path.parent)
        except OSError:
            return []
        found = []
        stem = unicodedata.normalize("NFC", stem)  # Mac и Windows хранят «й» в именах файлов по-разному
        for name in names:
            plain = unicodedata.normalize("NFC", name)
            rest = plain[len(stem):-len(suffix)] if suffix and plain.startswith(stem) and plain.endswith(suffix) else ""
            if rest and not rest[0].isalnum():
                found.append(self.path.with_name(name))
        return sorted(found)

    def index_of(self, entry_id):
        """Номер записи в списке по её постоянному номеру или None: порядок мог измениться при слиянии."""
        for index, entry in enumerate(self.entries):
            if entry["id"] == entry_id:
                return index
        return None

    def change_password(self, new_password):
        """Новый мастер-пароль: новая соль, новый ключ, всё перешифровывается."""
        self._pull()  # старым ключом — пока файл ещё можно прочитать
        salt = secrets.token_bytes(SALT_SIZE)
        params = dict(KDF_PARAMS)
        key = derive_key(new_password, salt, params)
        self._write(self.entries, key, salt, params)
        # меняем ключ в памяти, только когда файл уже записан
        self._key, self._salt, self._params = key, salt, params
        if self.backup_error:
            # Копия осталась зашифрованной СТАРЫМ паролем. Если пароль меняли
            # из-за утечки, такая копия опасна — лучше удалить её совсем.
            try:
                os.remove(backup_path(self.path))
            except OSError:
                pass

    # --- записи ---
    # Сначала сохраняем НОВЫЙ список на диск, и только если получилось —
    # заменяем список в памяти. Иначе при ошибке записи программа
    # показывала бы изменения, которых на диске нет.

    def _commit(self, entries, deleted=None):
        self._write(entries, self._key, self._salt, self._params, deleted=deleted)
        self.entries = entries
        if deleted is not None:
            self.deleted = deleted

    def log_access(self, site, login):
        """Запись в журнал: расширение получило пароль от site для login. SaveError — если не записалось."""
        self._pull()
        log = (self.access_log + [{"time": _now(), "site": site, "login": login}])[-ACCESS_LOG_SIZE:]
        self._write(self.entries, self._key, self._salt, self._params, access_log=log)
        self.access_log = log

    def clear_access_log(self):
        self._pull()
        self.access_log_cleared = max(self.access_log_cleared, _now())
        self._write(self.entries, self._key, self._salt, self._params, access_log=[])
        self.access_log = []

    def set_bridge_keys(self, keys):
        """Разрешённые расширения браузера: сначала на диск, потом в память. SaveError — если не вышло."""
        self._pull()
        self.bridge_keys_at = max(sync.now_ms(), self.bridge_keys_at + 1)
        self._write(self.entries, self._key, self._salt, self._params, bridge_keys=list(keys))
        self.bridge_keys = list(keys)

    def add(self, site, login, password, note="", url=""):
        self.add_many([{"site": site, "login": login, "password": password, "note": note, "url": url}])

    def add_many(self, entries):
        """Несколько записей одним сохранением (импорт из CSV): либо все, либо ни одной."""
        self._pull()
        now, version = _now(), sync.now_ms()
        fresh = [dict(entry, created=now, updated=now, id=sync.new_id(), modified=version, prevs=[]) for entry in entries]
        self._commit(self.entries + fresh)

    def _apply_then_merge(self, entries, deleted):
        """Правка — поверх той версии, которую видел человек, и только потом слияние с файлом.
        В обратном порядке правка молча затёрла бы чужую, которой человек не видел; а так
        две независимые правки — обычный конфликт, и обе остаются. Не вышло — всё как было."""
        names = ("entries", "deleted", "bridge_keys", "bridge_keys_at", "access_log", "access_log_cleared",
                 "generation", "_seen", "_stat")
        before = {name: getattr(self, name) for name in names}
        self.entries, self.deleted = entries, deleted
        try:
            self._pull()
            self._write(self.entries, self._key, self._salt, self._params)
        except SaveError:
            for name, value in before.items():
                setattr(self, name, value)
            raise

    def update_id(self, entry_id, base=None, **fields):
        """Правка записи по постоянному номеру: пока был открыт диалог, порядок мог измениться.
        base — какую запись правил человек: если её тем временем удалили на другом устройстве,
        правка важнее удаления, и запись вернётся."""
        index = self.index_of(entry_id)
        entries = [dict(e) for e in self.entries]
        if index is None:
            if base is None:
                raise KeyError(entry_id)
            entries.append(dict(base))
            index = len(entries) - 1
        entries[index] = sync.touched(dict(entries[index], **fields, updated=_now()))
        self._apply_then_merge(entries, {key: mark for key, mark in self.deleted.items() if key != entry_id})

    def update(self, index, **fields):
        self.update_id(self.entries[index]["id"], **fields)

    def delete_id(self, entry_id):
        index = self.index_of(entry_id)
        if index is None:
            return  # её уже удалили на другом устройстве
        entries = self.entries[:index] + self.entries[index + 1:]
        self._apply_then_merge(entries, dict(self.deleted, **{entry_id: sync.tombstone(self.entries[index])}))

    def delete(self, index):
        self.delete_id(self.entries[index]["id"])

    def search(self, text):
        """Номера записей, где text встречается в сайте, логине или заметке."""
        text = text.lower()
        return [i for i, entry in enumerate(self.entries)
                if text in entry["site"].lower()
                or text in entry["login"].lower()
                or text in entry["note"].lower()
                or text in entry.get("url", "").lower()]


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")
