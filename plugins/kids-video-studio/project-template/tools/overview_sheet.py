"""Overview sheet of a finished episode: one frame every N seconds, tiled. Usage: python tools/overview_sheet.py <episode_dir> [seconds]"""
import json
import subprocess
import sys
from pathlib import Path

ep = Path(sys.argv[1]).resolve()
step = float(sys.argv[2]) if len(sys.argv) > 2 else 9
name = json.loads((ep / "episode.json").read_text(encoding="utf-8"))["output_name"]
out = ep / "build" / "overview.jpg"
subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(ep / "output" / f"{name}.mp4"),
                "-vf", f"fps=1/{step},scale=480:-1,tile=4x5", "-frames:v", "1", str(out)], check=True)
print(out)
