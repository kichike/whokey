"""Сервер внутри WhoKey для расширения браузера (через мост, см. bridge_protocol.py).

Слушает локальный сокет, только пока хранилище открыто: закрыт WhoKey, не
введён мастер-пароль или он заблокировался — отвечать некому, и мост откроет
WhoKey сам.

Что защищает пароли (часть — по независимому ревью безопасности):
  - отвечает только своему мосту: система сообщает, какая программа на другом
    конце сокета, и это должен быть сам WhoKey (bridge_protocol.trusted_peer);
  - первое подключение расширения нужно разрешить в окне WhoKey, сверив код
    из окошка расширения; ключ хранится только отпечатком (SHA-256) и внутри
    зашифрованного хранилища — дописать «свой» ключ без мастер-пароля нельзя;
  - пароль отдаётся, только если адрес страницы подходит записи (sites.py) —
    WhoKey проверяет это сам, не доверяя расширению;
  - на странице без https (кроме localhost) не отдаётся ничего;
  - ограничены число соединений, время на запрос и частота запросов: никто
    не может «завалить» WhoKey или перебрать адреса, чтобы вытащить пароли;
  - каждая выдача пароля видна в строке состояния главного окна и записывается
    в журнал внутри хранилища (кнопка «Расширение»).
Сеть не используется: сокет — файл в папке программы, доступный только владельцу
(на Windows — именованный канал, открытый только для текущего пользователя).
"""

import hashlib
import hmac
import json
import os
import socket
import time

from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QDialog

import bridge_protocol as P
import sites
from gui.widgets import ask_code
from gui.i18n import tr
from vault import SaveError

OLD_KEYS_SETTING = "bridge/keys"  # раньше отпечатки лежали в открытых настройках — удаляем
MAX_CONNECTIONS = 8                # больше одновременно не бывает: один браузер, один мост
REQUEST_TIMEOUT_MS = 5000          # соединение без запроса дольше этого закрывается
PAIR_COOLDOWN = 10                 # секунд после отказа — новые запросы разрешения не показываем;
PAIR_COOLDOWN_MAX = 600            # после каждого следующего отказа пауза вдвое длиннее, до 10 минут
RATE_LIMIT = {"logins": 30, "fill": 10, "show": 5}  # запросов в минуту
CLOSE_AFTER_MS = 2000              # после ответа: сколько ждём, пока собеседник закроет соединение


def _fingerprint(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class BridgeServer(QObject):
    def __init__(self, vault, window, settings):
        # без родителя: окно пересоздаётся (смена языка), а сервер должен жить дальше —
        # будь он «ребёнком» окна, Qt удалил бы его вместе со старым окном
        super().__init__()
        self.vault, self.window, self.settings = vault, window, settings
        self.server = None
        self.buffers = {}  # соединение -> полученные байты
        self.busy = set()  # соединения, чей запрос сейчас обрабатывается (например, ждёт «разрешить?»)
        self.closing = set()  # ответ отправлен — ждём, пока собеседник закроет соединение
        self.pairing = False      # окно «разрешить?» уже открыто
        self.denied_at = None     # когда в последний раз отказали в разрешении (None — не отказывали)
        self.denials = 0          # отказов подряд — от них растёт пауза
        self.recent = {kind: [] for kind in RATE_LIMIT}  # время последних запросов
        settings.remove(OLD_KEYS_SETTING)
        # если сервер почему-то перестал слушать (например, кончились дескрипторы) — поднять снова
        self.watchdog = QTimer(self)
        self.watchdog.setInterval(2000)
        self.watchdog.timeout.connect(self._ensure_listening)

    def start(self):
        """Начинает слушать. False — не вышло (расширение просто не сможет подключиться)."""
        address = P.socket_address()
        QLocalServer.removeServer(address)  # сокет мог остаться от упавшего запуска
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)  # только владелец
        if not self.server.listen(address):
            print("WhoKey: не удалось открыть сокет для расширения:", self.server.errorString())
            self.server = None
            return False
        try:
            os.chmod(address, 0o600)
        except OSError:
            pass
        self.server.newConnection.connect(self._accept)
        self.watchdog.start()
        return True

    def stop(self):
        self.watchdog.stop()
        if self.server is not None:
            self.server.close()
            self.server = None
        for conn in list(self.buffers) + list(self.closing):
            conn.abort()
        self.buffers.clear()
        self.busy.clear()
        self.closing.clear()

    def _ensure_listening(self):
        if self.server is None or not self.server.isListening():
            if self.server is not None:
                self.server.close()
            self.start()

    # --- соединения ---

    def _accept(self):
        while self.server is not None and self.server.hasPendingConnections():
            conn = self.server.nextPendingConnection()
            if len(self.buffers) >= MAX_CONNECTIONS:
                conn.abort()  # слишком много соединений — даже не читаем
                conn.deleteLater()
                continue
            if not self._trusted(conn):
                # чужая программа: ничего не читаем и не отдаём, только говорим «не доверяю» —
                # иначе мост принял бы обрыв за «WhoKey закрыт» и открывал бы его снова
                self._answer_and_close(conn, b'{"status": "untrusted"}\n')
                continue
            self.buffers[conn] = b""
            conn.readyRead.connect(lambda c=conn: self._read(c))
            conn.disconnected.connect(lambda c=conn: self._drop(c))
            QTimer.singleShot(REQUEST_TIMEOUT_MS, lambda c=conn: self._timeout(c))

    def _trusted(self, conn):
        """На другом конце — наш мост (та же программа, что и WhoKey)?"""
        descriptor = conn.socketDescriptor()
        if descriptor is None or descriptor < 0:
            return False
        if P.WINDOWS:  # на Windows это не сокет, а именованный канал — спрашиваем систему о нём
            return P.trusted_pipe_client(descriptor)
        try:
            # копия дескриптора — только чтобы спросить систему о собеседнике
            with socket.socket(fileno=os.dup(int(descriptor))) as sock:
                return P.trusted_peer(sock)
        except OSError:
            return False

    def _timeout(self, conn):
        """Соединение молчит дольше REQUEST_TIMEOUT_MS — закрыть. Но не то, чей запрос
        в работе: человек может долго думать над «разрешить?», это нормально."""
        if conn in self.buffers and conn not in self.busy:
            conn.abort()

    def _drop(self, conn):
        self.buffers.pop(conn, None)
        conn.deleteLater()

    def _read(self, conn):
        if conn not in self.buffers:
            return
        self.buffers[conn] += bytes(conn.readAll())
        data = self.buffers[conn]
        if b"\n" not in data:
            if len(data) > P.MAX_LINE:  # слишком длинный запрос — не наш
                conn.abort()
            return
        line = data.split(b"\n", 1)[0]
        self.buffers[conn] = b""
        self.busy.add(conn)
        # Обрабатываем ПОСЛЕ выхода из обработчика сокета. Внутри запроса может
        # открыться окно «разрешить?» со своим циклом событий; если бы оно было
        # открыто прямо отсюда, а соединение за это время закрылось и удалилось,
        # Qt вернулся бы в удалённый объект — так WhoKey и вылетал.
        QTimer.singleShot(0, lambda: self._respond(conn, line))

    def _respond(self, conn, line):
        if self.server is None:  # WhoKey успел заблокироваться — окно «разрешить?» не показываем
            self.busy.discard(conn)
            return
        try:
            request = json.loads(line.decode("utf-8"))
            reply = self.handle(request) if isinstance(request, dict) else {"status": "error"}
        except Exception:  # noqa: BLE001 — любой мусор (в т.ч. «глубокий» JSON) — просто ошибка, не окно
            reply = {"status": "error"}
        self.busy.discard(conn)
        # пока человек думал над «разрешить?», соединение могло закрыться (и объект удалён) —
        # тогда к нему не обращаемся вовсе: проверка «есть ли в списке» его не трогает
        if conn in self.buffers:
            self._answer_and_close(conn, json.dumps(reply, ensure_ascii=False).encode("utf-8") + b"\n")

    def _answer_and_close(self, conn, data):
        """Отвечает и ждёт, пока собеседник сам закроет соединение (он закрывает, прочитав ответ).

        Если закрыть со своей стороны сразу, на Windows непрочитанный ответ пропадает
        (канал рвётся вместе с ним) — мост решил бы, что WhoKey закрыт. Молчуна
        закрываем принудительно через CLOSE_AFTER_MS.
        """
        if len(self.closing) >= MAX_CONNECTIONS:  # слишком много «повисших» — не ждём
            conn.abort()
            conn.deleteLater()
            return
        self.closing.add(conn)
        conn.disconnected.connect(lambda c=conn: self._closed(c))
        conn.write(data)
        conn.flush()
        QTimer.singleShot(CLOSE_AFTER_MS, lambda c=conn: self._closed(c, force=True))

    def _closed(self, conn, force=False):
        if conn not in self.closing:  # уже закрыт — объект не трогаем
            return
        self.closing.discard(conn)
        if force:
            conn.abort()
        conn.deleteLater()

    # --- запросы ---

    def _too_often(self, kind):
        """Не чаще RATE_LIMIT в минуту — так не перебрать много адресов подряд."""
        now = time.monotonic()
        recent = [moment for moment in self.recent[kind] if now - moment < 60]
        self.recent[kind] = recent + [now]
        return len(recent) >= RATE_LIMIT[kind]

    def handle(self, request):
        kind = request.get("type")
        if kind == "ping":
            return {"status": "ok"}
        if kind == "pair":
            return self._pair(request)
        if not self._key_ok(request.get("key")):
            return {"status": "pair_required"}
        url = request.get("url")
        if not isinstance(url, str) or sites.page_host(url) is None:
            return {"status": "bad_page"}  # не https — ничего не отдаём
        if kind in RATE_LIMIT and self._too_often(kind):
            return {"status": "busy"}
        if kind == "logins":
            items = [{"index": i, "site": e["site"], "login": e["login"]}
                     for i, e in enumerate(self.vault.entries) if sites.matches(e.get("url", ""), url)]
            return {"status": "ok", "items": items}
        if kind == "fill":
            return self._fill(request, url)
        if kind == "show":
            # «Добавить в WhoKey» из окошка расширения: для сайта ещё нет записи — открываем
            # окно новой записи с уже вписанным адресом (после ответа: окно не держит мост)
            QTimer.singleShot(0, lambda: self._show_new_entry(url))
            return {"status": "ok"}
        return {"status": "error"}

    def _show_new_entry(self, url):
        window = self.window
        if window is None or not hasattr(window, "add"):
            return
        window.showNormal()
        window.raise_()
        window.activateWindow()
        if not window.findChildren(QDialog):  # уже открыто какое-то окно — второе поверх не открываем
            address = sites.normalize(url) or ""
            # без «www.»: запись для github.com подойдёт и www.github.com, а наоборот — нет
            window.add(url=address[4:] if address.startswith("www.") else address)

    def _pair(self, request):
        """Первое подключение расширения: человек вводит в WhoKey код со значка расширения.

        Код придумывает расширение и показывает на своём значке в браузере (и в окошке).
        Чужая программа может прислать запрос со своим кодом, но показать его на значке
        нашего расширения не может — человеку нечего будет ввести, и доступ она не получит.
        Раньше WhoKey сам показывал код и спрашивал «Да / Нет» — нажать «Да» не глядя было легко.
        """
        code = request.get("code")
        if not (isinstance(code, str) and len(code) == 4 and code.isdigit() and code.isascii()):
            return {"status": "error"}
        # не «0.0»: time.monotonic() у Python на Mac отсчитывается почти от нуля при запуске программы
        pause = min(PAIR_COOLDOWN * 2 ** max(self.denials - 1, 0), PAIR_COOLDOWN_MAX)
        recently_denied = self.denied_at is not None and time.monotonic() - self.denied_at < pause
        if self.pairing or recently_denied:
            return {"status": "denied"}  # окно уже открыто или только что отказали — не заваливаем окнами
        self.pairing = True
        try:
            self.window.showNormal()
            self.window.raise_()
            self.window.activateWindow()
            typed = ask_code(self.window, tr("Browser extension"), tr("The WhoKey browser extension asks for access to your passwords.\nIt will be able to fill the login and password on websites listed in your entries.\n\nEnter the 4-digit code shown on the WhoKey icon in your browser.\nIf you did not just click the extension, press Cancel."))
            if typed is None or not hmac.compare_digest(typed.encode(), code.encode()):
                self.denied_at = time.monotonic()
                self.denials += 1
                return {"status": "denied"}
            self.denials = 0
            key = P.new_key()
            try:
                self.vault.set_bridge_keys(self.vault.bridge_keys + [_fingerprint(key)])
            except SaveError:
                return {"status": "error"}
            return {"status": "ok", "key": key}
        finally:
            self.pairing = False

    def _key_ok(self, key):
        if not isinstance(key, str) or not key:
            return False
        fingerprint = _fingerprint(key)
        # сравнение за одинаковое время — по скорости ответа ключ не подобрать
        return any(hmac.compare_digest(fingerprint, known) for known in self.vault.bridge_keys)

    def _fill(self, request, url):
        index, login = request.get("index"), request.get("login")
        entries = self.vault.entries
        if type(index) is not int or not 0 <= index < len(entries):
            return {"status": "not_found"}
        entry = entries[index]
        # WhoKey сам перепроверяет, что страница подходит записи, и что это та же запись
        if entry["login"] != login or not sites.matches(entry.get("url", ""), url):
            return {"status": "not_found"}
        host = sites.page_host(url)
        # журнал выдач: даже если пароль утащит не настоящее расширение (а программа,
        # укравшая его ключ), человек увидит, кто и когда получил пароли (кнопка «Расширение»)
        try:
            self.vault.log_access(host, entry["login"])
        except SaveError:
            pass  # не записалось (например, полон диск) — пароль всё равно нужен
        self.window.statusBar().showMessage(tr("Password for {site} sent to the browser").format(site=host), 8000)
        return {"status": "ok", "login": entry["login"], "password": entry["password"]}
