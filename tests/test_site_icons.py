"""Значки сайтов: какие адреса трогаем, как чистим чужие картинки, где храним (внутри шифровки)."""

import base64
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["WHOKEY_TESTING"] = "1"  # значки сайтов не скачиваются (favicons.fetch)

from PySide6.QtCore import QBuffer, QIODevice, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

import favicons  # noqa: E402
import vault as V  # noqa: E402
from gui import prefs  # noqa: E402

prefs.use_file(Path(tempfile.mkdtemp()) / "p.ini")


def png(width=64, height=64, two_colors=True, fmt="PNG"):
    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(QColor("#2050e0"))
    if two_colors:
        painter = QPainter(image)
        painter.fillRect(0, 0, width // 2, height // 2, QColor("#f0a020"))
        painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, fmt)
    return bytes(buffer.data())


class Hosts(unittest.TestCase):
    def test_host_from_address_or_name(self):
        self.assertEqual(favicons.host_of({"site": "Почта", "url": "https://e.mail.ru/inbox"}), "e.mail.ru")
        self.assertEqual(favicons.host_of({"site": "github.com"}), "github.com")
        self.assertIsNone(favicons.host_of({"site": "Cat Mail", "url": ""}))

    def test_local_addresses_get_no_icon(self):
        for url in ("localhost:3000", "192.168.0.1", "127.0.0.1", "[::1]"):
            self.assertIsNone(favicons.host_of({"site": "x", "url": url}), url)

    def test_only_public_https(self):
        for url in ("http://github.com/", "https://localhost/", "https://127.0.0.1/", "https://10.0.0.1/",
                    "https://192.168.1.1/", "https://169.254.169.254/", "https://user:pw@github.com/"):
            with self.assertRaises(favicons.Refused, msg=url):
                favicons._get(url, 100)

    def test_no_network_in_tests(self):
        self.assertIsNone(favicons.fetch("github.com"))


class Links(unittest.TestCase):
    def test_best_icons_first_and_no_svg(self):
        page = b"""<html><head>
            <link rel="icon" href="/small.ico">
            <link rel="icon" type="image/svg+xml" href="/logo.svg">
            <link rel="icon" sizes="32x32" href="/i32.png">
            <link rel="apple-touch-icon" href="https://cdn.example.com/touch.png">
            <link rel="icon" href="data:image/png;base64,AAAA">
            <link rel="stylesheet" href="/s.css">
        </head></html>"""
        self.assertEqual(favicons.icon_links(page, "https://example.com/start"),
                         ["https://cdn.example.com/touch.png", "https://example.com/i32.png", "https://example.com/small.ico"])

    def test_broken_markup(self):
        self.assertEqual(favicons.icon_links(b"<link rel=icon href='/a.png'><<<\xff\xfe", "https://x.com/"),
                         ["https://x.com/a.png"])


class Images(unittest.TestCase):
    def test_redrawn_to_small_png(self):
        out = favicons.normalize_image(png(64, 32))
        image = QImage.fromData(out, "PNG")
        self.assertEqual((image.width(), image.height()), (favicons.SIZE, favicons.SIZE))
        self.assertEqual(image.pixel(0, 0) >> 24, 0)  # поля сверху и снизу прозрачные, без растягивания

    def test_ico_is_read(self):
        self.assertIsNotNone(favicons.normalize_image(png(32, 32, fmt="ICO")))

    def test_rejected_images(self):
        self.assertIsNone(favicons.normalize_image(b"not an image"))
        self.assertIsNone(favicons.normalize_image(png(two_colors=False)))  # один цвет — не значок
        self.assertIsNone(favicons.normalize_image(png(favicons.MAX_SIDE + 1, 16)))  # слишком большая
        self.assertIsNone(favicons.normalize_image(png(4, 4)))


class Stored(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "v.dat"
        self.vault = V.Vault.create(self.path, "pw-pw-pw-1")

    def test_icons_are_saved_inside_the_encryption(self):
        icon = base64.b64encode(favicons.normalize_image(png())).decode()
        self.vault.set_icons({"github.com": {"png": icon, "time": "2026-11-09 10:00"}})
        self.assertNotIn("github.com", self.path.read_text())  # список сайтов не виден снаружи
        again = V.Vault.open(self.path, "pw-pw-pw-1")
        self.assertEqual(again.icons["github.com"]["png"], icon)
        again.add("x", "y", "z")  # обычное сохранение значки не теряет
        self.assertIn("github.com", V.Vault.open(self.path, "pw-pw-pw-1").icons)

    def test_bad_icons_are_dropped_not_fatal(self):
        icons = {"ok.com": {"png": "", "time": "2026-11-09 10:00"}, "big.com": {"png": "A" * (V.ICON_SIZE_LIMIT + 1), "time": "t"},
                 "bad.com": {"png": 5, "time": "t"}, "": {"png": "", "time": "t"}, "list.com": []}
        self.assertEqual(V._valid_icons(icons), {"ok.com": {"png": "", "time": "2026-11-09 10:00"}})
        self.assertEqual(V._valid_icons("junk"), {})
        many = {f"s{i}.com": {"png": "A" * 10000, "time": "t"} for i in range(1000)}
        kept = V._valid_icons(many)
        self.assertLess(sum(len(i["png"]) for i in kept.values()), V.ICONS_TOTAL_LIMIT)


class Downloads(unittest.TestCase):
    def wait(self, icons, condition):
        deadline = time.time() + 5
        while not condition() and time.time() < deadline:
            APP.processEvents()
            time.sleep(0.02)
            icons._collect()
        self.assertTrue(condition())

    def test_missing_icons_are_downloaded_once(self):
        from gui.site_icons import SiteIcons
        vault = V.Vault.create(Path(tempfile.mkdtemp()) / "v.dat", "pw-pw-pw-1")
        vault.add("GitHub", "me", "pw", url="github.com")
        vault.add("Nothing", "me", "pw", url="nothing.example")
        vault.add("Cat Mail", "me", "pw")
        asked = []
        image = png()

        def fake(host):
            asked.append(host)
            return image if host == "github.com" else None

        icons = SiteIcons(vault, fetch=fake)
        icons.request()
        self.wait(icons, lambda: set(vault.icons) == {"github.com", "nothing.example"})
        self.assertTrue(vault.icons["github.com"]["png"])
        self.assertEqual(vault.icons["nothing.example"]["png"], "")  # не нашёлся — запомнили, не долбим
        self.assertIsNotNone(icons.icon(vault.entries[0]))
        self.assertIsNone(icons.icon(vault.entries[1]))
        icons.request()  # всё свежее — второй раз не спрашиваем
        APP.processEvents()
        self.assertEqual(sorted(asked), ["github.com", "nothing.example"])
        icons.stop()

    def test_failing_download_is_just_no_icon(self):
        from gui.site_icons import SiteIcons
        vault = V.Vault.create(Path(tempfile.mkdtemp()) / "v.dat", "pw-pw-pw-1")
        vault.add("GitHub", "me", "pw", url="github.com")

        def broken(host):
            raise RuntimeError("network exploded")

        icons = SiteIcons(vault, fetch=broken)
        icons.request()
        self.wait(icons, lambda: "github.com" in vault.icons)
        self.assertIsNone(icons.icon(vault.entries[0]))
        icons.stop()


if __name__ == "__main__":
    unittest.main()
