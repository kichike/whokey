"""Значки сайтов в таблице главного окна: берутся из хранилища, недостающие скачиваются в фоне (favicons.py).

Скачивание — в отдельных потоках, чтобы окно не замирало. Потоки не трогают ни окна, ни хранилище:
они только кладут результат в очередь, а главный поток забирает его по таймеру и сохраняет
одним разом. Так закрытие окна (блокировка) посреди загрузки ничего не ломает: недокачанное
просто пропадает и докачается при следующем входе.
"""

import base64
import queue
import threading
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QIcon, QImage

import favicons
from gui import theme
from vault import SaveError, _now

WORKERS = 4
RETRY_MISSING = timedelta(days=7)   # у сайта не нашлось значка — попробуем снова через неделю
REFRESH = timedelta(days=30)        # сайты иногда меняют значок
SAVE_EVERY = 20                     # большой импорт: сохраняем частями, а не после сотни сайтов


def _when(text):
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return datetime.min


class SiteIcons(QObject):
    changed = Signal()  # появились новые значки — таблицу пора перерисовать

    def __init__(self, vault, parent=None, fetch=favicons.fetch):
        super().__init__(parent)
        self.vault = vault
        self._fetch = fetch
        self._todo = queue.Queue()      # сайты для потоков; None — потоку пора закончить
        self._workers = 0
        self._pending = set()
        self._results = queue.Queue()
        self._unsaved = {}
        self._tiles = {}  # (сайт, png) -> QIcon
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._collect)

    def icon(self, entry):
        """Значок для строки записи или None (тогда остаётся буква-кружок)."""
        host = favicons.host_of(entry)
        if host is None:
            return None
        png = (self._unsaved.get(host) or self.vault.icons.get(host) or {}).get("png")
        if not png:
            return None
        key = (host, png)
        if key not in self._tiles:
            image = QImage()
            try:
                ok = image.loadFromData(base64.b64decode(png, validate=True), "PNG")
            except ValueError:
                ok = False
            self._tiles[key] = QIcon(theme.site_tile(image)) if ok and not image.isNull() else None
        return self._tiles[key]

    def _due(self, host):
        icon = self._unsaved.get(host) or self.vault.icons.get(host)
        if icon is None:
            return True
        return datetime.now() - _when(icon["time"]) > (REFRESH if icon["png"] else RETRY_MISSING)

    def request(self):
        """Скачать значки сайтов, которых ещё нет (или они устарели)."""
        hosts = {favicons.host_of(entry) for entry in self.vault.entries} - {None}
        for host in sorted(hosts):
            if host in self._pending or not self._due(host):
                continue
            self._pending.add(host)
            self._todo.put(host)
        while self._workers < min(WORKERS, len(self._pending)):
            # потоки-«демоны»: выход из WhoKey не ждёт, пока докачается чей-то значок
            threading.Thread(target=self._work, args=(self._todo, self._results), daemon=True,
                             name="site-icon").start()
            self._workers += 1
        if self._pending:
            self._timer.start()

    def _work(self, todo, results):
        while True:
            host = todo.get()
            if host is None:
                return
            try:
                png = self._fetch(host)
            except Exception:  # сеть и чужие данные: любая ошибка — просто «значка нет»
                png = None
            results.put((host, png))

    def _collect(self):
        got = False
        while True:
            try:
                host, png = self._results.get_nowait()
            except queue.Empty:
                break
            self._pending.discard(host)
            self._unsaved[host] = {"png": base64.b64encode(png).decode("ascii") if png else "", "time": _now()}
            got = got or bool(png)
        if self._unsaved and (not self._pending or len(self._unsaved) >= SAVE_EVERY):
            self._save()
        if not self._pending:
            self._timer.stop()
            self._finish_workers()
        if got:
            self.changed.emit()

    def _save(self):
        icons = dict(self.vault.icons)
        icons.update(self._unsaved)
        try:
            self.vault.set_icons(icons)
        except SaveError:
            return  # значки — не главное: не записалось сейчас, запишется со следующим сохранением
        self._unsaved = {}

    def _finish_workers(self):
        for _ in range(self._workers):
            self._todo.put(None)
        self._workers = 0

    def stop(self):
        """Окно закрывается: очередь бросаем, начатые загрузки доработают впустую."""
        self._timer.stop()
        old, self._todo = self._todo, queue.Queue()
        try:
            while True:
                old.get_nowait()
        except queue.Empty:
            pass
        for _ in range(self._workers):
            old.put(None)
        self._workers = 0
        self._pending.clear()
