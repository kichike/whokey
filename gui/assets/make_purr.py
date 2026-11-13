"""Рисует звук пасхалки purr.wav — мурлыканье котика. Синтез, никаких чужих записей.
Запуск: python3 gui/assets/make_purr.py

Мурлыканье — глухие хлопки гортани ~25 раз в секунду: на вдохе тише и чуть чаще, на выдохе громче.
Сами хлопки низкие (ниже 150 Гц), а динамики ноутбука такие почти не играют — поэтому каждый хлопок
ещё и «звенит» в горле: резонанс около 380 Гц делает мурлыканье слышным на любом динамике.
Случайность с постоянным зерном: файл всегда один и тот же.
"""

import math
import random
import struct
import wave
from pathlib import Path

RATE = 22050
SECONDS = 1.7
INHALE = 0.72   # секунд: вдох, потом короткая пауза
EXHALE = 0.78   # с этого момента — выдох


def _resonator(freq, bandwidth):
    """Двухполюсный резонатор: пропускает полосу вокруг freq."""
    r = math.exp(-math.pi * bandwidth / RATE)
    b1, b2 = 2 * r * math.cos(2 * math.pi * freq / RATE), -r * r
    state = [0.0, 0.0]

    def step(x):
        y = (1 - r) * x + b1 * state[0] + b2 * state[1]
        state[1], state[0] = state[0], y
        return y
    return step


def samples():
    noise = random.Random(7)
    throat = _resonator(380, 160)
    low1 = low2 = phase = 0.0
    result = []
    for i in range(int(RATE * SECONDS)):
        t = i / RATE
        exhale = t >= EXHALE
        phase = (phase + (24 if exhale else 27) / RATE) % 1.0
        pulse = math.exp(-phase * 9)  # хлопок в начале каждого периода, затухает
        if exhale:
            breath = math.sin(math.pi * min(1, (t - EXHALE) / (SECONDS - EXHALE)))
        else:
            breath = math.sin(math.pi * min(1, t / INHALE)) * 0.7 if t < INHALE else 0.0
        breath = max(0.0, breath) ** 0.6
        raw = (noise.uniform(-1, 1) * 0.8 + math.sin(2 * math.pi * 110 * t) * 0.5) * pulse * breath
        low1 += 0.2 * (raw - low1)  # дважды срезаем верхи: глухое «урр»
        low2 += 0.2 * (low1 - low2)
        result.append(low2 + throat(raw) * 0.9)
    peak = max(abs(s) for s in result) or 1
    return [s / peak * 0.7 for s in result]


def main():
    target = Path(__file__).parent / "purr.wav"
    with wave.open(str(target), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in samples()))


if __name__ == "__main__":
    main()
