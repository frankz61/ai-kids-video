"""Generate 16:9 (1920x1080) and 4:3 (1440x1080) episode covers for Fenlo Season 1.

Usage:
    python tools/make_covers.py [dest_dir] [--aspect 16x9|4x3|all]
Default dest_dir: <project>/export
"""
import argparse
import html
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = ROOT / "export"

# Per-aspect layout constants (rendered at 1.5x DPR -> 1920x1080 and 1440x1080).
ASPECT_LAYOUTS = {
    "16x9": {
        "stage_w": 1280,
        "stage_h": 720,
        "brand_left": 26,
        "brand_top": 20,
        "logo_size": 26,
        "ep_size": 19,
        "panel_left": 590,
        "panel_w": 652,
        "panel_top": 32,
        "panel_top_party": 46,
        "zh_sizes": (90, 82, 74),
        "zh_stroke": 16,
        "en_sizes": (34, 31),
        "cards_w": 644,
        "cards_gap": 18,
        "cards_top_gap": 24,
        "cards_top_gap_party": 20,
        "card_h": 204,
        "art_h": 132,
        "word_size": 36,
        "word_compact": 31,
        "item_scales": (1.0, 1.0, 1.0),
        "rainbow_w": 900,
        "rainbow_h": 460,
        "rainbow_right": -70,
        "rainbow_top": 26,
        "bunting_x0": 540,
        "bunting_step": 72,
        "bunting_count": 11,
        "bunting_path": "M500 2 Q900 22 1300 2",
        "sparkles": [(572, 54, 28), (618, 134, 22), (1216, 132, 30), (1224, 662, 26), (576, 666, 24)],
        "wash_stops": ("38%", "54%"),
        "covers_subdir": "covers",
        "copy_jpg_to_root": True,
        "ep_suffix": "_cover.png",
        "sheet_name": "season1_covers_overview.jpg",
        "sheet_tile": "640:360",
    },
    "4x3": {
        "stage_w": 960,
        "stage_h": 720,
        "brand_left": 20,
        "brand_top": 18,
        "logo_size": 22,
        "ep_size": 16,
        "panel_left": 446,
        "panel_w": 494,
        "panel_top": 24,
        "panel_top_party": 42,
        "zh_sizes": (80, 72, 64),
        "zh_stroke": 14,
        "en_sizes": (29, 26),
        "cards_w": 468,
        "cards_gap": 16,
        "cards_top_gap": 24,
        "cards_top_gap_party": 18,
        "card_h": 224,
        "art_h": 146,
        "word_size": 32,
        "word_compact": 27,
        "item_scales": (0.94, 0.84, 0.76),
        "rainbow_w": 720,
        "rainbow_h": 380,
        "rainbow_right": -85,
        "rainbow_top": 26,
        "bunting_x0": 438,
        "bunting_step": 64,
        "bunting_count": 9,
        "bunting_path": "M410 2 Q695 20 980 2",
        "sparkles": [(442, 46, 24), (446, 668, 22), (918, 128, 26), (922, 668, 24)],
        "wash_stops": ("34%", "50%"),
        "covers_subdir": "covers_4x3",
        "copy_jpg_to_root": False,
        "ep_suffix": "_cover_4x3.png",
        "sheet_name": "season1_covers_4x3_overview.jpg",
        "sheet_tile": "480:360",
    },
}

# Per-episode visual configuration: frame selection, hero positioning (16:9 and 4:3), theme palette, and 4 cards.
# Card item entries are tuples of (item_id, size_px, rotation_deg, dx_px, dy_px).
EPISODE_COVERS = {
    "ep01_colors": {
        "frame": "shot_05.png",
        "hero": {"width": 1110, "left": -210, "top": 95, "fade_start": 45, "fade_end": 58},
        "hero_4x3": {"width": 920, "left": -165, "top": 202, "fade_start": 45, "fade_end": 56},
        "theme": {"primary": "#E8413C", "pill": "#3F8FE8", "wash1": "rgba(255,244,214,0.92)", "wash2": "rgba(219,242,255,0.97)"},
        "rainbow": True,
        "cards": [
            {"label": "red", "color": "#E8413C", "bg": "#FFF2F1", "items": [("apple", 124, 0, 0, 0)]},
            {"label": "yellow", "color": "#D99300", "bg": "#FFFBEB", "items": [("duck", 124, 0, 0, 0)]},
            {"label": "blue", "color": "#2C7BE5", "bg": "#EFF6FF", "items": [("bird", 124, 0, 0, 0)]},
            {"label": "green", "color": "#329E40", "bg": "#EFFBF0", "items": [("frog", 124, 0, 0, 0)]},
        ],
    },
    "ep02_numbers": {
        "frame": "shot_04.png",
        "hero": {"width": 1120, "left": -155, "top": 90, "fade_start": 42, "fade_end": 58},
        "hero_4x3": {"width": 900, "left": -135, "top": 214, "fade_start": 44, "fade_end": 55},
        "theme": {"primary": "#2C7BE5", "pill": "#F28A2E", "wash1": "rgba(227,245,255,0.92)", "wash2": "rgba(255,247,219,0.97)"},
        "cards": [
            {"label": "one", "color": "#E8413C", "bg": "#FFF2F1", "badge": "1", "items": [("balloon_red", 122, -4, 0, 2)]},
            {"label": "two", "color": "#2C7BE5", "bg": "#EFF6FF", "badge": "2", "items": [("balloon_blue", 96, -8, 6, 4), ("balloon_blue", 96, 8, -6, -4)]},
            {"label": "three", "color": "#D99300", "bg": "#FFFBEB", "badge": "3", "items": [("balloon_yellow", 80, -10, 10, 6), ("balloon_yellow", 84, 0, 0, -6), ("balloon_yellow", 80, 10, -10, 6)]},
            {"label": "balloon", "color": "#329E40", "bg": "#EFFBF0", "items": [("balloon_green", 126, 6, 0, 0)]},
        ],
    },
    "ep03_fruit": {
        "frame": "shot_04.png",
        "hero": {"width": 1120, "left": -145, "top": 90, "fade_start": 42, "fade_end": 58},
        "hero_4x3": {"width": 900, "left": -125, "top": 214, "fade_start": 44, "fade_end": 55},
        "theme": {"primary": "#E8413C", "pill": "#49A842", "wash1": "rgba(238,250,217,0.92)", "wash2": "rgba(255,242,222,0.97)"},
        "cards": [
            {"label": "apple", "color": "#E8413C", "bg": "#FFF2F1", "items": [("apple", 124, 0, 0, 0)]},
            {"label": "banana", "color": "#D99300", "bg": "#FFFBEB", "items": [("banana", 124, 0, 0, 0)]},
            {"label": "pear", "color": "#6E9B14", "bg": "#F4FAE8", "items": [("pear", 124, 0, 0, 0)]},
            {"label": "strawberry", "color": "#E8413C", "bg": "#FFF2F1", "items": [("strawberry", 124, 0, 0, 0)]},
        ],
    },
    "ep04_animals": {
        "frame": "shot_03.png",
        "hero": {"width": 1160, "left": -195, "top": 68, "fade_start": 44, "fade_end": 60},
        "hero_4x3": {"width": 960, "left": -190, "top": 180, "fade_start": 44, "fade_end": 55},
        "theme": {"primary": "#329E40", "pill": "#F28A2E", "wash1": "rgba(228,248,230,0.92)", "wash2": "rgba(255,247,219,0.97)"},
        "cards": [
            {"label": "cat", "color": "#68707C", "bg": "#F4F5F7", "items": [("cat", 124, 0, 0, 0)]},
            {"label": "dog", "color": "#A8693A", "bg": "#FDF5EE", "items": [("dog", 124, 0, 0, 0)]},
            {"label": "rabbit", "color": "#D96684", "bg": "#FFF1F5", "items": [("rabbit", 124, 0, 0, 0)]},
            {"label": "fish", "color": "#2C7BE5", "bg": "#EFF6FF", "items": [("fish", 124, 0, 0, 0)]},
        ],
    },
    "ep05_face": {
        "frame": "shot_03.png",
        "hero": {"width": 1100, "left": -185, "top": 88, "fade_start": 42, "fade_end": 57},
        "hero_4x3": {"width": 960, "left": -200, "top": 180, "fade_start": 44, "fade_end": 55},
        "theme": {"primary": "#EA7B1E", "pill": "#2C7BE5", "wash1": "rgba(255,242,224,0.92)", "wash2": "rgba(255,230,210,0.97)"},
        "cards": [
            {"label": "head", "color": "#E8413C", "bg": "#FFF2F1", "items": [("head", 122, 0, 0, 0)]},
            {"label": "eyes", "color": "#2C7BE5", "bg": "#EFF6FF", "items": [("eyes", 122, 0, 0, 0)]},
            {"label": "nose", "color": "#D99300", "bg": "#FFFBEB", "items": [("nose", 122, 0, 0, 0)]},
            {"label": "mouth", "color": "#329E40", "bg": "#EFFBF0", "items": [("mouth", 122, 0, 0, 0)]},
        ],
    },
    "ep06_picnic": {
        "frame": "shot_01.png",
        "hero": {"width": 1140, "left": -185, "top": 80, "fade_start": 43, "fade_end": 59},
        "hero_4x3": {"width": 960, "left": -185, "top": 180, "fade_start": 44, "fade_end": 55},
        "theme": {"primary": "#2EA85E", "pill": "#F28A2E", "wash1": "rgba(232,249,223,0.92)", "wash2": "rgba(255,246,204,0.97)"},
        "cards": [
            {"label": "three", "color": "#E8413C", "bg": "#FFF2F1", "items": [("apple", 76, -4, 6, 4), ("apple", 78, 0, 0, -4), ("apple", 76, 4, -6, 4)]},
            {"label": "rabbit", "color": "#D96684", "bg": "#FFF1F5", "items": [("rabbit", 124, 0, 0, 0)]},
            {"label": "green", "color": "#6E9B14", "bg": "#F4FAE8", "items": [("pear", 124, 0, 0, 0)]},
            {"label": "two", "color": "#2C7BE5", "bg": "#EFF6FF", "items": [("balloon_blue", 96, -8, 6, 2), ("balloon_yellow", 96, 8, -6, -2)]},
        ],
    },
    "ep07_actions": {
        "frame": "shot_03.png",
        "hero": {"width": 1160, "left": -175, "top": 68, "fade_start": 44, "fade_end": 60},
        "hero_4x3": {"width": 960, "left": -180, "top": 180, "fade_start": 44, "fade_end": 55},
        "theme": {"primary": "#E8413C", "pill": "#2C7BE5", "wash1": "rgba(224,244,255,0.92)", "wash2": "rgba(255,238,219,0.97)"},
        "cards": [
            {"label": "jump", "color": "#D96684", "bg": "#FFF1F5", "items": [("rabbit", 122, 0, 0, -4)]},
            {"label": "run", "color": "#A8693A", "bg": "#FDF5EE", "items": [("dog", 122, 0, 0, 0)]},
            {"label": "clap", "color": "#E8413C", "bg": "#FFF2F1", "items": [("hands", 122, 0, 0, 0)]},
            {"label": "swim", "color": "#2C7BE5", "bg": "#EFF6FF", "items": [("fish", 122, 0, 0, 0)]},
        ],
    },
    "ep08_family": {
        "frame": "shot_05.png",
        "hero": {"width": 1140, "left": -185, "top": 80, "fade_start": 43, "fade_end": 59},
        "hero_4x3": {"width": 960, "left": -190, "top": 180, "fade_start": 44, "fade_end": 55},
        "theme": {"primary": "#D95276", "pill": "#EA7B1E", "wash1": "rgba(255,240,229,0.92)", "wash2": "rgba(255,228,238,0.97)"},
        "cards": [
            {"label": "mom", "color": "#D96684", "bg": "#FFF1F5", "items": [("mom", 120, 0, 0, 0)]},
            {"label": "dad", "color": "#2C7BE5", "bg": "#EFF6FF", "items": [("dad", 120, 0, 0, 0)]},
            {"label": "grandma", "color": "#9356C4", "bg": "#F7F1FF", "items": [("grandma", 120, 0, 0, 0)]},
            {"label": "grandpa", "color": "#329E40", "bg": "#EFFBF0", "items": [("grandpa", 120, 0, 0, 0)]},
        ],
    },
    "ep09_feelings": {
        "frame": "shot_01.png",
        "hero": {"width": 1080, "left": -175, "top": 98, "fade_start": 42, "fade_end": 57},
        "hero_4x3": {"width": 920, "left": -180, "top": 202, "fade_start": 44, "fade_end": 55},
        "theme": {"primary": "#5E6EDB", "pill": "#EA7B1E", "wash1": "rgba(238,242,255,0.92)", "wash2": "rgba(255,243,217,0.97)"},
        "cards": [
            {"label": "happy", "color": "#D99300", "bg": "#FFFBEB", "items": [("happy", 122, 0, 0, 0)]},
            {"label": "sad", "color": "#2C7BE5", "bg": "#EFF6FF", "items": [("sad", 122, 0, 0, 0)]},
            {"label": "hungry", "color": "#EA7B1E", "bg": "#FFF5EB", "items": [("hungry", 122, 0, 0, 0)]},
            {"label": "sleepy", "color": "#5E7AD0", "bg": "#F0F4FF", "items": [("sleepy", 122, 0, 0, 0)]},
        ],
    },
    "ep10_breakfast": {
        "frame": "shot_05.png",
        "hero": {"width": 1100, "left": -175, "top": 92, "fade_start": 43, "fade_end": 58},
        "hero_4x3": {"width": 950, "left": -185, "top": 186, "fade_start": 44, "fade_end": 55},
        "theme": {"primary": "#EA7B1E", "pill": "#4E89D8", "wash1": "rgba(255,244,220,0.92)", "wash2": "rgba(255,229,194,0.97)"},
        "cards": [
            {"label": "milk", "color": "#4E7EC9", "bg": "#EFF5FF", "items": [("milk", 122, 0, 0, 0)]},
            {"label": "bread", "color": "#A8693A", "bg": "#FDF5EE", "items": [("bread", 122, 0, 0, 0)]},
            {"label": "eggs", "color": "#D99300", "bg": "#FFFBEB", "items": [("eggs", 122, 0, 0, 0)]},
            {"label": "juice", "color": "#E67A00", "bg": "#FFF4E5", "items": [("juice", 122, 0, 0, 0)]},
        ],
    },
    "ep11_big_small": {
        "frame": "shot_03.png",
        "hero": {"width": 1070, "left": -160, "top": 115, "fade_start": 44, "fade_end": 58},
        "hero_4x3": {"width": 880, "left": -125, "top": 225, "fade_start": 45, "fade_end": 56},
        "theme": {"primary": "#E8413C", "pill": "#2C7BE5", "wash1": "rgba(255,235,232,0.92)", "wash2": "rgba(227,241,255,0.97)"},
        "cards": [
            {"label": "big", "color": "#E8413C", "bg": "#FFF2F1", "items": [("ball", 126, 0, 0, 0)]},
            {"label": "small", "color": "#2C7BE5", "bg": "#EFF6FF", "items": [("ball", 46, 0, 0, 6)]},
            {"label": "ball", "color": "#E8413C", "bg": "#FFF2F1", "items": [("ball", 92, 0, 0, 2)]},
            {"label": "car", "color": "#2C7BE5", "bg": "#EFF6FF", "items": [("car", 126, 0, 0, 0)]},
        ],
    },
    "ep12_happy": {
        "frame": "shot_01.png",
        "hero": {"width": 1070, "left": -175, "top": 115, "fade_start": 43, "fade_end": 57},
        "hero_4x3": {"width": 920, "left": -180, "top": 202, "fade_start": 44, "fade_end": 55},
        "theme": {"primary": "#E8413C", "pill": "#7C3AED", "wash1": "rgba(255,243,214,0.92)", "wash2": "rgba(255,230,242,0.97)"},
        "party": True,
        "cards": [
            {"label": "happy", "color": "#D99300", "bg": "#FFFBEB", "items": [("happy", 122, 0, 0, 0)]},
            {"label": "big ball", "color": "#E8413C", "bg": "#FFF2F1", "items": [("ball", 126, 0, 0, 0)]},
            {"label": "three", "color": "#2C7BE5", "bg": "#EFF6FF", "items": [("balloon_red", 78, -10, 10, 6), ("balloon_yellow", 82, 0, 0, -6), ("balloon_blue", 78, 10, -10, 6)]},
            {"label": "clap", "color": "#7C3AED", "bg": "#F5F0FF", "items": [("hands", 122, 0, 0, 0)]},
        ],
    },
}


def file_url(path: Path) -> str:
    return "file:///" + quote(path.resolve().as_posix(), safe="/:")


def build_bunting_svg(lay: dict) -> str:
    flags = []
    colors = ["#e8413c", "#ffd23f", "#3f8fe8", "#4fbf5a"]
    n = lay["bunting_count"]
    mid = (n - 1) / 2.0
    for i in range(n):
        x = lay["bunting_x0"] + i * lay["bunting_step"]
        y = 6 + 13 * (1 - abs(i - mid) / (mid + 0.5)) * 0.55
        c = colors[i % 4]
        flags.append(f'<path d="M{x - 15} {y - 2} L{x + 15} {y - 2} L{x} {y + 24}Z" fill="{c}" stroke="#fff" stroke-width="2"/>')
    return (
        f'<svg class="bunting" width="{lay["stage_w"]}" height="60" viewBox="0 0 {lay["stage_w"]} 60">'
        f'<path d="{lay["bunting_path"]}" stroke="#c9a06a" stroke-width="3.5" fill="none"/>'
        + "".join(flags)
        + "</svg>"
    )


def build_sparkles_svg(pts: list[tuple[int, int, int]]) -> str:
    out = []
    for x, y, s in pts:
        out.append(
            f'<svg class="spark" style="left:{x}px;top:{y}px;width:{s}px;height:{s}px" viewBox="0 0 44 44">'
            '<path d="M22 2 L27 17 L42 22 L27 27 L22 42 L17 27 L2 22 L17 17Z" fill="#ffd23f" stroke="#fff" stroke-width="2.5"/>'
            "</svg>"
        )
    return "".join(out)


def build_html(ep_dir: Path, spec: dict, cfg: dict, num: int, aspect: str) -> str:
    lay = ASPECT_LAYOUTS[aspect]
    frame_url = file_url(ep_dir / "h3" / "frames" / cfg["frame"])
    # items.js first, then per-season files (e.g. season2-items.js adds to window.ITEMS)
    items_js_tags = "".join(f'<script src="{file_url(p)}"></script>' for p in sorted((ROOT / "engine" / "h5").glob("*items.js")))
    zh_font_url = file_url(ROOT / "assets" / "fonts" / "KidsSubSans-Bold.ttf")
    nunito_path = Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts" / "Nunito-VariableFont_wght.ttf"
    nunito_face = (
        f'@font-face {{ font-family: "NunitoLocal"; src: url("{file_url(nunito_path)}"); font-weight: 100 900; }}'
        if nunito_path.exists()
        else ""
    )

    h = cfg["hero_4x3"] if aspect == "4x3" else cfg["hero"]
    hero_h = round(h["width"] * 9 / 16)
    top_mask = "linear-gradient(180deg, transparent 0%, #000 3.5%, #000 100%)" if h["top"] > 10 else "none"
    wrap_mask = (
        f"linear-gradient(90deg, #000 0%, #000 {h['fade_start']}%, "
        f"rgba(0,0,0,0.4) {(h['fade_start'] + h['fade_end']) / 2:.1f}%, transparent {h['fade_end']}%)"
    )

    zh_len = len(spec["title_zh"].replace(" ", ""))
    zh_big, zh_med, zh_small = lay["zh_sizes"]
    zh_size = zh_small if zh_len >= 6 else (zh_med if zh_len == 5 else zh_big)
    en_big, en_small = lay["en_sizes"]
    en_size = en_small if len(spec["title_en"]) >= 22 else en_big
    panel_top = lay["panel_top_party"] if cfg.get("party") else lay["panel_top"]
    cards_gap_top = lay["cards_top_gap_party"] if cfg.get("party") else lay["cards_top_gap"]

    rainbow_html = (
        f'<svg class="rainbow" width="{lay["rainbow_w"]}" height="{lay["rainbow_h"]}" viewBox="0 0 900 460" fill="none" stroke-linecap="round">'
        '<path d="M 40 460 A 410 410 0 0 1 860 460" stroke="#e8413c" stroke-width="30"/>'
        '<path d="M 72 460 A 378 378 0 0 1 828 460" stroke="#ffd23f" stroke-width="30"/>'
        '<path d="M 104 460 A 346 346 0 0 1 796 460" stroke="#4fbf5a" stroke-width="30"/>'
        '<path d="M 136 460 A 314 314 0 0 1 764 460" stroke="#3f8fe8" stroke-width="30"/>'
        "</svg>"
        if cfg.get("rainbow")
        else ""
    )
    party_html = build_bunting_svg(lay) if cfg.get("party") else ""
    cards_json = json.dumps(cfg["cards"], ensure_ascii=False)
    # 3D-style item images (assets/skin, made by tools/make_skin.py) replace the flat vector items when they exist
    man_path = ROOT / "assets" / "skin" / "manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {"items": {}}
    swap = spec["skin"].get("items", {}) if isinstance(spec.get("skin"), dict) else {}     # per-episode pictures (rabbit -> rabbit_jump)
    skin_json = json.dumps({i: file_url(ROOT / "assets" / "skin" / man["items"].get(swap.get(i, i), e)["src"]) for i, e in man["items"].items()})
    scales_json = json.dumps(lay["item_scales"])
    th = cfg["theme"]
    sw, sh = lay["stage_w"], lay["stage_h"]
    w_s0, w_s1 = lay["wash_stops"]

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
{nunito_face}
@font-face {{
  font-family: "KidsSubSans";
  src: url("{zh_font_url}");
  font-weight: 700;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: {sw}px; height: {sh}px; overflow: hidden; background: #fff; }}
#stage {{
  position: relative;
  width: {sw}px;
  height: {sh}px;
  overflow: hidden;
  font-family: "NunitoLocal", "Nunito", "KidsSubSans", "Noto Sans SC", sans-serif;
}}
.bg-blur {{
  position: absolute;
  inset: 0;
  width: {sw}px;
  height: {sh}px;
  object-fit: cover;
  transform: scaleX(-1) scale(1.22);
  filter: blur(20px) saturate(1.18) brightness(1.06);
}}
.bg-wash {{
  position: absolute;
  inset: 0;
  background: linear-gradient(104deg,
    rgba(255,255,255,0.00) 0%,
    rgba(255,255,255,0.12) {w_s0},
    {th["wash1"]} {w_s1},
    {th["wash2"]} 100%);
}}
.rainbow {{
  position: absolute;
  right: {lay["rainbow_right"]}px;
  top: {lay["rainbow_top"]}px;
  opacity: 0.20;
  pointer-events: none;
}}
.bunting {{
  position: absolute;
  left: 0;
  top: 0;
  z-index: 6;
  pointer-events: none;
}}
.hero-wrap {{
  position: absolute;
  inset: 0;
  z-index: 2;
  -webkit-mask-image: {wrap_mask};
  mask-image: {wrap_mask};
}}
.hero-img {{
  position: absolute;
  left: {h["left"]}px;
  top: {h["top"]}px;
  width: {h["width"]}px;
  height: {hero_h}px;
  object-fit: cover;
  -webkit-mask-image: {top_mask};
  mask-image: {top_mask};
}}
.spark {{
  position: absolute;
  z-index: 5;
  filter: drop-shadow(0 3px 6px rgba(0,0,0,0.12));
}}
.brand-pill {{
  position: absolute;
  left: {lay["brand_left"]}px;
  top: {lay["brand_top"]}px;
  z-index: 10;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 6px 16px 6px 18px;
  background: rgba(255,255,255,0.95);
  border-radius: 999px;
  border: 3px solid #ffffff;
  box-shadow: 0 6px 0 rgba(0,0,0,0.08), 0 10px 20px rgba(0,0,0,0.12);
}}
.fenlo-logo {{
  font-size: {lay["logo_size"]}px;
  font-weight: 900;
  letter-spacing: 2px;
  line-height: 1;
}}
.ep-tag {{
  background: {th["primary"]};
  color: #fff;
  font-family: "KidsSubSans", "NunitoLocal", sans-serif;
  font-size: {lay["ep_size"]}px;
  font-weight: 700;
  padding: 5px 13px;
  border-radius: 999px;
  line-height: 1.1;
  letter-spacing: 0.5px;
}}
.right-panel {{
  position: absolute;
  left: {lay["panel_left"]}px;
  top: {panel_top}px;
  width: {lay["panel_w"]}px;
  height: {sh - panel_top - 16}px;
  z-index: 8;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
}}
.title-zh {{
  font-family: "KidsSubSans", "Noto Sans SC", sans-serif;
  font-size: {zh_size}px;
  font-weight: 700;
  line-height: 1.12;
  color: {th["primary"]};
  -webkit-text-stroke: {lay["zh_stroke"]}px #ffffff;
  paint-order: stroke fill;
  filter: drop-shadow(0 7px 0 rgba(0,0,0,0.13)) drop-shadow(0 12px 24px rgba(0,0,0,0.10));
  white-space: nowrap;
  text-align: center;
  margin-top: 6px;
}}
.title-en-pill {{
  margin-top: 10px;
  padding: 7px 24px;
  background: {th["pill"]};
  color: #ffffff;
  font-size: {en_size}px;
  font-weight: 900;
  line-height: 1.2;
  border-radius: 999px;
  border: 4px solid #ffffff;
  box-shadow: 0 6px 0 rgba(0,0,0,0.10), 0 10px 20px rgba(0,0,0,0.08);
  white-space: nowrap;
}}
.cards-grid {{
  margin-top: {cards_gap_top}px;
  width: {lay["cards_w"]}px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: {lay["cards_gap"]}px;
}}
.card {{
  position: relative;
  height: {lay["card_h"]}px;
  background: rgba(255,255,255,0.94);
  border-radius: 26px;
  border: 4px solid #ffffff;
  box-shadow: 0 8px 0 rgba(0,0,0,0.07), 0 14px 28px rgba(0,0,0,0.09);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 12px 12px 12px;
  overflow: hidden;
}}
.card-art {{
  position: relative;
  width: 100%;
  height: {lay["art_h"]}px;
  border-radius: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}}
.card-art svg {{
  display: block;
  overflow: visible;
  filter: drop-shadow(0 4px 6px rgba(0,0,0,0.08));
}}
.card-art img {{
  display: block;
  filter: drop-shadow(0 6px 7px rgba(0,0,0,0.22));
}}
.card-badge {{
  position: absolute;
  left: 9px;
  top: 8px;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  color: #fff;
  font-size: 18px;
  font-weight: 900;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 3px 0 rgba(0,0,0,0.12);
}}
.card-word {{
  font-size: {lay["word_size"]}px;
  font-weight: 900;
  line-height: 1;
  letter-spacing: 0.4px;
  margin-top: 4px;
}}
.card-word.compact {{
  font-size: {lay["word_compact"]}px;
}}
</style>
</head>
<body>
<div id="stage">
  <img class="bg-blur" src="{frame_url}" alt="">
  <div class="bg-wash"></div>
  {rainbow_html}
  {party_html}
  <div class="hero-wrap">
    <img class="hero-img" src="{frame_url}" alt="">
  </div>
  {build_sparkles_svg(lay["sparkles"])}
  <div class="brand-pill">
    <div class="fenlo-logo">
      <span style="color:#e8413c">F</span><span style="color:#f0b400">E</span><span style="color:#3f8fe8">N</span><span style="color:#3fae4b">L</span><span style="color:#e8413c">O</span>
    </div>
    <div class="ep-tag">第 {num} 集 · EP{num:02d}</div>
  </div>
  <div class="right-panel">
    <div class="title-zh">{html.escape(spec["title_zh"])}</div>
    <div class="title-en-pill">{html.escape(spec["title_en"])}</div>
    <div class="cards-grid" id="cards"></div>
  </div>
</div>
{items_js_tags}
<script>
const cards = {cards_json};
const scales = {scales_json};
const skin = {skin_json};
const grid = document.getElementById("cards");
for (const c of cards) {{
  const card = document.createElement("div");
  card.className = "card";
  card.style.borderBottom = "6px solid " + c.color;

  const art = document.createElement("div");
  art.className = "card-art";
  art.style.background = c.bg;

  if (c.badge) {{
    const b = document.createElement("div");
    b.className = "card-badge";
    b.style.background = c.color;
    b.textContent = c.badge;
    art.appendChild(b);
  }}

  const scale = scales[Math.min(c.items.length, 3) - 1];
  for (const [id, size, rot, dx, dy] of c.items) {{
    const item = window.ITEMS[id];
    if (!item) throw new Error("Unknown item: " + id);
    const sz = Math.round(size * scale);
    if (skin[id]) {{
      const img = document.createElement("img");
      img.src = skin[id];
      img.width = sz;
      img.height = sz;
      img.style.transform = `translate(${{Math.round(dx * scale)}}px, ${{Math.round(dy * scale)}}px) rotate(${{rot}}deg)`;
      art.appendChild(img);
      continue;
    }}
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 200 200");
    svg.setAttribute("width", String(sz));
    svg.setAttribute("height", String(sz));
    svg.style.transform = `translate(${{Math.round(dx * scale)}}px, ${{Math.round(dy * scale)}}px) rotate(${{rot}}deg)`;
    svg.innerHTML = item.svg;
    art.appendChild(svg);
  }}

  const word = document.createElement("div");
  word.className = "card-word" + (c.label.length >= 8 ? " compact" : "");
  word.style.color = c.color;
  word.textContent = c.label;

  card.appendChild(art);
  card.appendChild(word);
  grid.appendChild(card);
}}
</script>
</body>
</html>
"""


def make_contact_sheet(pngs: list[Path], out_jpg: Path, tile_scale: str, cols: int = 3) -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        for i, p in enumerate(pngs):
            subprocess.run(
                ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(p), "-vf", f"scale={tile_scale}", str(tmp / f"c_{i:02d}.png")],
                check=True,
            )
        rows = -(-len(pngs) // cols)
        subprocess.run(
            ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-framerate", "1", "-i", str(tmp / "c_%02d.png"),
             "-vf", f"tile={cols}x{rows}", "-frames:v", "1", "-q:v", "2", str(out_jpg)],
            check=True,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_aspect(dest: Path, aspect: str) -> None:
    lay = ASPECT_LAYOUTS[aspect]
    covers_dir = dest / lay["covers_subdir"]
    covers_dir.mkdir(parents=True, exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"fenlo_covers_{aspect}_"))
    try:
        jobs = []
        outputs = []
        for ep in sorted(p for p in (ROOT / "episodes").glob("ep[0-9][0-9]_*") if p.is_dir()):
            cfg = EPISODE_COVERS.get(ep.name)
            if not cfg:
                continue
            spec = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
            name, num = spec["output_name"], int(ep.name[2:4])
            tag = f"S01E{num:02d}_{name.split('_', 1)[1]}"
            html_path = tmp_dir / f"{tag}.html"
            html_path.write_text(build_html(ep, spec, cfg, num, aspect), encoding="utf-8")

            ep_cover_png = ep / "output" / f"{name}{lay['ep_suffix']}"
            dest_png = covers_dir / f"{tag}.png"
            dest_jpg = (dest / f"{tag}.jpg") if lay["copy_jpg_to_root"] else (covers_dir / f"{tag}.jpg")

            jobs.append({"tag": f"{tag}({aspect})", "html": str(html_path), "png": str(ep_cover_png),
                         "width": lay["stage_w"], "height": lay["stage_h"]})
            outputs.append((tag, ep_cover_png, dest_png, dest_jpg))

        manifest_path = tmp_dir / "manifest.json"
        manifest_path.write_text(json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2), encoding="utf-8")

        subprocess.run(["node", "render_covers.mjs", str(manifest_path)], cwd=ROOT / "tools", check=True)

        pngs_for_sheet = []
        for tag, ep_png, dest_png, dest_jpg in outputs:
            shutil.copy2(ep_png, dest_png)
            with Image.open(ep_png) as im:
                im.convert("RGB").save(dest_jpg, "JPEG", quality=93, optimize=True)
            pngs_for_sheet.append(dest_png)
            print(f"[{aspect}] {tag}: png={dest_png.stat().st_size // 1024}KB jpg={dest_jpg.stat().st_size // 1024}KB")

        sheet_path = covers_dir / lay["sheet_name"]
        make_contact_sheet(pngs_for_sheet, sheet_path, lay["sheet_tile"], cols=3)
        print(f"[{aspect}] overview sheet -> {sheet_path}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dest", nargs="?", default=str(DEFAULT_DEST))
    parser.add_argument("--aspect", choices=["16x9", "4x3", "all"], default="all")
    args = parser.parse_args()
    dest = Path(args.dest).resolve()
    aspects = ["16x9", "4x3"] if args.aspect == "all" else [args.aspect]
    for aspect in aspects:
        render_aspect(dest, aspect)


if __name__ == "__main__":
    main()
