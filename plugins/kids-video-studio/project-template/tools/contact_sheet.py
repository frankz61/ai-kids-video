"""Tile images into one contact sheet. Usage: python contact_sheet.py <out.jpg> <cols> <img> [<img> ...]"""
import subprocess
import sys
import tempfile
from pathlib import Path

out, cols, imgs = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
tmp = Path(tempfile.mkdtemp())
for i, f in enumerate(imgs):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", f, "-vf", "scale=480:270", str(tmp / f"s_{i:02d}.png")], check=True)
rows = -(-len(imgs) // cols)
subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-framerate", "1", "-i", str(tmp / "s_%02d.png"),
                "-vf", f"tile={cols}x{rows}", "-frames:v", "1", out], check=True)
for i, f in enumerate(imgs):
    print(i, Path(f).parent.parent.parent.name, Path(f).name)
