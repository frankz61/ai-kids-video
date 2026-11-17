"""Frame sheet of H3 clips: 3 frames (start / middle / end) per clip, one row per clip.
Usage: python clip_sheet.py <out.jpg> <clip.mp4> [<clip.mp4> ...]
"""
import subprocess
import sys
import tempfile
from pathlib import Path

out, clips = sys.argv[1], sys.argv[2:]
tmp = Path(tempfile.mkdtemp())
rows = []
for n, c in enumerate(clips):
    row = tmp / f"row_{n:02d}.png"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", c, "-vf",
                    "select='eq(n,0)+eq(n,60)+eq(n,119)',scale=400:-2,tile=3x1", "-frames:v", "1", str(row)], check=True)
    rows.append(str(row))
args = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error"]
for r in rows:
    args += ["-i", r]
args += ["-filter_complex", f"vstack=inputs={len(rows)}" if len(rows) > 1 else "null", "-frames:v", "1", out]
subprocess.run(args, check=True)
print("\n".join(f"row {i}: {Path(c).parent.parent.parent.name}/{Path(c).name}" for i, c in enumerate(clips)))
