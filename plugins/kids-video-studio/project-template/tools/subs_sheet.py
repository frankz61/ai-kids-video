"""Contact sheet of frames taken mid-cue for selected subtitle lines.
Usage: python subs_sheet.py <video> <srt> <out.jpg> <substring> [<substring> ...]
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

video, srt, out, *wants = sys.argv[1:]
blocks = re.findall(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)\r?\n(.+)",
                    Path(srt).read_text(encoding="utf-8"))
tmp = Path(tempfile.mkdtemp())
n = 0
for w in wants:
    for b in blocks:
        if w in b[8]:
            a = int(b[0]) * 3600 + int(b[1]) * 60 + int(b[2]) + int(b[3]) / 1000
            e = int(b[4]) * 3600 + int(b[5]) * 60 + int(b[6]) + int(b[7]) / 1000
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-ss", f"{(a + e) / 2:.3f}",
                            "-frames:v", "1", "-vf", "scale=640:360", str(tmp / f"k_{n:02d}.jpg")], check=True)
            print(f"{n}  {(a + e) / 2:7.2f}s  {b[8]}")
            n += 1
            break
cols = 3
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "1", "-i", str(tmp / "k_%02d.jpg"),
                "-vf", f"tile={cols}x{-(-n // cols)}", "-frames:v", "1", out], check=True)
