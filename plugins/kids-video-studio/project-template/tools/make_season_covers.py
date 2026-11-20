"""Covers and the upload folder for any season, driven by seasons/<sNN>/covers.json.

  python tools/make_season_covers.py seasons/s02 covers [--aspect 16x9|4x3|all]
        episode covers -> episodes/<ep>/output/<output_name>_cover.png and _cover_4x3.png
        overview sheets -> seasons/s02/cover/covers_overview.jpg and covers_4x3_overview.jpg  (look at both)
  python tools/make_season_covers.py seasons/s02 season
        season cover -> seasons/s02/cover/season_cover.png and season_cover_4x3.png
  python tools/make_season_covers.py seasons/s02 export [dest]
        upload folder (default: covers.json "export_dir", relative to the project):
        <CODE>E01_<slug>.mp4 + .jpg, nosub/, srt/, covers/, covers_4x3/, <CODE>_season_cover.jpg, 标题与简介.md

Same template as tools/make_covers.py (episode) and tools/make_season_cover.py (season): Fenlo on the left from an H3
first frame, the Chinese title, the English title, and 4 word cards (season: one tile per episode) on the right.

covers.json:
  code        "S02"                          file-name prefix
  ep_tag      "第二季 · 第 {n} 集"            the pill next to the logo
  export_dir  "../Fenlo_Season2"
  hero, hero_4x3                             default position of the big picture (an episode can override)
  episodes    [{dir, frame, theme{primary,pill,wash1,wash2}, cards[{label,color,bg,items[[id,size,rot,dx,dy]],badge?}],
                hero?, hero_4x3?, rainbow?, party?}]   in episode order; titles come from each episode.json
  season_cover {title_zh, title_en, tag, hero_episode, theme, tiles[[item, two-character label, colour, background]]}
Card and tile pictures are assets/skin/<id>.png (the same 3D sprites as the episodes); items from every engine/h5/*items.js.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_season_cover  # noqa: E402
from make_covers import ASPECT_LAYOUTS, EPISODE_COVERS, ROOT, build_html, make_contact_sheet  # noqa: E402


def load(season_dir):
    cfg = json.loads((season_dir / "covers.json").read_text(encoding="utf-8"))
    eps = []
    for num, e in enumerate(cfg["episodes"], 1):
        ep = ROOT / "episodes" / e["dir"]
        spec = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
        slug = re.sub(r"[^a-z0-9]+", "_", spec["title_en"].lower().replace("'", "")).strip("_")
        look = {"hero": cfg["hero"], "hero_4x3": cfg["hero_4x3"], **{k: v for k, v in e.items() if k != "dir"}}
        eps.append((num, ep, spec, f"{cfg['code']}E{num:02d}_{slug}", look))
    return cfg, eps


def render(jobs):
    tmp = Path(tempfile.mkdtemp(prefix="season_covers_"))
    try:
        for j in jobs:
            h = tmp / f"{j['tag']}.html"
            h.write_text(j.pop("page"), encoding="utf-8")
            j["html"] = str(h)
        m = tmp / "manifest.json"
        m.write_text(json.dumps({"jobs": jobs}, ensure_ascii=False), encoding="utf-8")
        subprocess.run(["node", "render_covers.mjs", str(m)], cwd=ROOT / "tools", check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def covers(season_dir, aspects):
    cfg, eps = load(season_dir)
    out = season_dir / "cover"
    out.mkdir(parents=True, exist_ok=True)
    for aspect in aspects:
        lay = ASPECT_LAYOUTS[aspect]
        jobs, pngs = [], []
        for num, ep, spec, tag, look in eps:
            page = build_html(ep, spec, look, num, aspect)
            old = f'<div class="ep-tag">第 {num} 集 · EP{num:02d}</div>'
            assert page.count(old) == 1
            page = page.replace(old, f'<div class="ep-tag">{cfg["ep_tag"].format(n=num)}</div>')
            png = ep / "output" / f"{spec['output_name']}{lay['ep_suffix']}"
            jobs.append({"tag": f"{tag}_{aspect}", "page": page, "png": str(png), "width": lay["stage_w"], "height": lay["stage_h"]})
            pngs.append(png)
        render(jobs)
        sheet = out / ("covers_overview.jpg" if aspect == "16x9" else "covers_4x3_overview.jpg")
        make_contact_sheet(pngs, sheet, lay["sheet_tile"], cols=3)
        print(f"[{aspect}] {len(pngs)} covers, overview {sheet}")


def season(season_dir):
    cfg, eps = load(season_dir)
    sc = cfg["season_cover"]
    out = season_dir / "cover"
    out.mkdir(parents=True, exist_ok=True)
    make_season_cover.SEASON = sc
    EPISODE_COVERS[sc["hero_episode"]] = next(look for _, ep, _, _, look in eps if ep.name == sc["hero_episode"])
    jobs = []
    for aspect, name in (("16x9", "season_cover.png"), ("4x3", "season_cover_4x3.png")):
        lay = ASPECT_LAYOUTS[aspect]
        jobs.append({"tag": f"season_{aspect}", "page": make_season_cover.season_html(aspect), "png": str(out / name),
                     "width": lay["stage_w"], "height": lay["stage_h"]})
    render(jobs)
    print("season cover ->", out)


def jpg(src, dst):
    with Image.open(src) as im:
        im.convert("RGB").save(dst, "JPEG", quality=93, optimize=True)


def export(season_dir, dest):
    cfg, eps = load(season_dir)
    dest = dest or (ROOT / cfg["export_dir"]).resolve()
    for sub in ("nosub", "srt", "covers", "covers_4x3"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
    for num, ep, spec, tag, _ in eps:
        o, n = ep / "output", spec["output_name"]
        shutil.copy2(o / f"{n}.mp4", dest / f"{tag}.mp4")
        shutil.copy2(o / f"{n}_nosub.mp4", dest / "nosub" / f"{tag}_nosub.mp4")
        shutil.copy2(o / f"{n}.srt", dest / "srt" / f"{tag}.srt")
        shutil.copy2(o / f"{n}_cover.png", dest / "covers" / f"{tag}.png")
        jpg(o / f"{n}_cover.png", dest / f"{tag}.jpg")
        shutil.copy2(o / f"{n}_cover_4x3.png", dest / "covers_4x3" / f"{tag}.png")
        jpg(o / f"{n}_cover_4x3.png", dest / "covers_4x3" / f"{tag}.jpg")
        print(f"{tag}.mp4  {(dest / f'{tag}.mp4').stat().st_size / 2**20:6.1f} MB")
    code, cov = cfg["code"], season_dir / "cover"
    if (cov / "season_cover.png").exists():
        shutil.copy2(cov / "season_cover.png", dest / "covers" / f"{code}_season_cover.png")
        jpg(cov / "season_cover.png", dest / f"{code}_season_cover.jpg")
        shutil.copy2(cov / "season_cover_4x3.png", dest / "covers_4x3" / f"{code}_season_cover.png")
        jpg(cov / "season_cover_4x3.png", dest / "covers_4x3" / f"{code}_season_cover.jpg")
    if (season_dir / "publish_titles.md").exists():
        shutil.copy2(season_dir / "publish_titles.md", dest / "标题与简介.md")
    print("exported ->", dest)


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[1] not in ("covers", "season", "export"):
        sys.exit(__doc__)
    season_dir = (ROOT / a[0]).resolve() if not Path(a[0]).is_absolute() else Path(a[0])
    if a[1] == "covers":
        asp = a[a.index("--aspect") + 1] if "--aspect" in a else "all"
        covers(season_dir, ["16x9", "4x3"] if asp == "all" else [asp])
    elif a[1] == "season":
        season(season_dir)
    else:
        export(season_dir, Path(a[2]).resolve() if len(a) > 2 else None)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
