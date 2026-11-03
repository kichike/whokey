"""Логотип без плитки — только неоновый пиксельный ключ на прозрачном фоне (key.png).

Его рисуют в окнах WhoKey и в расширении. Делается из icon.png: тёмный фон плитки
становится прозрачным (чем темнее точка, тем прозрачнее), цвета ключа сохраняются.
Запуск: python3 gui/assets/make_key.py (нужен Pillow; в сборку скрипт не входит).
"""

from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
CROP = (270, 170, 750, 910)  # ключ на icon.png (1024×1024) с запасом: свечение вокруг затухает целиком
FLOOR = 95  # фон плитки (тёмный индиго) не ярче этого — он становится полностью прозрачным

key = Image.open(HERE / "icon.png").convert("RGB").crop(CROP)
out = Image.new("RGBA", key.size)
pixels = []
for r, g, b in key.getdata():
    brightest = max(r, g, b)
    alpha = max(0, min(255, (brightest - FLOOR) * 255 // (255 - FLOOR - 40)))
    k = 255 / max(brightest, 1)  # цвет — как у самой яркой точки неона, без тёмной примеси фона
    pixels.append((min(255, int(r * k)), min(255, int(g * k)), min(255, int(b * k)), alpha) if alpha else (0, 0, 0, 0))
out.putdata(pixels)
out = out.crop(out.getbbox())  # без пустых полей
out.save(HERE / "key.png", optimize=True)
print("key.png", out.size)
