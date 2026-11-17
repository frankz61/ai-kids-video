"""Shared season tooling: voice settings, the cross-episode voice-line cache, episode spec loading.

An episode is described by <episode>/episode.json:
{
  "id": "ep02_numbers", "output_name": "ep02_one_more_balloon", "title_en": "...", "title_zh": "...", "bg": "outdoor",
  "lines":    {"n_q": {"role": "narrator", "text": "[curious] How many?", "zh": "有几个？"}, ...},
  "segments": [ ...H5 engine segments (see engine/h5/engine.js)... ],
  "order":    [["h5", "intro"], ["h3", 1, [["n_line", 0.9]]], ["h3", 3, [], "../ep02_numbers/h3/clips_1080p/shot_01.mp4"], ...],
  "credits_voice": "ElevenLabs"
}
Lines shared by every episode (hello / bye) live in seasons/s01/common_lines.json and are merged in.
"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SEASON = ROOT / "seasons" / "s01"
CACHE = SEASON / "voice_cache"
sys.path.insert(0, str(ROOT / "tools"))

SR = 44100
MODEL = "eleven_v4"
SETTINGS = {"stability": 0.4, "similarity_boost": 0.75}   # v4 only has stability + similarity
VOICES = {  # free-tier keys can only use premade voices
    "narrator": {"voice": "cgSgspJ2msm6clMCkdW9", "tempo": 0.93, "pitch": 1.0},   # Jessica: young, playful
    "hero": {"voice": "FGY2WhTYpPnrIDTdsKH5", "tempo": 1.0, "pitch": 1.14},       # Laura, pitched up for Fenlo
}
TAG = re.compile(r"\[[^\]]*\]\s*")
TRIM = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
        "silenceremove=start_periods=1:start_threshold=-45dB,areverse")


def spoken(text):
    return TAG.sub("", text).strip()


def load_episode(ep: Path) -> dict:
    spec = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    common = json.loads((SEASON / "common_lines.json").read_text(encoding="utf-8"))
    spec["lines"] = {**common, **spec.get("lines", {})}
    return spec


def run(cmd, cwd=None, timeout=900):
    """Run a command; ffmpeg always gets -nostdin and no stdin (it can block polling stdin in the background)."""
    cmd = [str(c) for c in cmd]
    if cmd[0] == "ffmpeg" and "-nostdin" not in cmd:
        cmd = [cmd[0], "-nostdin", *cmd[1:]]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise SystemExit("COMMAND FAILED:\n" + " ".join(cmd)[:600] + "\n" + (r.stderr or r.stdout)[-3000:])
    return r.stdout


def read_wav(path):
    with wave.open(str(path), "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (SR, 2, 2), path
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).reshape(-1, 2).astype(np.float32) / 32768


def write_wav(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def wav_seconds(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


# ---------------- voice lines ----------------
def cache_key(role, text):
    v = VOICES[role]
    blob = json.dumps([MODEL, SETTINGS, v["voice"], v["tempo"], v["pitch"], text], sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def post_process(src, dst, role):
    """Trim silence, hero pitch-up / narrator slow-down, peak-normalise to -3 dBFS (same as EP01)."""
    v, af = VOICES[role], [TRIM]
    if v["pitch"] != 1.0:
        af.append(f"asetrate={SR * v['pitch']:.0f},aresample={SR},atempo={1 / v['pitch']:.5f}")
    if v["tempo"] != 1.0:
        af.append(f"atempo={v['tempo']}")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-af", ",".join(af),
         "-ar", SR, "-ac", "2", "-c:a", "pcm_s16le", dst])
    x = read_wav(dst)
    peak = float(np.abs(x).max()) if len(x) else 0.0
    if peak < 1e-4:
        return 0.0
    write_wav(dst, x * (0.708 / peak))
    return len(x) / SR


def synth_line(role, text, dst: Path, retries=4):
    import eleven
    limit = 0.7 + 0.17 * len(spoken(text))
    chars = 0
    for _ in range(retries):
        mp3 = dst.with_suffix(".mp3")
        mp3.write_bytes(eleven.tts(text, VOICES[role]["voice"], MODEL, SETTINGS))
        chars += len(text)
        dur = post_process(mp3, dst, role)
        mp3.unlink()
        if 0.25 <= dur <= limit:
            return dur, chars
        print(f"    retry: {dur:.2f}s outside 0.25..{limit:.2f}s", flush=True)
    raise SystemExit(f"could not get a clean take for: {text}")


def seed_cache_from_ep01():
    """EP01 lines were synthesized before the cache existed: register them so identical lines are reused."""
    import importlib.util
    ep01 = ROOT / "episodes" / "ep01_colors"
    spec = importlib.util.spec_from_file_location("ep01_tts", ep01 / "audio" / "tts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    CACHE.mkdir(parents=True, exist_ok=True)
    n = 0
    for key, (s, text) in mod.LINES.items():
        role = "hero" if s is mod.HERO else "narrator"
        src, dst = ep01 / "audio" / "tts" / f"{key}.wav", CACHE / f"{cache_key(role, text)}.wav"
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst); n += 1
    return n


def episode_tts(ep: Path, only=()):
    """Make every line of the episode available in <ep>/audio/tts, synthesizing only lines not in the cache."""
    spec = load_episode(ep)
    CACHE.mkdir(parents=True, exist_ok=True)
    out = ep / "audio" / "tts"
    out.mkdir(parents=True, exist_ok=True)
    durations, chars, new = {}, 0, 0
    for key, ln in spec["lines"].items():
        cached = CACHE / f"{cache_key(ln['role'], ln['text'])}.wav"
        if key in only and cached.exists():
            cached.unlink()
        if not cached.exists():
            d, c = synth_line(ln["role"], ln["text"], cached)
            chars += c; new += 1
            print(f"  + {key:20s} {d:5.2f}s  {ln['text']}", flush=True)
        shutil.copy2(cached, out / f"{key}.wav")
        durations[key] = {"text": spoken(ln["text"]), "dur": round(wav_seconds(cached), 3)}
    for stale in out.glob("*.wav"):
        if stale.stem not in spec["lines"]:
            stale.unlink()
    (ep / "audio" / "durations.json").write_text(json.dumps(durations, indent=2), encoding="utf-8")
    h5 = ep / "h5"
    h5.mkdir(exist_ok=True)
    (h5 / "durations.js").write_text("window.DUR = " + json.dumps(durations, indent=1) + ";\n", encoding="utf-8")
    page_spec = {k: spec[k] for k in ("id", "title_en", "bg", "segments") if k in spec}
    if spec.get("skin"):
        page_spec["skin"] = page_skin(spec)
    (h5 / "episode.js").write_text("window.EP = " + json.dumps(page_spec, indent=1, ensure_ascii=False) + ";\n", encoding="utf-8")
    index = h5 / "index.html"
    if not index.exists() or "engine/h5/engine.js" in index.read_text(encoding="utf-8"):
        index.write_text(PAGE.replace("{TITLE}", spec.get("title_en", spec["id"])), encoding="utf-8")
    print(f"tts: {len(durations)} lines, {new} newly synthesized, {chars} characters sent", flush=True)
    return chars


def used_items(spec):
    """Item ids an episode's segments show."""
    ids = set()
    for s in spec.get("segments", []):
        ids.update(x for x in (s.get("item"), s.get("swapTo")) if x)
        ids.update(q if isinstance(q, str) else q["id"] for q in s.get("items", []))
        for ln in s.get("lines", []):
            if isinstance(ln, dict):
                ids.update(x for x in [ln.get("item"), *ln.get("show", [])] if x)
    return ids


def page_skin(spec, rel="../../../assets/skin/"):
    """EP.skin for the H5 engine, from assets/skin/manifest.json (made by tools/make_skin.py).
    episode.json: "skin": true, or {"bg": {"outdoor": "orchard"}} to use another backdrop for one of the engine's scenes,
    and/or {"items": {"rabbit": "rabbit_jump"}} to show another picture for an item in this episode."""
    man = json.loads((ROOT / "assets" / "skin" / "manifest.json").read_text(encoding="utf-8"))
    opt = spec["skin"] if isinstance(spec["skin"], dict) else {}
    swap = opt.get("items", {})        # {"rabbit": "rabbit_jump"}: this episode shows another picture for an item
    items = {i: man["items"][swap.get(i, i)] for i in used_items(spec) if swap.get(i, i) in man["items"]}
    out = {"items": {i: rel + e["src"] for i, e in items.items()},
           "covers": {c: rel + e["src"] for c, e in man["covers"].items()},
           "coverFront": {c: rel + e["front"] for c, e in man["covers"].items() if "front" in e},
           "focus": {i: e["focus"] for i, e in items.items() if "focus" in e},
           "noShadow": [i for i, e in items.items() if e.get("noShadow")],
           "anim": {i: {**e["anim"], "sheet": rel + e["anim"]["sheet"]} for i, e in items.items() if "anim" in e},
           "bg": {}, "ground": {}}
    for scene in ("outdoor", "indoor", "party"):
        name = opt.get("bg", {}).get(scene, scene)
        if name in man["bg"]:
            out["bg"][scene] = rel + man["bg"][name]["src"]
            out["ground"][scene] = man["bg"][name]["ground"]
    if "brush" in man:
        out["brush"] = rel + man["brush"]
    return out


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{TITLE} - H5 scenes</title>
<link rel="stylesheet" href="../../../engine/h5/engine.css"></head>
<body><div id="stage"></div>
<script src="../../../engine/h5/items.js"></script>
<script>document.write('<script src="' + (new URLSearchParams(location.search).get("dur") || "durations.js") + '"><\\/script>');</script>
<script src="episode.js"></script>
<script src="../../../engine/h5/engine.js"></script>
</body></html>
"""
