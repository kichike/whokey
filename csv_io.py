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
import tempfile
from pathlib import Path

import sites
from regular_file import NotRegularFile, open_regular

# с запасом меньше предела хранилища (vault.MAX_FILE_SIZE): шифрование раздувает данные почти вдвое
MAX_SIZE = 5 * 1024 * 1024
MAX_ROWS = 50_000

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
    try:
        fd = open_regular(path)
    except NotRegularFile:
        raise CsvError("format")
    if os.fstat(fd).st_size > MAX_SIZE:
        os.close(fd)
        raise CsvError("too_big")
    try:
        # utf-8-sig — Excel и Windows-программы пишут в начало файла невидимую метку BOM
        rows = []
        with open(fd, encoding="utf-8-sig", newline="") as file:
            for row in csv.reader(file):
                rows.append(row)
                if len(rows) > MAX_ROWS:
                    raise CsvError("too_big")
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
        # только сайт: браузеры выгружают длинные ссылки на страницу входа, открывать их незачем
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
    # Новый файл с правами 600 и подмена в конце: пароли ни на миг не лежат в файле, открытом всем,
    # а на месте выбранного файла ссылка или канал не уведут их в другое место и не повесят программу.
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8", newline="") as file:
            out = csv.writer(file)
            out.writerow(EXPORT_HEADER)
            for entry in entries:
                out.writerow([entry["site"], entry.get("url", ""), entry["login"], entry["password"], entry["note"]])
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
