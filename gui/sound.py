"""Звук пасхалки. Средствами системы: ради одного звука модуль QtMultimedia в программу не тянем.
Не вышло сыграть — ничего страшного, просто тишина."""

import sys
from pathlib import Path

from PySide6.QtCore import QFile, QProcess

FART_FILE = Path(__file__).parent / "assets" / "fart.wav"


def play_fart():
    if not QFile.exists(str(FART_FILE)):
        return
    if sys.platform == "win32":
        try:
            import winsound
            winsound.PlaySound(str(FART_FILE), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except (ImportError, RuntimeError):
            pass
    elif sys.platform == "darwin":
        QProcess.startDetached("/usr/bin/afplay", [str(FART_FILE)])  # полный путь: не чужая программа из PATH
    else:
        for player in ("/usr/bin/pw-play", "/usr/bin/paplay", "/usr/bin/aplay"):  # PipeWire, PulseAudio, ALSA
            if QFile.exists(player):
                QProcess.startDetached(player, [str(FART_FILE)])
                break
