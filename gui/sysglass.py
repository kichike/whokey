"""Системное стекло macOS: под окном лежит настоящее размытие рабочего стола (NSVisualEffectView),
а WhoKey рисует поверх него полупрозрачную вуаль и пятна света (theme._paint_wash):
в тёмной теме — индиго и неон, в светлой — перламутр и пастель.

Только macOS и только через PyObjC. Если чего-то нет (другая система, нет PyObjC, в настройках
доступности включено «Уменьшить прозрачность» или человек выключил прозрачный фон в «Настройках»),
available() отвечает False, и окна рисуются как раньше — нарисованным стеклом.

Вид материала кладётся в рамку окна ПОД вид Qt, а не вместо него: если подменить contentView,
Qt перестаёт узнавать своё окно, и hide() оставляет на экране пустой «призрак».

Родное жидкое стекло (macOS 26+, NSGlassEffectView; liquid_available): над размытием и ПОД видом Qt
ложатся ещё два слоя (класс Liquid): вуаль окна родной картинкой (theme.wash_image — стекло
преломляет и её) и NSGlassEffectContainerView с NSGlassEffectView под карточкой, полем поиска,
группой кнопок, замком, кнопками и полями. Qt над ними рисует только текст, значки, пилюлю группы,
разделители и рамку фокуса. Что стеклянное и каким оттенком — решает theme (native_look):
здесь только механика — создать, подогнать рамки, перекрасить. Где родного стекла нет
(macOS < 26, «Уменьшить прозрачность», выключенный прозрачный фон, prefs native_glass, Windows,
Linux, тесты без экрана) — остаются нарисованные пластины theme.
"""

import sys

from PySide6.QtWidgets import QDialog, QMainWindow, QWidget

CORNER = 16.0     # скругление окна macOS: материал обрезается по нему же
TOP_TRIM = 12     # Qt сам опускает содержимое под полосу заголовка (safe area), лишний воздух сверху убираем

_DONE = "_whokey_glass"  # свойство окна: для какого NSWindow стекло уже поставлено


def available():
    if sys.platform != "darwin":
        return False
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.platformName() != "cocoa":  # тесты и снимки без экрана (offscreen): родных окон нет
        return False
    try:
        import AppKit
    except ImportError:
        return False
    try:
        return not AppKit.NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceTransparency()
    except Exception:
        return False


def is_window(obj):
    """Окна, которым нужно стекло: главное, вход, все диалоги, меню правого клика и выпадающие списки
    (их помечает theme.rounded_menu / rounded_popup свойством glassPopup). Подсказки — нет."""
    if not isinstance(obj, QWidget) or not obj.isWindow():
        return False
    return (isinstance(obj, (QMainWindow, QDialog)) or obj.property("role") == "backdrop"
            or obj.property("glassPopup") is True)


def prepare(window):
    """До создания родного окна: фон окна прозрачный, иначе macOS зальёт его сплошным цветом."""
    from PySide6.QtCore import Qt
    window.setAttribute(Qt.WA_TranslucentBackground, True)


def attach(window, light=False):
    """При показе окна: прозрачная полоса заголовка, материал под содержимым. Повторно — ничего не делает.
    light — светлая тема: светлый материал (см. set_light)."""
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.platformName() != "cocoa":  # winId() здесь не NSView — PyObjC упал бы
        return
    import AppKit
    import objc
    view = objc.objc_object(c_void_p=int(window.winId()))
    ns_window = view.window()
    if ns_window is None:
        return
    number = int(ns_window.windowNumber()) or id(ns_window)
    if window.property(_DONE) == number:
        return
    first = window.property(_DONE) is None
    window.setProperty(_DONE, number)

    ns_window.setStyleMask_(ns_window.styleMask() | AppKit.NSWindowStyleMaskFullSizeContentView)
    ns_window.setTitlebarAppearsTransparent_(True)
    ns_window.setTitleVisibility_(AppKit.NSWindowTitleHidden)
    ns_window.setOpaque_(False)
    ns_window.setBackgroundColor_(AppKit.NSColor.clearColor())

    content = ns_window.contentView()
    frame_view = content.superview()
    fx = AppKit.NSVisualEffectView.alloc().initWithFrame_(frame_view.bounds())
    fx.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
    fx.setState_(AppKit.NSVisualEffectStateActive)
    _look(fx, light)
    fx.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
    fx.setWantsLayer_(True)
    fx.layer().setCornerRadius_(float(window.property("glassRadius") or CORNER))  # у меню скругление меньше
    fx.layer().setMasksToBounds_(True)
    if fx.layer().respondsToSelector_("setCornerCurve:"):
        fx.layer().setCornerCurve_("continuous")
    frame_view.addSubview_positioned_relativeTo_(fx, AppKit.NSWindowBelow, content)
    ns_window.invalidateShadow()

    if first:
        _trim_top(window)
    try:  # последним и без падения: закрытые виды AppKit могут поменяться в будущих macOS
        _clear_titlebar(ns_window)
    except Exception:
        pass
    if _LOOKS is not None and window.property("glassPopup") is not True and liquid_available():
        old = getattr(window, "_liquid", None)
        if old is not None:
            old.drop()  # родное окно пересоздано (новый номер) — прежние слои остались в старом
        try:
            window._liquid = Liquid(window, frame_view, content, fx, light)
        except Exception:  # родное стекло не встало — окно остаётся с нарисованным
            import traceback
            traceback.print_exc()
            window._liquid = None
    if window.property("glassPopup") is True and not window.property("glassAttached"):
        # размытие под меню есть — теперь его заливку можно сделать тонкой (theme: [glassAttached="true"])
        window.setProperty("glassAttached", True)
        for widget in [window] + window.findChildren(QWidget):  # и список внутри выпадающего окошка
            widget.style().unpolish(widget)
            widget.style().polish(widget)


def _clear_titlebar(ns_window):
    """Новые macOS кладут под полосу заголовка свою подложку и «край» с резкой границей — поверх
    нашего фона это выглядело серой полосой. Подложку прячем, кнопки окна остаются."""
    import AppKit
    if ns_window.respondsToSelector_("setTitlebarSeparatorStyle:"):
        ns_window.setTitlebarSeparatorStyle_(AppKit.NSTitlebarSeparatorStyleNone)
    frame_view = ns_window.contentView().superview()
    for container in frame_view.subviews():
        if container.className() != "NSTitlebarContainerView":
            continue
        for view in container.subviews():
            if view.className() in ("NSTitlebarBackgroundView", "_NSTitlebarDecorationView"):
                view.setHidden_(True)


def _look(fx, light):
    """Тёмная тема — тёмный материал HUD: пропускает цвета рабочего стола, текст читается.
    Светлая — светлая матовая изморозь (материал всплывающих окон в светлом оформлении)."""
    import AppKit
    fx.setMaterial_(AppKit.NSVisualEffectMaterialPopover if light else AppKit.NSVisualEffectMaterialHUDWindow)
    fx.setAppearance_(AppKit.NSAppearance.appearanceNamed_(
        AppKit.NSAppearanceNameAqua if light else AppKit.NSAppearanceNameDarkAqua))


def set_light(window, light):
    """Смена темы на лету: перекрашивает материал под уже открытым окном."""
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.platformName() != "cocoa" or window.property(_DONE) is None:
        return
    import AppKit
    import objc
    ns_window = objc.objc_object(c_void_p=int(window.winId())).window()
    if ns_window is None:
        return
    for view in ns_window.contentView().superview().subviews():
        if view.isKindOfClass_(AppKit.NSVisualEffectView):
            _look(view, light)
    liquid = getattr(window, "_liquid", None)
    if liquid is not None:
        liquid.restyle(light)  # оттенки родного стекла и вуаль — под новую тему или палитру котика


def _trim_top(window):
    layout = window.centralWidget().layout() if isinstance(window, QMainWindow) and window.centralWidget() else window.layout()
    if layout is None:
        return
    margins = layout.contentsMargins()
    if margins.top() < 16:  # маленькие стандартные поля (Настройки, вопросы) не трогаем
        return
    layout.setContentsMargins(margins.left(), max(4, margins.top() - TOP_TRIM), margins.right(), margins.bottom())


def fit_height(window):
    """Полоса заголовка теперь часть окна: диалог, подогнанный по содержимому, становится выше на её высоту."""
    from PySide6.QtCore import Qt
    if window.testAttribute(Qt.WA_ContentsMarginsRespectsSafeArea):
        # Qt отступает под полосой заголовка («безопасная зона»), но в нужный размер окна этот отступ
        # не считает: окна выходили ниже, чем надо, и текст сплющивался (вопросы, генератор).
        # Делаем отступ обычным полем окна — его Qt учитывает везде, и QMessageBox тоже.
        safe = window.contentsMargins()
        window.setAttribute(Qt.WA_ContentsMarginsRespectsSafeArea, False)
        own = window.contentsMargins()
        window.setContentsMargins(own.left(), safe.top(), own.right(), own.bottom())
        window.updateGeometry()
        if window.minimumHeight() == window.maximumHeight():  # QMessageBox: пусть пересчитает свой размер
            window.adjustSize()
    # естественная высота, а не минимальная: при минимальной строки (оценка пароля в генераторе) сжимались
    need = max(window.minimumSizeHint().height(), window.sizeHint().height())
    layout = window.layout()
    if layout is not None and layout.hasHeightForWidth():  # текст с переносом строк: высота зависит от ширины
        # поля самого окна считаем отдельно: на Mac сверху их больше (полоса заголовка), а Qt о них забывает
        margins = window.contentsMargins()
        inner = window.width() - margins.left() - margins.right()
        need = max(need, margins.top() + margins.bottom() + layout.heightForWidth(inner))
    if window.height() >= need:
        return
    if window.minimumHeight() != window.maximumHeight():  # у QMessageBox размер постоянный — см. выше
        window.resize(window.width(), need)


# --- родное жидкое стекло (macOS 26+) ---

_LOOKS = None  # (look, wash) из theme — задаёт use_looks; None — родного стекла нет


def use_looks(look, wash):
    """theme передаёт сюда вид стекла: look(widget) -> None (стекла нет) или (QColor оттенка с альфой,
    стиль 0 обычный / 1 прозрачный, скругление); wash(width, height) -> QImage вуали окна."""
    global _LOOKS
    _LOOKS = (look, wash)


def liquid_available():
    """Есть ли настоящее жидкое стекло (macOS 26 Tahoe и новее) и можно ли его включать."""
    if _LOOKS is None or not available():
        return False
    import objc
    try:
        objc.lookUpClass("NSGlassEffectView")
        objc.lookUpClass("NSGlassEffectContainerView")
    except objc.nosuchclass_error:
        return False
    return True


def has_liquid(widget):
    """Под элементом лежит родное стекло: нарисованную пластину не рисуем (theme._glass_b)."""
    return widget.property("nativeGlass") is True


def _ns_color(color):
    import AppKit
    return AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(color.redF(), color.greenF(), color.blueF(), color.alphaF())


def _ns_image(image):
    """QImage -> NSImage через PNG."""
    import AppKit
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return AppKit.NSImage.alloc().initWithData_(AppKit.NSData.dataWithBytes_length_(bytes(data), data.size()))


class Liquid:
    """Родное стекло одного окна: вуаль, контейнер, по NSGlassEffectView на элемент — и их подгонка.

    Рамки подгоняются по событиям окна и элементов (сдвиг, размер, показ, скрытие, раскладка);
    стекло под Qt мышь не получает, поэтому наведение и нажатие показывает оттенок (theme._state).
    Новые элементы (диалог добавил поле) находятся при следующей раскладке или показе."""

    SPACING = 6.0  # стёкла ближе этого сливаются в одну каплю; группа и замок стоят на 12 — не сливаются
    WASH_MS = 120  # вуаль перерисовывается, когда растягивание закончилось (до того — растягивается)

    def __init__(self, window, frame_view, qt_view, under, light):
        import AppKit
        import objc
        from PySide6.QtCore import QObject, QTimer
        self.window, self.frame_view, self.qt_view, self.light = window, frame_view, qt_view, light
        self.glass_class = objc.lookUpClass("NSGlassEffectView")
        bounds = frame_view.bounds()
        sizable = AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable

        self.backdrop = AppKit.NSImageView.alloc().initWithFrame_(bounds)  # вуаль окна
        self.backdrop.setImageScaling_(AppKit.NSImageScaleAxesIndependently)
        self.backdrop.setAutoresizingMask_(sizable)
        self.backdrop.setWantsLayer_(True)
        self.backdrop.layer().setCornerRadius_(float(window.property("glassRadius") or CORNER))
        self.backdrop.layer().setMasksToBounds_(True)
        frame_view.addSubview_positioned_relativeTo_(self.backdrop, AppKit.NSWindowAbove, under)

        self.container = objc.lookUpClass("NSGlassEffectContainerView").alloc().initWithFrame_(bounds)
        self.container.setSpacing_(self.SPACING)
        self.container.setAutoresizingMask_(sizable)
        self.holder = AppKit.NSView.alloc().initWithFrame_(bounds)  # контейнер показывает стёкла через contentView
        self.holder.setAutoresizingMask_(sizable)
        self.container.setContentView_(self.holder)
        frame_view.addSubview_positioned_relativeTo_(self.container, AppKit.NSWindowAbove, self.backdrop)

        self.pairs = {}  # QWidget -> NSGlassEffectView
        self._wash_size = None
        self._rescan = False
        layer = self

        class Watcher(QObject):
            def eventFilter(self, obj, event):
                try:
                    layer._event(obj, event)
                except Exception:  # подгонка стекла не должна ломать окно
                    import traceback
                    traceback.print_exc()
                return False

        self.watcher = Watcher(window)
        self.timer = QTimer(self.watcher)  # одна подгонка на пачку событий — после раскладки
        self.timer.setSingleShot(True)
        self.timer.setInterval(0)
        self.timer.timeout.connect(self._flush)
        self.wash_timer = QTimer(self.watcher)
        self.wash_timer.setSingleShot(True)
        self.wash_timer.setInterval(self.WASH_MS)
        self.wash_timer.timeout.connect(self._paint_wash)
        window.installEventFilter(self.watcher)
        self._set_appearance()
        self.scan()
        self._paint_wash()

    # --- элементы ---

    def scan(self):
        """Находит в окне всё, чему положено родное стекло, и заводит стекло новым элементам."""
        from PySide6.QtWidgets import QWidget
        from shiboken6 import isValid
        if not isValid(self.window):
            return
        look = _LOOKS[0]
        for widget in self.window.findChildren(QWidget):
            if widget in self.pairs or widget.window() is not self.window or look(widget) is None:
                continue
            glass = self.glass_class.alloc().initWithFrame_(((0, 0), (1, 1)))
            self.holder.addSubview_(glass)
            self.pairs[widget] = glass
            widget.setProperty("nativeGlass", True)  # theme: пластину не рисовать, только текст и фокус
            widget.installEventFilter(self.watcher)
            widget.destroyed.connect(lambda *_, w=widget: self._forget(w))
            self._tint(widget)
            widget.update()
        self.sync()

    def _forget(self, widget):
        glass = self.pairs.pop(widget, None)
        if glass is not None:
            glass.removeFromSuperview()

    def _tint(self, widget):
        from shiboken6 import isValid
        glass = self.pairs.get(widget)
        if glass is None or not isValid(widget):
            return
        found = _LOOKS[0](widget)
        if found is None:  # элемент больше не стеклянный (переехал в карточку…) — прячем
            glass.setHidden_(True)
            return
        tint, style, radius = found
        glass.setStyle_(style)
        glass.setCornerRadius_(radius)
        glass.setTintColor_(_ns_color(tint))

    def sync(self):
        """Стекло встаёт точно под свой элемент; скрытый элемент — стекло тоже прячется."""
        from shiboken6 import isValid
        if not isValid(self.window):
            return
        shown = self.window.isVisible()
        for widget, glass in list(self.pairs.items()):
            if not isValid(widget):
                self._forget(widget)
                continue
            visible = shown and widget.isVisibleTo(self.window) and widget.width() > 0 and widget.height() > 0
            glass.setHidden_(not visible)
            if not visible:
                continue
            corner = widget.mapTo(self.window, widget.rect().topLeft())
            # Qt считает в точках от левого верхнего угла, вид Qt «перевёрнут» так же —
            # прямоугольник достаточно перевести в систему координат контейнера
            rect = ((corner.x(), corner.y()), (widget.width(), widget.height()))
            glass.setFrame_(self.qt_view.convertRect_toView_(rect, self.holder))

    def _event(self, obj, event):
        from PySide6.QtCore import QEvent, QTimer
        kind = event.type()
        if kind in (QEvent.Move, QEvent.Resize, QEvent.Show, QEvent.Hide, QEvent.LayoutRequest,
                    QEvent.ShowToParent, QEvent.HideToParent, QEvent.ParentChange):
            if kind in (QEvent.LayoutRequest, QEvent.Show) and obj is self.window:
                self._rescan = True  # раскладка поменялась — могли появиться элементы
            self.timer.start()
            if obj is self.window and kind == QEvent.Resize:
                self.wash_timer.start()
            elif kind == QEvent.Resize and obj in self.pairs:
                self._tint(obj)  # скругление — от высоты: при первом взгляде элемент мог быть ещё нулевым
        elif obj in self.pairs and kind in (QEvent.Enter, QEvent.Leave, QEvent.MouseButtonPress,
                                            QEvent.MouseButtonRelease, QEvent.EnabledChange):
            QTimer.singleShot(0, lambda w=obj: self._tint(w))  # после события: isDown/underMouse уже новые

    def _flush(self):
        rescan, self._rescan = self._rescan, False
        self.scan() if rescan else self.sync()

    # --- тема ---

    def restyle(self, light):
        """Тема или палитра (котик) сменилась: оттенки, светлое/тёмное оформление стекла, вуаль."""
        self.light = light
        self._set_appearance()
        for widget in list(self.pairs):
            self._tint(widget)
        self._wash_size = None
        self._paint_wash()

    def _set_appearance(self):
        import AppKit
        self.container.setAppearance_(AppKit.NSAppearance.appearanceNamed_(
            AppKit.NSAppearanceNameAqua if self.light else AppKit.NSAppearanceNameDarkAqua))

    def _paint_wash(self):
        from shiboken6 import isValid
        if not isValid(self.window):
            return
        size = (max(1, self.window.width()), max(1, self.window.height()))
        if size != self._wash_size:
            self._wash_size = size
            self.backdrop.setImage_(_ns_image(_LOOKS[1](*size)))

    def drop(self):
        """Убирает слои (родное окно пересоздано)."""
        from shiboken6 import isValid
        for widget, glass in list(self.pairs.items()):
            glass.removeFromSuperview()
            if isValid(widget):
                widget.setProperty("nativeGlass", False)
                widget.removeEventFilter(self.watcher)
        self.pairs.clear()
        self.container.removeFromSuperview()
        self.backdrop.removeFromSuperview()
        if isValid(self.window):
            self.window.removeEventFilter(self.watcher)

    def report(self):
        """Для проверок: под каким элементом какое стекло, где и каким оттенком."""
        from shiboken6 import isValid
        rows = []
        for widget, glass in self.pairs.items():
            if not isValid(widget):
                continue
            back = self.qt_view.convertRect_fromView_(glass.frame(), self.holder)
            corner = widget.mapTo(self.window, widget.rect().topLeft())
            tint = glass.tintColor()
            rows.append({"widget": type(widget).__name__, "name": widget.objectName() or str(widget.property("role") or widget.property("kind") or ""),
                         "text": (widget.text() if hasattr(widget, "text") and callable(widget.text) else "")[:20],
                         "qt": (corner.x(), corner.y(), widget.width(), widget.height()),
                         "ns": (back.origin.x, back.origin.y, back.size.width, back.size.height),
                         "hidden": bool(glass.isHidden()), "style": int(glass.style()), "radius": round(glass.cornerRadius(), 1),
                         "tint": None if tint is None else tuple(round(v, 3) for v in (
                             tint.redComponent(), tint.greenComponent(), tint.blueComponent(), tint.alphaComponent()))})
        return rows
