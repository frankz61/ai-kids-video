"""Export an episode's voice lines to lines.json for the Colab TTS run.
Usage: python export_lines.py <episode_dir> <out.json>
"""
import importlib.util
import json
import sys
from pathlib import Path

ep = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location("ep_tts", ep / "audio" / "tts.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
lines = {k: {"role": "hero" if s is mod.HERO else "narrator", "text": t} for k, (s, t) in mod.LINES.items()}
Path(sys.argv[2]).write_text(json.dumps(lines, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"{len(lines)} lines -> {sys.argv[2]}")
