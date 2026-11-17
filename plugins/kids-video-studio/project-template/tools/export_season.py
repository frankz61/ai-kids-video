"""Copy every finished episode of a season into one folder outside the project.

Usage: python tools/export_season.py <dest_dir>
Layout:  <dest>/S01E01_<name>.mp4 (subtitled)   <dest>/nosub/...   <dest>/srt/...   <dest>/covers/...   <dest>/covers_4x3/...
"""
import json
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
dest = Path(sys.argv[1])
for sub in ("", "nosub", "srt", "covers", "covers_4x3"):
    (dest / sub).mkdir(parents=True, exist_ok=True)
for ep in sorted(p for p in (ROOT / "episodes").glob("ep[0-9][0-9]_*") if p.is_dir()):
    spec = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    name, num = spec["output_name"], int(ep.name[2:4])
    out = ep / "output"
    tag = f"S01E{num:02d}_{name.split('_', 1)[1]}"
    for src, dst in ((out / f"{name}.mp4", dest / f"{tag}.mp4"), (out / f"{name}_nosub.mp4", dest / "nosub" / f"{tag}_nosub.mp4"),
                     (out / f"{name}.srt", dest / "srt" / f"{tag}.srt")):
        shutil.copy2(src, dst)
    cover_png = out / f"{name}_cover.png"
    if cover_png.exists():
        shutil.copy2(cover_png, dest / "covers" / f"{tag}.png")
        with Image.open(cover_png) as im:
            im.convert("RGB").save(dest / f"{tag}.jpg", "JPEG", quality=93, optimize=True)
    cover_4x3_png = out / f"{name}_cover_4x3.png"
    if cover_4x3_png.exists():
        shutil.copy2(cover_4x3_png, dest / "covers_4x3" / f"{tag}.png")
        with Image.open(cover_4x3_png) as im:
            im.convert("RGB").save(dest / "covers_4x3" / f"{tag}.jpg", "JPEG", quality=93, optimize=True)
    print(f"{tag}.mp4  {(dest / f'{tag}.mp4').stat().st_size / 2**20:6.1f} MB")
