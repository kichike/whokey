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
import unicodedata
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

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
        params = {}
        for name, (low, high) in KDF_LIMITS.items():
            value = kdf[name]
            # именно целое число: JSON пропускает и Infinity, и true/false
            if type(value) is not int or not low <= value <= high:
                raise VaultError(f"bad kdf parameter {name}")
            params[name] = value
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
    # url (адрес сайта для расширения браузера) появился позже — у старых записей его нет
    return isinstance(entry, dict) and all(isinstance(entry.get(f), str) for f in ENTRY_FIELDS) \
        and isinstance(entry.get("url", ""), str)


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


def _write_file(path, text):
    """Безопасная запись: временный файл -> подмена.

    Если программа упадёт посреди записи, старый файл останется целым.
    Временный файл создаётся через mkstemp: всегда НОВЫЙ, со случайным именем,
    с правами «только владелец» (0600) и без перехода по символическим ссылкам.
    """
    folder = path.parent
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            _full_sync(f.fileno())
        os.replace(tmp, path)
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
        self.old_backup = None    # куда отложена чужая старая копия при создании

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
        salt, params, token = _read_header(path)
        key = derive_key(password, salt, params)
        try:
            data = Fernet(key).decrypt(token)
        except InvalidToken:
            raise WrongPassword()
        try:
            content = json.loads(data.decode("utf-8"))
            entries = content["entries"]
            if not isinstance(entries, list) or not all(_valid_entry(e) for e in entries):
                raise ValueError("bad entries")
            bridge_keys = content.get("bridge_keys", [])  # у хранилищ до расширения браузера его нет
            if not isinstance(bridge_keys, list) or not all(isinstance(k, str) for k in bridge_keys):
                raise ValueError("bad bridge keys")
        except (ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
            raise VaultError(str(error))
        vault = cls(path, key, salt, params, entries)
        vault.bridge_keys = bridge_keys
        return vault

    def check_password(self, password):
        """Верный ли мастер-пароль — без повторного чтения файла."""
        key = derive_key(password, self._salt, self._params)
        # compare_digest сравнивает за одинаковое время, не выдавая, где отличие
        return hmac.compare_digest(key, self._key)

    # --- сохранение ---

    def _write(self, entries, key, salt, params, bridge_keys=None):
        """Шифрует записи и сохраняет файл + резервную копию. SaveError — если не вышло."""
        content = {"entries": entries}
        bridge_keys = self.bridge_keys if bridge_keys is None else bridge_keys
        if bridge_keys:
            content["bridge_keys"] = bridge_keys
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
        """Сохраняет текущие записи как есть."""
        self._write(self.entries, self._key, self._salt, self._params)

    def change_password(self, new_password):
        """Новый мастер-пароль: новая соль, новый ключ, всё перешифровывается."""
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

    def _commit(self, entries):
        self._write(entries, self._key, self._salt, self._params)
        self.entries = entries

    def set_bridge_keys(self, keys):
        """Разрешённые расширения браузера: сначала на диск, потом в память. SaveError — если не вышло."""
        self._write(self.entries, self._key, self._salt, self._params, bridge_keys=list(keys))
        self.bridge_keys = list(keys)

    def add(self, site, login, password, note="", url=""):
        now = _now()
        entry = {"site": site, "login": login, "password": password,
                 "note": note, "url": url, "created": now, "updated": now}
        self._commit(self.entries + [entry])

    def update(self, index, **fields):
        entries = [dict(e) for e in self.entries]
        entries[index].update(fields, updated=_now())
        self._commit(entries)

    def delete(self, index):
        self._commit(self.entries[:index] + self.entries[index + 1:])

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
