"""Какой записи WhoKey подходит страница в браузере — защита от фишинга.

Запись хранит адрес сайта (`mail.ru`). Страница подходит, если её домен —
тот же самый или его поддомен: `mail.ru`, `e.mail.ru`, `account.mail.ru`.
Не подходят похожие: `mail.ru.evil.com`, `mai1.ru`, `evilmail.ru`.
Поддомен чужого сайта злоумышленник создать не может, а похожий домен — легко,
поэтому сравниваем строго по точкам, а не «содержит ли адрес строку».

Исключения (по ревью безопасности):
  - зона целиком (`co.uk`, `com.ru`) — не адрес сайта: подошла бы ко всем сайтам зоны;
  - на сервисах, где поддомены принадлежат разным людям (`*.github.io`,
    `*.tumblr.com`), поддомены не подходят — только точный адрес;
  - у localhost и IP-адреса учитывается порт: разные порты — разные программы;
  - адрес с буквами, которые Python и браузер переводят в латиницу по-разному
    (`ß`, `ς`, невидимые соединители), нужно вводить латиницей (punycode).

Заполняем только на защищённых страницах (https), кроме своего компьютера
(localhost): по http пароль может подсмотреть любой в той же сети.
Только стандартная библиотека — этим модулем пользуется и мост для браузера.
"""

import ipaddress
from urllib.parse import urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Зоны, где сайты регистрируют люди (часть Public Suffix List, publicsuffix.org).
# Полный список — тысячи строк; здесь частые. Сама зона не может быть адресом записи.
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
        if port is None:
            return host
        return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    host = _idna(host)
    # одно слово без точки («ru», «com») подошло бы ко всем сайтам в этой зоне
    if not host or "." not in host or any(not part for part in host.split(".")):
        return None
    if host in PUBLIC_SUFFIXES:
        return None
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
    if host == site_host:
        return True
    return host.endswith("." + site_host) and not _shared(site_host)
