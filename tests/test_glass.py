"""Жидкое стекло: рисуется само и не ломает окна, а при ошибке остаётся обычный вид."""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QPushButton, QToolButton, QVBoxLayout  # noqa: E402

APP = QApplication.instance() or QApplication([])

from gui import prefs, theme  # noqa: E402

theme.apply(APP)
prefs.use_file(Path(tempfile.mkdtemp()) / "p.ini")


def make_dialog(*buttons):
    dialog = QDialog()
    dialog.resize(320, 160)
    column = QVBoxLayout(dialog)
    for button in buttons:
        column.addWidget(button)
    dialog.show()
    APP.processEvents()
    return dialog


class Glass(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("traceback.print_exc")  # ошибки фильтра не должны проходить молча
        self.errors = patcher.start()
        self.addCleanup(patcher.stop)

    def test_states_paint_without_errors(self):
        plain, primary, danger, off = (QPushButton(t) for t in ("Отмена", "Сохранить", "Удалить", "Выключена"))
        theme.kind(primary, "primary")
        theme.kind(danger, "danger")
        off.setEnabled(False)
        eye = QToolButton()
        eye.setCheckable(True)
        eye.setChecked(True)
        dialog = make_dialog(plain, primary, danger, off, eye)
        self.assertFalse(dialog.grab().isNull())
        QTest.mousePress(primary, Qt.LeftButton, Qt.NoModifier, QPoint(5, 5))  # нажатие и свечение нажатия
        APP.processEvents()
        dialog.grab()
        QTest.mouseRelease(primary, Qt.LeftButton, Qt.NoModifier, QPoint(5, 5))
        self.errors.assert_not_called()

    def test_button_text_is_drawn_and_kinds_differ(self):
        with_text, empty, primary = QPushButton("Текст"), QPushButton(""), QPushButton("Текст")
        theme.kind(primary, "primary")
        for button in (with_text, empty, primary):
            button.setFixedSize(120, 34)
        dialog = make_dialog(with_text, empty, primary)
        picture = dialog.grab().toImage()
        region = lambda b: picture.copy(b.geometry())  # noqa: E731
        self.assertNotEqual(region(with_text), region(primary))
        # надпись есть: в середине кнопки встречаются почти белые точки, а у пустой — нет
        bright = lambda image: sum(image.pixelColor(x, 17).lightness() > 200 for x in range(30, 90))  # noqa: E731
        self.assertGreater(bright(region(with_text)), 0)
        self.assertEqual(bright(region(empty)), 0)

    def test_clear_button_in_a_field_is_not_glass(self):
        field = QLineEdit("текст")
        field.setClearButtonEnabled(True)
        dialog = make_dialog(field)  # ссылка на окно: иначе поле удалится вместе с ним
        self.assertTrue(dialog.isVisible())
        inner = field.findChildren(QToolButton)
        self.assertTrue(inner)
        self.assertFalse(theme._is_glass_button(inner[0]))

    def test_paint_error_falls_back_to_the_usual_look(self):
        dialog = make_dialog(QPushButton("Кнопка"))
        with mock.patch.object(theme, "_paint_glass", side_effect=RuntimeError("сбой")):
            self.assertFalse(dialog.grab().isNull())  # Qt нарисовал сам по оформлению STYLE
        self.assertTrue(self.errors.called)

    def test_unusual_buttons_are_left_to_qt(self):
        from PySide6.QtGui import QIcon, QPixmap
        from PySide6.QtWidgets import QMenu
        picture = QPixmap(8, 8)
        picture.fill(Qt.white)
        with_icon, with_menu, plain = QPushButton(QIcon(picture), "Значок"), QPushButton("Меню"), QPushButton("Текст")
        with_menu.setMenu(QMenu(with_menu))
        arrow, text_tool, eye = QToolButton(), QToolButton(), QToolButton()
        arrow.setArrowType(Qt.DownArrow)
        text_tool.setText("Текст")
        for button in (with_icon, with_menu, arrow, text_tool):
            self.assertFalse(theme._is_glass_button(button))
        for button in (plain, eye):
            self.assertTrue(theme._is_glass_button(button))

    def test_scene_size_is_limited_and_empty_size_is_safe(self):
        sharp, _small = theme._scene(100000, 50)
        self.assertLessEqual(max(sharp.width(), sharp.height()), theme._SCENE_MAX)
        self.assertFalse(theme._scene(0, 0)[0].isNull())

    def test_scene_cache_is_limited(self):
        for size in range(100, 130):
            theme._scene(size, size)
        self.assertLessEqual(len(theme._SCENES), theme._SCENE_LIMIT)

    def test_painting_is_fast_enough(self):
        buttons = [QPushButton(f"Кнопка {n}") for n in range(8)]
        dialog = make_dialog(*buttons)
        started = time.perf_counter()
        for _ in range(30):
            dialog.grab()
        self.assertLess((time.perf_counter() - started) / 30, 0.1)  # меньше 0,1 с на всё окно


class IconButton(unittest.TestCase):
    def test_glyph_is_centered(self):
        """Замок на кнопке блокировки: шрифт держит значок не посреди ячейки, он съезжал вправо."""
        button = QPushButton(theme.GLYPHS["lock"])
        button.resize(46, 34)
        button.show()
        APP.processEvents()
        with_glyph = button.grab().toImage()
        button.setText("")
        button.resize(46, 34)
        APP.processEvents()
        empty = button.grab().toImage()
        ink = [(x, y) for y in range(with_glyph.height()) for x in range(with_glyph.width())
               if abs(with_glyph.pixelColor(x, y).lightness() - empty.pixelColor(x, y).lightness()) > 60]
        self.assertTrue(ink)
        xs, ys = [p[0] for p in ink], [p[1] for p in ink]
        self.assertLessEqual(abs(min(xs) + max(xs) + 1 - with_glyph.width()) / 2, 0.5)
        self.assertLessEqual(abs(min(ys) + max(ys) + 1 - with_glyph.height()) / 2, 0.5)
        button.close()


if __name__ == "__main__":
    unittest.main()


class SystemGlass(unittest.TestCase):
    """Системное стекло macOS (gui/sysglass.py): без настоящего экрана выключено, а рисование поверх него не падает."""

    def setUp(self):
        patcher = mock.patch("traceback.print_exc")
        self.errors = patcher.start()
        self.addCleanup(patcher.stop)

    def test_off_without_a_real_screen(self):
        from gui import sysglass
        self.assertFalse(sysglass.available())  # offscreen: родных окон нет
        self.assertFalse(theme.SYSTEM)

    def test_preference_defaults_to_on_and_can_be_turned_off(self):
        self.assertTrue(prefs.system_glass())
        prefs.set_value("system_glass", False)
        self.addCleanup(prefs.set_value, "system_glass", True)
        self.assertFalse(prefs.system_glass())

    def test_painting_over_system_glass(self):
        from PySide6.QtWidgets import QFrame
        card = QFrame()
        theme.role(card, "card")
        primary = QPushButton("Сохранить")
        theme.kind(primary, "primary")
        with mock.patch.object(theme, "SYSTEM", True), \
                mock.patch.object(theme, "_scene", side_effect=AssertionError("сцена под стеклом не нужна")):
            dialog = make_dialog(card, primary, QPushButton("Отмена"))
            image = dialog.grab().toImage()
        self.assertFalse(image.isNull())
        self.errors.assert_not_called()
        dialog.close()

    def test_small_margins_are_not_trimmed(self):
        from gui import sysglass
        dialog = QDialog()
        column = QVBoxLayout(dialog)
        column.setContentsMargins(11, 11, 11, 11)
        sysglass._trim_top(dialog)
        self.assertEqual(column.contentsMargins().top(), 11)
        column.setContentsMargins(24, 20, 24, 20)  # как у главного окна и окна входа
        sysglass._trim_top(dialog)
        self.assertEqual(column.contentsMargins().top(), 8)

    def test_window_drags_by_empty_places_only(self):
        """Полосу заголовка закрывает стекло: окно тянется за фон и подписи, но не за кнопки и ссылки."""
        from PySide6.QtGui import QWindow
        from PySide6.QtWidgets import QLabel
        label, link, button = QLabel("Подпись"), QLabel('<a href="#x">ссылка</a>'), QPushButton("Кнопка")
        dialog = make_dialog(label, link, button)
        clicks = []
        button.pressed.connect(lambda: clicks.append(1))
        with mock.patch.object(theme, "SYSTEM", True), \
                mock.patch.object(QWindow, "startSystemMove", return_value=True) as move:
            link.adjustSize()
            for widget, point in ((button, QPoint(3, 3)), (link, QPoint(8, link.height() // 2))):
                QTest.mousePress(widget, Qt.LeftButton, Qt.NoModifier, point)
                QTest.mouseRelease(widget, Qt.LeftButton, Qt.NoModifier, point)
            move.assert_not_called()
            QTest.mousePress(label, Qt.LeftButton, Qt.NoModifier, QPoint(3, 3))
            QTest.mousePress(dialog, Qt.LeftButton, Qt.NoModifier, QPoint(1, 1))
            self.assertEqual(move.call_count, 2)
        self.assertEqual(clicks, [1])
        self.errors.assert_not_called()
        dialog.close()
