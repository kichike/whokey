"""Урезанный шрифт MesloLGS Nerd Font для расширения (extension/fonts/*.woff).

Целиком шрифт весит ~2.8 МБ — для окошка расширения это слишком. Оставляем только
латиницу, кириллицу, знаки препинания, стрелки и клавиши (⌘ ⇧ ⏎) и несколько значков
Nerd Font — тогда расширение выглядит так же, как окна WhoKey, и на Windows (без
встроенного шрифта там был бы Consolas).
Запуск: python3 gui/assets/make_extension_font.py (нужен fontTools; в сборку не входит).
"""

from pathlib import Path

from fontTools import subset

ROOT = Path(__file__).resolve().parent.parent.parent
UNICODES = ("U+0020-007E,U+00A0-00FF,U+0400-045F,U+2010-2027,U+2030-203A,U+2190-21FF,"
            "U+2300-23FF,U+25CF,U+2713,U+2726,"
            # значки Nerd Font: замок, лупа, шестерёнка, пазл, волшебная палочка, плюс, щит, часы, ключ
            "U+F023,U+F002,U+F013,U+F12E,U+F0D0,U+F067,U+F132,U+F017,U+F084")
for weight in ("Regular", "Bold"):
    out = ROOT / "extension" / "fonts" / f"meslo-{weight.lower()}.woff"
    out.parent.mkdir(exist_ok=True)
    subset.main([str(ROOT / "gui" / "fonts" / f"MesloLGSNerdFont-{weight}.ttf"), f"--unicodes={UNICODES}",
                 "--flavor=woff", "--layout-features=*", f"--output-file={out}"])
    print(out.name, out.stat().st_size // 1024, "КБ")
