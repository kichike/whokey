"""Слияние двух версий хранилища — для синхронизации через облачную папку.

Хранилище — один зашифрованный файл, который облако возит между устройствами. Если на
одном компьютере добавили запись, а на другом в это время изменили другую, простая
перезапись файла потеряла бы одну из правок. Поэтому перед каждым сохранением WhoKey
читает файл и сливает его со своими записями. Главное правило: пароль нельзя потерять.

Как отличить «уже видели и изменили» от «изменили независимо», не доверяя часам устройств:
у записи есть номер версии (modified) и список предыдущих версий (prevs).
  - версия одной записи есть в истории другой — другая просто новее, старую можно забыть;
  - иначе это настоящий конфликт: остаются обе, старая — отдельной записью с пометкой ⚠.
Удаление помнит, какие версии удалены (seen). Версия из этого списка не воскреснет,
а правка, которой удалявшее устройство не видело, останется.

Модуль без интерфейса и без файлов: только словари записей.
"""

import hashlib
import json
import secrets
import time
from datetime import datetime, timezone

MAX_PREVS = 16             # сколько прошлых версий записи помнить
TOMBSTONE_MS = 365 * 24 * 3600 * 1000  # пометки об удалении старше года забываем
CONTENT = ("site", "login", "password", "note", "url")  # что видит человек — по этому сравниваем версии


def now_ms():
    return int(time.time() * 1000)


def new_id():
    return secrets.token_hex(16)


def _stamp_ms(text):
    try:
        # как UTC, а не местное время: иначе на компьютерах в разных часовых поясах
        # у одной и той же старой записи получились бы разные версии
        return int(datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp() * 1000)
    except (ValueError, OverflowError, OSError):
        return 0


def upgrade(entries):
    """Записям из старых версий WhoKey — номер и версия.

    Номер считается из самой записи, а не случайный: иначе два устройства, обновившие один и
    тот же файл, выдали бы одной записи разные номера, и все записи задвоились бы.
    Одинаковые по этим полям записи различает порядковый номер среди таких же."""
    result, seen = [], {}
    for entry in entries:
        if "id" in entry:
            result.append(entry)
            continue
        base = "\0".join((entry["created"], entry["site"], entry["login"]))
        number = seen[base] = seen.get(base, -1) + 1
        digest = hashlib.sha256(f"{base}\0{number}".encode("utf-8")).hexdigest()[:32]
        result.append(dict(entry, id=digest, modified=_stamp_ms(entry["updated"]), prevs=[]))
    return result


def touched(entry):
    """Запись после правки: новая версия, старая — в истории."""
    prevs = (entry["prevs"] + [entry["modified"]])[-MAX_PREVS:]
    return dict(entry, modified=max(now_ms(), entry["modified"] + 1), prevs=prevs)


def tombstone(entry):
    """Пометка об удалении: какие версии записи удалены."""
    return {"at": now_ms(), "seen": (entry["prevs"] + [entry["modified"]])[-MAX_PREVS:]}


def _content(entry):
    return tuple(entry.get(field, "") for field in CONTENT)


def _history(*lists):
    return sorted(set().union(*lists))[-MAX_PREVS:]


def _conflict_copy(entry):
    """Проигравшая версия — отдельной записью. Номер считается из версии, поэтому на всех
    устройствах получается одна и та же копия, а не по копии на устройство."""
    digest = hashlib.sha256(f"{entry['id']}\0{entry['modified']}\0{_content(entry)}".encode("utf-8")).hexdigest()[:32]
    return dict(entry, id=digest, site=f"{entry['site']} ⚠ {entry['updated']}", prevs=[])


def _merge_pair(one, other):
    """Две версии одной записи -> (итог, копия проигравшей или None)."""
    if one["modified"] == other["modified"]:
        # одна версия на двух устройствах; разное содержимое — почти невозможное совпадение времени
        newer, older = sorted((one, other), key=lambda e: json.dumps(_content(e), ensure_ascii=False))[::-1]
    else:
        newer, older = (one, other) if one["modified"] > other["modified"] else (other, one)
    linear = older["modified"] in newer["prevs"] or older["modified"] == newer["modified"]
    same = _content(newer) == _content(older)
    history = _history(newer["prevs"], older["prevs"], [older["modified"]] if older["modified"] != newer["modified"] else [])
    copy = None if same or (linear and older["modified"] != newer["modified"]) else _conflict_copy(older)
    return dict(newer, prevs=history), copy


def merge_entries(local, local_deleted, remote, remote_deleted):
    """Сливает две версии -> (записи, пометки об удалении). Порядок: наши записи на своих местах,
    потом новые с другого устройства. Результат не зависит от того, кто с кем сливается."""
    deleted = {}
    for source in (local_deleted, remote_deleted):
        for key, mark in source.items():
            old = deleted.get(key, {"at": 0, "seen": []})
            deleted[key] = {"at": max(old["at"], mark["at"]), "seen": _history(old["seen"], mark["seen"])}
    others = {entry["id"]: entry for entry in remote}
    merged, copies = [], []
    for entry in local:
        partner = others.pop(entry["id"], None)
        if partner is None:
            merged.append(entry)
        else:
            winner, copy = _merge_pair(entry, partner)
            merged.append(winner)
            if copy:
                copies.append(copy)
    merged.extend(entry for entry in remote if entry["id"] in others)
    known = {entry["id"] for entry in merged}
    merged.extend(copy for copy in copies if copy["id"] not in known)

    result = []
    for entry in merged:
        mark = deleted.get(entry["id"])
        if mark is None:
            result.append(entry)
        elif entry["modified"] not in mark["seen"]:
            del deleted[entry["id"]]  # эту версию удалявший не видел: правка важнее удаления
            result.append(entry)
    limit = now_ms() - TOMBSTONE_MS
    return result, {key: mark for key, mark in deleted.items() if mark["at"] >= limit}


def merge_log(local, remote, cleared, size):
    """Журнал выдач паролей расширению: всё с обоих устройств, но не старше последней очистки."""
    items = {(item["time"], item["site"], item["login"]): item for item in local + remote}
    return [items[key] for key in sorted(items) if key[0] > cleared][-size:]


def same_entries(one, other):
    """Одинаковы ли два списка записей (порядок не важен)."""
    return {e["id"]: (e["modified"], _content(e)) for e in one} == {e["id"]: (e["modified"], _content(e)) for e in other}
