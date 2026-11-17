"""Export a static Bold instance of the installed Noto Sans SC variable font for subtitle burn-in.

libass cannot pick a weight from a variable font (it renders the default Thin master), so subtitles
need a static file. Noto Sans SC is SIL OFL 1.1: free for commercial use, and modified copies must not
keep the reserved font name, hence the new family name. The file is used locally only, not shipped.

Usage: python make_sub_font.py
"""
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

SRC = Path(r"C:\Windows\Fonts\NotoSansSC-VF.ttf")
OUT = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "KidsSubSans-Bold.ttf"
FAMILY = "Kids Sub Sans"

OUT.parent.mkdir(parents=True, exist_ok=True)
font = instancer.instantiateVariableFont(TTFont(SRC), {"wght": 700})
for rec in font["name"].names:
    if rec.nameID in (1, 16):
        rec.string = FAMILY
    elif rec.nameID in (2, 17):
        rec.string = "Bold"
    elif rec.nameID == 4:
        rec.string = f"{FAMILY} Bold"
    elif rec.nameID == 6:
        rec.string = "KidsSubSans-Bold"
font["OS/2"].usWeightClass = 700
font["OS/2"].fsSelection = (font["OS/2"].fsSelection & ~0x40) | 0x20  # BOLD on, REGULAR off
font["head"].macStyle |= 0x01
font.save(OUT)
print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
