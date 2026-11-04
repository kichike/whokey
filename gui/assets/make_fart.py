"""Рисует звук пасхалки fart.wav — синтез, никаких чужих записей. Запуск: python3 gui/assets/make_fart.py

Звук — низкие частые хлопки (как губной «пук»): частота плавает и падает к концу,
громкость дрожит, сверху немного шума. Случайность с постоянным зерном: файл всегда один и тот же.
"""

import math
import random
import struct
import wave
from pathlib import Path

RATE = 22050
SECONDS = 0.85


def samples():
    noise = random.Random(2026)
    count = int(RATE * SECONDS)
    phase, smooth, result = 0.0, 0.0, []
    for i in range(count):
        t = i / count
        pitch = 118 - 58 * t + 16 * math.sin(t * 31) + noise.uniform(-14, 14)  # герц
        phase = (phase + pitch / RATE) % 1.0
        buzz = (1 - 2 * phase) * (1 if phase < 0.42 else 0.25)  # неровная «пила»: хрипит, а не гудит
        flutter = 0.72 + 0.28 * math.sin(t * 95 + 3 * math.sin(t * 13))
        envelope = min(1, t / 0.02) * min(1, (1 - t) / 0.28) ** 0.7  # резко вступает, затухает
        raw = (buzz * flutter + noise.uniform(-0.22, 0.22)) * envelope
        smooth += 0.42 * (raw - smooth)  # срезаем резкие верхи
        result.append(smooth)
    peak = max(abs(s) for s in result)
    return [s / peak * 0.5 for s in result]


def main():
    target = Path(__file__).parent / "fart.wav"
    with wave.open(str(target), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in samples()))


if __name__ == "__main__":
    main()
