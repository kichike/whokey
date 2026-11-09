"""Урезанный шрифт MesloLGS Nerd Font для окон WhoKey (gui/fonts/*.ttf).

В полном Nerd Font больше 10 000 значков из разных наборов (у каждого своя лицензия),
а WhoKey рисует всего несколько значков Font Awesome на кнопках (theme.GLYPHS) и ключ
в расширении. Оставляем все обычные буквы и знаки шрифта (всё вне области частного
использования Unicode) и только эти значки: файл в десятки раз меньше, а в лицензии
(gui/fonts/LICENSE.txt) — только Meslo и Font Awesome.

Запуск: python3 gui/assets/make_app_font.py (нужен fontTools; в сборку не входит).
Повторный запуск ничего не портит. Потом — make_extension_font.py: он берёт буквы отсюда.
"""

from pathlib import Path

from fontTools import subset

ROOT = Path(__file__).resolve().parent.parent.parent
# значки Font Awesome 4 (в Nerd Font — на тех же местах): замок, лупа, шестерёнка, пазл,
# волшебная палочка, плюс, загрузка, щит, часы (theme.GLYPHS) и ключ (расширение)
ICONS = "U+F023,U+F002,U+F013,U+F12E,U+F0D0,U+F067,U+F093,U+F132,U+F017,U+F084"
UNICODES = "U+0000-DFFF,U+F900-FFFF,U+10000-EFFFF," + ICONS
for weight in ("Regular", "Bold"):
    font = ROOT / "gui" / "fonts" / f"MesloLGSNerdFont-{weight}.ttf"
    subset.main([str(font), f"--unicodes={UNICODES}", "--layout-features=*", "--name-IDs=*",
                 "--name-languages=*", "--notdef-outline", "--glyph-names", f"--output-file={font}"])
    print(font.name, font.stat().st_size // 1024, "КБ")
