"""Значки сайтов для таблицы: скачиваются с самих сайтов (а не через Google и т.п. — им пришлось бы
отдать весь список сайтов из хранилища).

Осторожности ради:
- только https, без cookies и логинов, короткие таймауты, ограничение размера каждого ответа;
- адреса внутри сети (роутер, localhost, 10.x, 192.168.x …) не трогаем, даже после перенаправления:
  подсунутый CSV не заставит WhoKey стучаться внутрь домашней или рабочей сети;
- картинка с сайта — чужие данные: её размер проверяется до декодирования, а в хранилище попадает
  только наша перерисовка в маленький PNG.

Работает в фоновых потоках: здесь нет окон, только сеть и QImage (QImage можно и не в главном потоке).
"""

import http.client
import os
import ipaddress
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt
from PySide6.QtGui import QImage, QImageIOHandler, QImageReader, QPainter

import sites

SIZE = 48                 # сторона значка в хранилище: в таблице он 24 pt, на Retina — 48 точек
PAGE_LIMIT = 400 * 1024   # сколько читаем от главной страницы в поисках <link rel="icon">
IMAGE_LIMIT = 300 * 1024  # самый большой файл значка
MAX_SIDE = 1024           # картинку больше этого и не декодируем
TIMEOUT = 6
REDIRECTS = 3
TRIES = 3                 # сколько адресов значка пробуем, кроме /favicon.ico
USER_AGENT = "Mozilla/5.0 (compatible; WhoKey site icons)"


class Refused(Exception):
    """Адрес нельзя трогать (не https, сеть внутри, слишком много перенаправлений)."""


def host_of(entry):
    """Сайт записи для значка: из «Адреса сайта», иначе из названия, если оно похоже на адрес.
    None — значка не будет (адрес не задан, IP, localhost)."""
    for text in (entry.get("url", ""), entry.get("site", "")):
        host = sites.normalize(text)
        if host:
            name = host[1:host.find("]")] if host.startswith("[") else host.split(":")[0]  # без порта
            if name == "localhost" or _is_ip(name):
                return None
            return host
    return None


def _is_ip(text):
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def _public_address(host, port):
    """Проверенный внешний адрес для host или Refused. Соединение потом идёт ровно на него:
    иначе DNS мог бы сначала ответить внешним адресом, а при подключении — внутренним."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        raise Refused("no such host")
    addresses = [info[4][0].split("%")[0] for info in infos]
    if not addresses or not all(ipaddress.ip_address(address).is_global for address in addresses):
        raise Refused("not a public address")
    return addresses[0]


class _PinnedHTTPS(http.client.HTTPSConnection):
    """https на заранее проверенный адрес; сертификат при этом проверяется для имени сайта."""

    def __init__(self, host, port, address):
        super().__init__(host, port, timeout=TIMEOUT, context=_CONTEXT)
        self._address = address

    def connect(self):
        sock = socket.create_connection((self._address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


_CONTEXT = ssl.create_default_context()


def _get(url, limit):
    """(итоговый адрес, тип, байты) или Refused / OSError."""
    for _ in range(REDIRECTS + 1):
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise Refused("https only")
        port = parts.port or 443
        connection = _PinnedHTTPS(parts.hostname, port, _public_address(parts.hostname, port))
        try:
            path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
            connection.request("GET", path, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            response = connection.getresponse()
            location = response.getheader("Location")
            if response.status in (301, 302, 303, 307, 308) and location:
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise OSError(f"HTTP {response.status}")
            data = response.read(limit + 1)
            if len(data) > limit:
                raise OSError("too large")
            kind = (response.getheader("Content-Type") or "").split(";")[0].strip().lower()
            return url, kind, data
        except (http.client.HTTPException, ssl.SSLError, ValueError) as error:
            raise OSError(str(error))
        finally:
            connection.close()
    raise Refused("too many redirects")


class _IconLinks(HTMLParser):
    """<link rel="icon" …> из начала страницы: (насколько хорош, адрес)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = []

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        attrs = {name: (value or "") for name, value in attrs}
        rel = attrs.get("rel", "").lower().split()
        href = attrs.get("href", "").strip()
        if not href or href.startswith("data:") or ".svg" in href.lower() or "svg" in attrs.get("type", ""):
            return  # SVG не берём: это целая программа рисования, а не картинка
        if "apple-touch-icon" in rel or "apple-touch-icon-precomposed" in rel:
            score = 3
        elif "icon" in rel:
            sizes = attrs.get("sizes", "").lower()
            score = 2 if any(size in sizes for size in ("32", "48", "64", "96", "128", "192")) else 1
        else:
            return
        self.found.append((score, href))


def icon_links(page, base):
    """Адреса значков со страницы, лучшие — первыми."""
    parser = _IconLinks()
    try:
        parser.feed(page.decode("utf-8", "replace"))
    except Exception:  # кривая разметка — не повод падать, берём что успели найти
        pass
    ordered = sorted(parser.found, key=lambda item: -item[0])
    links = []
    for _, href in ordered:
        link = urljoin(base, href)
        if link not in links:
            links.append(link)
    return links


def normalize_image(data):
    """Байты чужой картинки -> наш PNG SIZE×SIZE (прозрачные поля, без растягивания) или None."""
    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QIODevice.ReadOnly)
    reader = QImageReader(buffer)
    reader.setAutoTransform(False)
    size = reader.size()
    if not size.isValid() or size.width() > MAX_SIDE or size.height() > MAX_SIDE:
        return None  # размер узнаём до декодирования: «бомба» 50000×50000 не дойдёт до памяти
    if reader.supportsOption(QImageIOHandler.ImageOption.ScaledSize) and max(size.width(), size.height()) > SIZE * 4:
        reader.setScaledSize(size.scaled(SIZE * 4, SIZE * 4, Qt.KeepAspectRatio))
    image = reader.read()
    if image.isNull() or image.width() < 8 or image.height() < 8:
        return None
    image = image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    if not _has_content(image):
        return None
    scaled = image.scaled(SIZE, SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out = QImage(SIZE, SIZE, QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    place = QRect(0, 0, scaled.width(), scaled.height())
    place.moveCenter(out.rect().center())
    painter.drawImage(place, scaled)
    painter.end()
    result = QBuffer()
    result.open(QIODevice.WriteOnly)
    out.save(result, "PNG")
    return bytes(result.data())


def _has_content(image):
    """Не пустой ли значок (полностью прозрачный или одного цвета — не значок)."""
    step_x, step_y = max(1, image.width() // 16), max(1, image.height() // 16)
    colors = set()
    for y in range(0, image.height(), step_y):
        for x in range(0, image.width(), step_x):
            pixel = image.pixel(x, y)
            if (pixel >> 24) > 16:
                colors.add(pixel)
                if len(colors) > 1:
                    return True
    return False


def fetch(host):
    """PNG значка сайта или None. Сеть и чужие данные: любая ошибка — просто «значка нет»."""
    if os.environ.get("WHOKEY_TESTING"):  # автотесты не ходят в сеть
        return None
    base = f"https://{host}/"
    candidates = []
    try:
        final, kind, page = _get(base, PAGE_LIMIT)
        if kind in ("text/html", "application/xhtml+xml"):
            candidates = icon_links(page, final)[:TRIES]
    except (Refused, OSError, ValueError):
        pass
    fallback = urljoin(base, "/favicon.ico")
    if fallback not in candidates:
        candidates.append(fallback)
    for url in candidates:
        try:
            _, kind, data = _get(url, IMAGE_LIMIT)
        except (Refused, OSError, ValueError):
            continue
        if kind.startswith("text/") or "svg" in kind:
            continue
        png = normalize_image(data)
        if png:
            return png
    return None
