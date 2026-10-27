"""Какой записи WhoKey подходит страница в браузере — защита от фишинга.

Запись хранит адрес сайта (`mail.ru`). Страница подходит, если её домен —
тот же самый или его поддомен: `mail.ru`, `e.mail.ru`, `account.mail.ru`.
Не подходят похожие: `mail.ru.evil.com`, `mai1.ru`, `evilmail.ru`.
Поддомен чужого сайта злоумышленник создать не может, а похожий домен — легко,
поэтому сравниваем строго по точкам, а не «содержит ли адрес строку».

Исключения (по ревью безопасности):
  - зона целиком (`co.uk`, `com.ru`, `myshopify.com`) — не адрес сайта: подошла бы
    ко всем сайтам зоны. Список зон — полный Public Suffix List (public_suffix_list.dat);
  - на сервисах, где поддомены принадлежат разным людям (`*.github.io`,
    `*.tumblr.com`), поддомены не подходят — только точный адрес;
  - учитывается порт: разные порты — разные программы. Запись без порта подходит
    только к сайту на обычном порту (443 для https);
  - адрес с буквами, которые Python и браузер переводят в латиницу по-разному
    (`ß`, `ς`, невидимые соединители), нужно вводить латиницей (punycode).

Заполняем только на защищённых страницах (https), кроме своего компьютера
(localhost): по http пароль может подсмотреть любой в той же сети.
Только стандартная библиотека — этим модулем пользуется и мост для браузера.
"""

import ipaddress
from pathlib import Path
from urllib.parse import urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Зоны, где сайты регистрируют люди: полный Public Suffix List (publicsuffix.org) —
# в файле public_suffix_list.dat рядом. Если файла почему-то нет — хотя бы частые зоны.
PSL_FILE = Path(__file__).resolve().parent / "public_suffix_list.dat"
PUBLIC_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "ltd.uk", "plc.uk",
    "com.au", "net.au", "org.au", "co.nz", "co.jp", "ne.jp", "or.jp", "co.kr", "or.kr",
    "com.br", "com.cn", "com.tw", "com.hk", "com.sg", "com.tr", "com.mx", "com.ar",
    "co.in", "co.za", "co.il", "com.ua", "org.ua", "in.ua", "kiev.ua", "com.by",
    "com.ru", "net.ru", "org.ru", "pp.ru", "msk.ru", "spb.ru", "ru.net", "com.kz", "org.kz",
}
# Сервисы, где поддомены принадлежат разным людям: chto-to.github.io — не GitHub.
# Для них подходит только точный адрес, без поддоменов.
SHARED_HOSTS = {
    "github.io", "githubusercontent.com", "gitlab.io", "tumblr.com", "blogspot.com",
    "wordpress.com", "herokuapp.com", "vercel.app", "netlify.app", "pages.dev",
    "workers.dev", "web.app", "firebaseapp.com", "appspot.com", "azurewebsites.net",
    "cloudfront.net", "s3.amazonaws.com", "glitch.me", "repl.co", "ngrok.io",
    "ngrok-free.app", "onrender.com", "fly.dev", "surge.sh", "neocities.org",
    "narod.ru", "ucoz.ru", "tilda.ws", "wixsite.com", "weebly.com", "notion.site",
}
# В IDNA2003 (Python) и UTS-46 (браузер) эти символы переводятся по-разному:
# «faß.de» у Python — «fass.de», а это чужой домен
DEVIATION_CHARS = {"ß", "ς", "‌", "‍"}


def _idna(host):
    """«госуслуги.рф» -> «xn--...»: браузер показывает домены в таком виде."""
    if host.isascii():
        return host
    if DEVIATION_CHARS & set(host):
        return None
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return None


def _is_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _load_psl():
    """Правила Public Suffix List: обычные, «*.зона» (любой домен в ней — тоже зона)
    и исключения «!домен»."""
    exact, wildcard, exceptions = set(PUBLIC_SUFFIXES), set(), set()
    try:
        lines = PSL_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return exact, wildcard, exceptions
    for line in lines:
        if not line or line.startswith("//"):
            continue
        if line.startswith("!"):
            exceptions.add(line[1:])
        elif line.startswith("*."):
            wildcard.add(line[2:])
        else:
            exact.add(line)
    return exact, wildcard, exceptions


_PSL = _load_psl()


def is_public_suffix(host):
    """Это зона целиком (`co.uk`, `github.io`, `myshopify.com`), а не адрес сайта?"""
    exact, wildcard, exceptions = _PSL
    if host in exceptions:
        return False
    if host in exact:
        return True
    return "." in host and host.split(".", 1)[1] in wildcard


def _shared(host):
    return any(host == s or host.endswith("." + s) for s in SHARED_HOSTS)


def normalize(text):
    """Адрес сайта из того, что ввёл человек: «https://Mail.ru/login» -> «mail.ru».

    У localhost и IP-адреса сохраняется порт, если он указан: «localhost:3000».
    Пустая строка — адрес не задан. None — это не похоже на адрес сайта.
    """
    text = (text or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
        host, port = parts.hostname, parts.port  # без схемы, пути и логина
    except ValueError:
        return None
    if not host:
        return None
    host = host.rstrip(".").lower()
    if _is_ip(host) or host == "localhost":
        if ":" in host:  # IPv6 — всегда в скобках, иначе адрес не прочитать заново
            host = f"[{host}]"
        return host if port is None else f"{host}:{port}"
    host = _idna(host)
    # одно слово без точки («ru», «com») подошло бы ко всем сайтам в этой зоне
    if not host or "." not in host or any(not part for part in host.split(".")):
        return None
    if is_public_suffix(host):
        return None
    # необычный порт — часть адреса: example.com:8443 — другая программа, чем example.com
    if port is not None and port not in (443, 80):
        return f"{host}:{port}"
    return host


def page_host(url):
    """Домен страницы, если на ней можно заполнять пароль; иначе None."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").rstrip(".").lower()
    except ValueError:
        return None
    if not host:
        return None
    if parts.scheme == "https" or (parts.scheme == "http" and host in LOCAL_HOSTS):
        return host
    return None


def _page_port(url):
    parts = urlsplit(url)
    return parts.port or {"https": 443, "http": 80}.get(parts.scheme)


def matches(site, url):
    """Подходит ли страница url записи с адресом сайта site."""
    host = page_host(url)
    site = normalize(site)
    if not host or not site:
        return False
    site_parts = urlsplit("https://" + site)
    site_host, site_port = site_parts.hostname, site_parts.port
    if _is_ip(site_host) or _is_ip(host) or site_host == "localhost":
        # адрес-число и localhost — только точное совпадение (и порта, если он указан в записи)
        try:
            return host == site_host and (site_port is None or site_port == _page_port(url))
        except ValueError:
            return False
    try:
        page_port = _page_port(url)
    except ValueError:
        return False
    # у записи без порта — только обычный порт https (у страницы по http localhost
    # сюда не дойдёт: это обычный домен, а по http он не заполняется)
    if page_port != (site_port or 443):
        return False
    if host == site_host:
        return True
    return host.endswith("." + site_host) and not _shared(site_host)
