"""Системное стекло macOS: под окном лежит настоящее размытие рабочего стола (NSVisualEffectView),
а WhoKey рисует поверх него полупрозрачную вуаль и пятна света (theme._paint_wash):
в тёмной теме — индиго и неон, в светлой — перламутр и пастель.

Только macOS и только через PyObjC. Если чего-то нет (другая система, нет PyObjC, в настройках
доступности включено «Уменьшить прозрачность» или человек выключил прозрачный фон в «Настройках»),
available() отвечает False, и окна рисуются как раньше — нарисованным стеклом.

Вид материала кладётся в рамку окна ПОД вид Qt, а не вместо него: если подменить contentView,
Qt перестаёт узнавать своё окно, и hide() оставляет на экране пустой «призрак».
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
