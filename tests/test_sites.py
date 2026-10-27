"""Правило «какой записи подходит страница» (sites.py) — защита от фишинга.

Запуск: python -m unittest discover tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sites  # noqa: E402

FILL = [  # (адрес в записи, страница) — заполнять можно
    ("mail.ru", "https://mail.ru/login"),
    ("mail.ru", "https://e.mail.ru/inbox"),
    ("mail.ru", "https://account.mail.ru:443/"),
    ("Mail.RU", "https://MAIL.ru/"),
    ("https://mail.ru/login?x=1", "https://mail.ru/"),
    ("mail.ru.", "https://mail.ru./"),
    ("localhost", "http://localhost:3000/"),
    ("127.0.0.1", "http://127.0.0.1:8000/"),
    ("1.2.3.4", "https://1.2.3.4/"),
    ("tumblr.com", "https://tumblr.com/login"),        # сам сервис — можно
    ("user.github.io", "https://user.github.io/"),
    ("localhost:3000", "http://localhost:3000/login"),
    ("bbc.co.uk", "https://www.bbc.co.uk/"),
]
NO_FILL = [  # а здесь — ни в коем случае
    ("mail.ru", "https://mail.ru.evil.com/"),
    ("mail.ru", "https://evilmail.ru/"),
    ("mail.ru", "https://mai1.ru/"),
    ("mail.ru", "http://mail.ru/"),                    # без https
    ("mail.ru", "https://user:pw@evil.com/mail.ru"),
    ("e.mail.ru", "https://mail.ru/"),                 # запись поддомена не подходит основному
    ("ru", "https://mail.ru/"),                        # одно слово — не адрес
    ("3.4", "https://1.2.3.4/"),                       # адрес-число — только точно
    ("", "https://mail.ru/"),
    ("mail.ru", "javascript:alert(1)"),
    ("mail.ru", "file:///etc/passwd"),
    ("mail.ru", "chrome://settings"),
    ("mail.ru", "not a url"),
    # ревью безопасности
    ("faß.de", "https://fass.de/"),                    # Python превратил бы в чужой fass.de
    ("co.uk", "https://bbc.co.uk/"),                   # зона целиком — не адрес
    ("tumblr.com", "https://evil.tumblr.com/"),        # поддомены — чужие блоги
    ("user.github.io", "https://evil.github.io/"),
    ("localhost:3000", "http://localhost:8080/"),      # другой порт — другая программа
]


class Matching(unittest.TestCase):
    def test_fill(self):
        for site, url in FILL:
            with self.subTest(site=site, url=url):
                self.assertTrue(sites.matches(site, url))

    def test_no_fill(self):
        for site, url in NO_FILL:
            with self.subTest(site=site, url=url):
                self.assertFalse(sites.matches(site, url))

    def test_cyrillic_domain(self):
        page = "https://" + "госуслуги.рф".encode("idna").decode() + "/login"
        self.assertTrue(sites.matches("госуслуги.рф", page))

    def test_normalize(self):
        self.assertEqual(sites.normalize("https://Mail.ru:8080/login"), "mail.ru")
        self.assertEqual(sites.normalize("  "), "")
        self.assertEqual(sites.normalize("http://localhost:3000/x"), "localhost:3000")
        # IPv6 — в скобках и с портом, и без: сохранённый адрес должен читаться заново
        for text, saved in (("[::1]", "[::1]"), ("http://[::1]:8080/x", "[::1]:8080")):
            with self.subTest(text=text):
                self.assertEqual(sites.normalize(text), saved)
                self.assertEqual(sites.normalize(saved), saved)
        self.assertTrue(sites.matches("[::1]", "http://[::1]/login"))
        for bad in ("ru", "a..b", "http://", "http://[bad", "co.uk", "faß.de", "ex\u200dample.com"):
            with self.subTest(bad=bad):
                self.assertIsNone(sites.normalize(bad))


if __name__ == "__main__":
    unittest.main()
