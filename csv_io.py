"""Импорт и экспорт паролей в CSV — чтобы переехать в WhoKey из браузера или другой программы и обратно.

Импорт понимает столбцы Chrome / Edge / Яндекс Браузера, Firefox, Bitwarden, KeePassXC
и 1Password: у каждого свои названия («username», «login_username», «Username»…).
Экспорт пишет столбцы как у Chrome (name, url, username, password, note) — такой файл
принимают и браузеры, и другие менеджеры паролей.

CSV — обычный текст: пароли в нём НЕ зашифрованы. Поэтому файл экспорта создаётся
с доступом только для владельца, а окно WhoKey советует удалить его после переноса.
"""

import csv
import os

import sites

MAX_SIZE = 20 * 1024 * 1024  # больше 20 МБ паролей не бывает — это не тот файл

# столбец записи WhoKey -> как он называется в разных программах (без учёта регистра)
COLUMNS = {
    "site": ["name", "title"],
    "url": ["url", "login_uri", "website", "web site"],
    "login": ["username", "login_username", "login", "user name", "email"],
    "password": ["password", "login_password"],
    "note": ["note", "notes", "comments"],
}
EXPORT_HEADER = ["name", "url", "username", "password", "note"]


class CsvError(Exception):
    """Файл не читается как таблица паролей — текст ошибки показывается человеку."""


def _column_numbers(header):
    """{"site": 1, "password": 3, …} — номера нужных столбцов по первой строке файла."""
    names = [name.strip().lower() for name in header]
    found = {}
    for field, variants in COLUMNS.items():
        for variant in variants:
            if variant in names:
                found[field] = names.index(variant)
                break
    return found


def read(path):
    """Записи из CSV-файла: список словарей site/login/password/note/url.

    Строки без пароля (например, заметки Bitwarden) пропускаются. CsvError — если
    файл не похож на экспорт паролей."""
    if os.path.getsize(path) > MAX_SIZE:
        raise CsvError("too_big")
    try:
        # utf-8-sig — Excel и Windows-программы пишут в начало файла невидимую метку BOM
        with open(path, encoding="utf-8-sig", newline="") as file:
            rows = list(csv.reader(file))
    except UnicodeDecodeError:
        raise CsvError("encoding")
    except csv.Error:
        raise CsvError("format")
    if not rows:
        raise CsvError("format")
    columns = _column_numbers(rows[0])
    if "password" not in columns or not ({"site", "url"} & columns.keys()):
        raise CsvError("columns")

    entries = []
    for row in rows[1:]:
        value = {field: (row[number].strip() if number < len(row) else "")
                 for field, number in columns.items()}
        password = row[columns["password"]] if columns["password"] < len(row) else ""
        if not password:
            continue
        url = sites.normalize(value.get("url", "")) or ""
        # нет названия — берём адрес сайта (у Firefox названия нет вовсе)
        name = value.get("site") or url or value.get("url", "")
        if not name:
            continue
        entries.append({"site": name, "login": value.get("login", ""), "password": password,
                        "note": value.get("note", ""), "url": url})
    return entries


def new_only(entries, existing):
    """Записи, которых ещё нет в хранилище (тот же сайт, логин и пароль) — повторный импорт не дублирует."""
    seen = {(e["site"], e["login"], e["password"]) for e in existing}
    result = []
    for entry in entries:
        key = (entry["site"], entry["login"], entry["password"])
        if key not in seen:
            seen.add(key)
            result.append(entry)
    return result


def write(path, entries):
    """Сохраняет записи в CSV. Файл доступен только владельцу (на Mac и Linux — права 600)."""
    # O_TRUNC + режим 600 сразу при создании: пароли ни на миг не лежат в файле, открытом всем
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with open(fd, "w", encoding="utf-8", newline="") as file:
        out = csv.writer(file)
        out.writerow(EXPORT_HEADER)
        for entry in entries:
            out.writerow([entry["site"], entry.get("url", ""), entry["login"], entry["password"], entry["note"]])
    try:
        os.chmod(path, 0o600)  # файл уже был — его старые права тоже сужаем
    except OSError:
        pass
