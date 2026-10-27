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

if os.name == "nt":
    import ctypes
    import msvcrt

import bridge_protocol as P

WAIT_FOR_UNLOCK = 90  # секунд: открыть WhoKey и ввести мастер-пароль


def browser_left(stdin, seconds):
    """Ждёт seconds; True — если браузер за это время закрыл соединение.

    Пока мост ждёт мастер-пароль, расширение может передумать (человек закрыл
    WhoKey и нажал кнопку ещё раз — расширение запускает новый мост, а старый
    отключает). Без этой проверки старый мост висел бы все 90 секунд.
    """
    if os.name == "nt":  # select на Windows не работает с каналами — спрашиваем сам канал
        try:
            handle = msvcrt.get_osfhandle(stdin.fileno())
        except (AttributeError, OSError, ValueError):  # не настоящий канал (в тестах) — просто ждём
            time.sleep(seconds)
            return False
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if not P.pipe_alive(handle):
                return True
            time.sleep(0.1)
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


def std_streams():
    """Каналы к браузеру: stdin и stdout в двоичном виде.

    Собранный WhoKey на Windows — программа с окнами, и Python может не создать
    sys.stdin / sys.stdout. Тогда берём каналы, которые передал браузер, напрямую.
    Двоичный режим — иначе Windows дописывала бы к переводам строк лишний символ
    и портила длину сообщений.
    """
    if os.name != "nt":
        return sys.stdin.buffer, sys.stdout.buffer
    streams = []
    for stream, number, mode in ((sys.stdin, -10, "rb"), (sys.stdout, -11, "wb")):
        if stream is not None and getattr(stream, "buffer", None) is not None:
            try:
                msvcrt.setmode(stream.fileno(), os.O_BINARY)
            except (AttributeError, OSError, ValueError):
                pass  # не настоящий канал (в тестах) — режим не нужен
            streams.append(stream.buffer)
            continue
        get_handle = ctypes.windll.kernel32.GetStdHandle
        get_handle.restype = ctypes.c_void_p
        handle = get_handle(number)  # STD_INPUT_HANDLE / STD_OUTPUT_HANDLE
        fd = msvcrt.open_osfhandle(handle, os.O_BINARY)
        streams.append(os.fdopen(fd, mode))
    return streams[0], streams[1]


def main():
    stdin, stdout = std_streams()
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
