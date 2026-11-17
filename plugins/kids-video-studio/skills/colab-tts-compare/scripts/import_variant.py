"""Turn one engine's raw Colab output into a voice variant of an episode.

Applies exactly the same post-processing as the main ElevenLabs voice (trim silence, narrator slowed 7%,
hero pitched up 14%, peak-normalised), so the comparison is about the voices, not the processing.

Usage: python import_variant.py <episode_dir> <engine> <raw_dir>
Writes <episode>/audio/variants/<engine>/{tts/*.wav, durations.json, durations.js} and copies durations.js
next to the H5 page as durations_<engine>.js (load it with capture.mjs --dur durations_<engine>.js).
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

ep, engine, raw = Path(sys.argv[1]).resolve(), sys.argv[2], Path(sys.argv[3])
spec = importlib.util.spec_from_file_location("ep_tts", ep / "audio" / "tts.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

var = ep / "audio" / "variants" / engine
(var / "tts").mkdir(parents=True, exist_ok=True)
durations, missing = {}, []
for key, (s, text) in mod.LINES.items():
    src = raw / f"{key}.wav"
    if not src.exists():
        missing.append(key)
        continue
    d = mod.to_wav(src, var / "tts" / f"{key}.wav", s)
    durations[key] = {"text": re.sub(r"\[[^\]]*\]\s*", "", text), "dur": round(d, 3)}
if missing:
    raise SystemExit(f"{engine}: missing lines {missing}")
(var / "durations.json").write_text(json.dumps(durations, indent=2), encoding="utf-8")
js = "window.DUR = " + json.dumps(durations, indent=1) + ";\n"
(ep / "h5" / f"durations_{engine}.js").write_text(js, encoding="utf-8")
total = sum(v["dur"] for v in durations.values())
print(f"{engine}: {len(durations)} lines, {total:.1f}s of speech -> {var}")
