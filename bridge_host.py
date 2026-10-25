"""Мост: браузер запускает его, когда расширение WhoKey просит пароль.

Без окон и без Qt — только пересылает запросы расширения в открытый WhoKey
(см. bridge_protocol.py). Если WhoKey закрыт или заблокирован, открывает его
и ждёт, пока человек введёт мастер-пароль, сообщая расширению «жду».
Работает, пока расширение держит соединение, и отвечает на каждое сообщение.
"""

import os
import select
import socket
import sys
import time

import bridge_protocol as P

WAIT_FOR_UNLOCK = 90  # секунд: открыть WhoKey и ввести мастер-пароль


def browser_left(stdin, seconds):
    """Ждёт seconds; True — если браузер за это время закрыл соединение.

    Пока мост ждёт мастер-пароль, расширение может передумать (человек закрыл
    WhoKey и нажал кнопку ещё раз — расширение запускает новый мост, а старый
    отключает). Без этой проверки старый мост висел бы все 90 секунд.
    """
    if os.name == "nt":  # select на Windows не работает с каналами — просто ждём
        time.sleep(seconds)
        return False
    ready, _, _ = select.select([stdin], [], [], seconds)
    return bool(ready) and stdin.peek(1) == b""  # «готов к чтению», но читать нечего — это конец


def forward(message, stdin, out, origin):
    """Пересылает запрос в WhoKey; если тот не слушает — открывает его и ждёт.

    None — браузер ушёл, пока мост ждал (отвечать уже некому).
    """
    message["origin"] = origin  # какое расширение спрашивает
    try:
        return P.ask_app(message)
    except socket.timeout:
        # WhoKey есть, но долго думает (человек решает, разрешать ли расширение) —
        # это не «WhoKey закрыт»: открывать его заново и повторять запрос нельзя
        return {"status": "timeout"}
    except P.PeerError:
        return {"status": "fake_app"}  # на сокете не WhoKey — ничего ему не отправили
    except OSError:
        pass
    P.write_message(out, {"status": "waiting"})  # расширение покажет «введи мастер-пароль»
    P.launch_app()
    deadline = time.monotonic() + WAIT_FOR_UNLOCK
    while time.monotonic() < deadline:
        if browser_left(stdin, 0.5):
            return None
        try:
            return P.ask_app(message)
        except socket.timeout:
            return {"status": "timeout"}
        except P.PeerError:
            return {"status": "fake_app"}
        except OSError:
            continue
    return {"status": "locked"}


def main():
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    origin = sys.argv[1] if len(sys.argv) > 1 else ""
    while True:
        try:
            message = P.read_message(stdin)
        except (ValueError, RecursionError):
            # не JSON — от браузера такого не бывает: отвечаем ошибкой и никуда не пересылаем
            P.write_message(stdout, {"status": "error"})
            continue
        if message is None:  # браузер закрыл соединение — работа окончена
            return
        if not isinstance(message, dict):
            P.write_message(stdout, {"status": "error"})
            continue
        reply = forward(message, stdin, stdout, origin)
        if reply is None:  # браузер закрыл соединение, пока ждали WhoKey
            return
        P.write_message(stdout, reply)
