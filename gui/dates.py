"""Даты записей и журнала: коротко в списках («сегодня, 09:12», «вчера», «14 сент.»)
и полностью в подсказках — на выбранном языке."""

from PySide6.QtCore import QDate, QDateTime, QLocale

from gui import i18n
from gui.i18n import tr


def _locale():
    return QLocale("ru_RU" if i18n.LANG == "ru" else "en_US")


def full_date(stamp):
    """«2026-10-27 22:54» из хранилища — в привычном виде для выбранного языка."""
    moment = QDateTime.fromString(stamp, "yyyy-MM-dd HH:mm")
    if not moment.isValid():
        return stamp
    return _locale().toString(moment, QLocale.ShortFormat)


def shown_date(stamp):
    """Коротко, как в почте: «сегодня, 09:12», «вчера», «14 сент.», «20 дек. 2025»."""
    moment = QDateTime.fromString(stamp, "yyyy-MM-dd HH:mm")
    if not moment.isValid():
        return stamp
    days = moment.date().daysTo(QDate.currentDate())
    if days == 0:
        return tr("today, {time}").format(time=moment.toString("HH:mm"))
    if days == 1:
        return tr("yesterday")
    if moment.date().year() == QDate.currentDate().year():
        return _locale().toString(moment.date(), "d MMM")
    return _locale().toString(moment.date(), "d MMM yyyy")
