"""Season cover (one picture for the whole season) in 16:9 (1920x1080) and 4:3 (1440x1080), in the same look as the
episode covers of tools/make_covers.py: Fenlo on the left, the season title and one small tile per episode on the right.

Usage: python tools/make_season_cover.py [dest_dir]
Writes seasons/s01/cover/season1_cover[_4x3].png and, in dest_dir (default <project>/export):
  S01_season_cover.jpg, covers/S01_season_cover.png, covers_4x3/S01_season_cover.png + .jpg
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_covers import ASPECT_LAYOUTS, DEFAULT_DEST, EPISODE_COVERS, ROOT, build_html, file_url  # noqa: E402

SEASON = {
    "title_zh": "芬洛的魔法画笔",
    "title_en": "英语启蒙 · Season 1",
    "tag": "第一季 · 全 12 集",
    "hero_episode": "ep01_colors",          # Fenlo with the paintbrush in the rainbow garden
    "theme": {"primary": "#E8413C", "pill": "#3F8FE8", "wash1": "rgba(255,244,214,0.92)", "wash2": "rgba(219,242,255,0.97)"},
    # one tile per episode: (picture in assets/skin, label, colour, tile background)
    "tiles": [
        ("apple", "颜色", "#E8413C", "#FFF2F1"), ("balloon_blue", "数字", "#2C7BE5", "#EFF6FF"),
        ("banana", "水果", "#D99300", "#FFFBEB"), ("cat", "动物", "#68707C", "#F4F5F7"),
        ("nose", "五官", "#EA7B1E", "#FFF5EB"), ("basket", "野餐", "#329E40", "#EFFBF0"),
        ("rabbit_hop", "动作", "#D96684", "#FFF1F5"), ("mom", "家人", "#9356C4", "#F7F1FF"),
        ("happy", "心情", "#D99300", "#FFFBEB"), ("milk", "早餐", "#4E7EC9", "#EFF5FF"),
        ("car", "大小", "#2C7BE5", "#EFF6FF"), ("bear_clap", "派对", "#E8413C", "#FFF2F1"),
    ],
}
TILE = {"16x9": {"h": 146, "img": 88, "font": 24, "gap": 14}, "4x3": {"h": 158, "img": 70, "font": 21, "gap": 11}}


def season_html(aspect):
    ep = ROOT / "episodes" / SEASON["hero_episode"]
    cfg = {**EPISODE_COVERS[SEASON["hero_episode"]], "theme": SEASON["theme"], "cards": [], "rainbow": False}
    cfg["hero_4x3"] = {**cfg["hero_4x3"], "left": cfg["hero_4x3"]["left"] - 32}      # keeps the paintbrush clear of the tiles
    page = build_html(ep, {"title_zh": SEASON["title_zh"], "title_en": SEASON["title_en"]}, cfg, 0, aspect)
    a = '<div class="ep-tag">第 0 集 · EP00</div>'
    assert page.count(a) == 1
    page = page.replace(a, f'<div class="ep-tag">{SEASON["tag"]}</div>')
    t = TILE[aspect]
    tiles = "".join(
        f'<div class="tile" style="border-bottom:5px solid {c}"><div class="num" style="background:{c}">{i + 1}</div>'
        f'<div class="pic" style="background:{bg}"><img src="{file_url(ROOT / "assets" / "skin" / (pic + ".png"))}" width="{t["img"]}" height="{t["img"]}"></div>'
        f'<div class="lab" style="color:{c}">{lab}</div></div>'
        for i, (pic, lab, c, bg) in enumerate(SEASON["tiles"]))
    css = f"""<style>
.cards-grid {{ grid-template-columns: repeat(4, 1fr); gap: {t["gap"]}px; }}
.tile {{ position: relative; height: {t["h"]}px; background: rgba(255,255,255,0.95); border-radius: 20px; border: 3px solid #fff;
  box-shadow: 0 6px 0 rgba(0,0,0,0.07), 0 10px 20px rgba(0,0,0,0.09); display: flex; flex-direction: column; align-items: center;
  justify-content: space-between; padding: 7px 7px 6px; overflow: hidden; }}
.tile .pic {{ width: 100%; flex: 1; border-radius: 13px; display: flex; align-items: center; justify-content: center; }}
.tile .pic img {{ display: block; filter: drop-shadow(0 4px 5px rgba(0,0,0,0.22)); }}
.tile .lab {{ font-family: "KidsSubSans", "Noto Sans SC", sans-serif; font-size: {t["font"]}px; font-weight: 700; line-height: 1; margin-top: 6px; letter-spacing: 2px; }}
.tile .num {{ position: absolute; left: 10px; top: 10px; width: 24px; height: 24px; border-radius: 50%; color: #fff; font-size: 15px; font-weight: 900;
  display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 0 rgba(0,0,0,0.12); }}
.title-en-pill {{ font-family: "KidsSubSans", "NunitoLocal", sans-serif; font-weight: 700; letter-spacing: 1px; }}
</style>"""
    a = '<div class="cards-grid" id="cards"></div>'
    assert page.count(a) == 1
    return page.replace(a, f'<div class="cards-grid" id="cards">{tiles}</div>').replace("</head>", css + "</head>")


def main():
    dest = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DEST
    keep = ROOT / "seasons" / "s01" / "cover"
    keep.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="fenlo_season_cover_"))
    try:
        jobs = []
        for aspect in ("16x9", "4x3"):
            lay = ASPECT_LAYOUTS[aspect]
            h = tmp / f"season_{aspect}.html"
            h.write_text(season_html(aspect), encoding="utf-8")
            png = keep / ("season1_cover.png" if aspect == "16x9" else "season1_cover_4x3.png")
            jobs.append({"tag": f"season({aspect})", "html": str(h), "png": str(png), "width": lay["stage_w"], "height": lay["stage_h"]})
        m = tmp / "manifest.json"
        m.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
        subprocess.run(["node", "render_covers.mjs", str(m)], cwd=ROOT / "tools", check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for sub, src, jpg in (("covers", keep / "season1_cover.png", dest / "S01_season_cover.jpg"),
                          ("covers_4x3", keep / "season1_cover_4x3.png", dest / "covers_4x3" / "S01_season_cover.jpg")):
        (dest / sub).mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / sub / "S01_season_cover.png")
        with Image.open(src) as im:
            im.convert("RGB").save(jpg, "JPEG", quality=93, optimize=True)
            print(f"{jpg}  {im.size}")


if __name__ == "__main__":
    main()
