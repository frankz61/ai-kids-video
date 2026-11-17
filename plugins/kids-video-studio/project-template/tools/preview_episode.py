"""Write the H5 page for an episode with ESTIMATED line durations (no voice synthesis), for layout checks.
Usage: python tools/preview_episode.py <episode_dir>
The real durations are written later by `make_episode.py <ep> tts`, which overwrites these files.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from season_lib import PAGE, load_episode, spoken  # noqa: E402

ep = Path(sys.argv[1]).resolve()
spec = load_episode(ep)
h5 = ep / "h5"
h5.mkdir(exist_ok=True)
dur = {k: {"text": spoken(v["text"]), "dur": round(0.35 + 0.075 * len(spoken(v["text"])), 2)} for k, v in spec["lines"].items()}
(h5 / "durations.js").write_text("window.DUR = " + json.dumps(dur) + ";\n", encoding="utf-8")
page = {k: spec[k] for k in ("id", "title_en", "bg", "segments") if k in spec}
(h5 / "episode.js").write_text("window.EP = " + json.dumps(page, ensure_ascii=False) + ";\n", encoding="utf-8")
if not (h5 / "index.html").exists():
    (h5 / "index.html").write_text(PAGE.replace("{TITLE}", spec.get("title_en", spec["id"])), encoding="utf-8")
print("preview page written:", h5 / "index.html")
