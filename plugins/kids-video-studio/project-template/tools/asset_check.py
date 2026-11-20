"""Shared asset library check: reuse what exists, 3D by default, actions as animations.

  python tools/asset_check.py find <word> [<word> ...]     # before making an asset: is there one already?
  python tools/asset_check.py episode <episode dir> [...]  # every item an episode uses: 3D? animated where it should be?
  python tools/asset_check.py list [3d|anim|flat]          # the whole library

The library is one for all seasons:
  engine/h5/items.js, engine/h5/season2-items.js   every item the H5 engine knows (id, word, vector fallback)
  assets/skin/prompts.json, assets/skin/manifest.json   its 3D picture (H3-Image sprite) or animation (H3 video -> sprite sheet)

Item kinds:  anim = H3 video turned into an animation   3d = 3D sprite   3d-group = a group drawn from another item's
3D sprite (four ducks)   flat = vector drawing only (to be replaced: assets are 3D by default).
`episode` exits with 1 when an item is flat or an action word is not animated.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SKIN = ROOT / "assets" / "skin"
ITEM_FILES = [p for p in sorted((ROOT / "engine/h5").glob("*items.js")) if p.exists()]   # items.js + per-season files
# words children learn by seeing them done: a still picture of "run" and "jump" looks the same. These get an animation.
ACTION_WORDS = {
    "jump", "hop", "run", "walk", "swim", "fly", "clap", "wave", "dance", "sing", "kick", "throw", "catch", "climb", "sit",
    "stand", "sleep", "eat", "drink", "wash", "brush", "open", "close", "push", "pull", "go", "stop", "turn", "spin",
    "roll", "ride", "drive", "cook", "read", "write", "draw", "paint", "cut", "pour", "blow", "shake", "nod", "point",
    "touch", "hug", "kiss", "cry", "laugh", "smile", "look", "listen", "carry", "pick", "drop", "help", "rain", "snow",
    "sunny", "rainy", "windy", "cloudy", "snowy",     # weather: the sun shines, the rain falls, the wind blows
}


def engine_items():
    """{id: {"word", "compose"}} from the engine's item files (run in node: the files are plain browser scripts)."""
    js = ("const vm=require('vm'),fs=require('fs');const ctx={window:{}};vm.createContext(ctx);"
          f"for(const f of {json.dumps([str(p) for p in ITEM_FILES])}) vm.runInContext(fs.readFileSync(f,'utf8'),ctx);"
          "const o={};for(const [k,v] of Object.entries(ctx.window.ITEMS)) o[k]={word:v.word||'',compose:v.compose?v.compose.of:null};"
          "process.stdout.write(JSON.stringify(o));")
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8", check=True).stdout)


def library():
    items = engine_items()
    man = json.loads((SKIN / "manifest.json").read_text(encoding="utf-8"))["items"]
    prompts = json.loads((SKIN / "prompts.json").read_text(encoding="utf-8"))["items"]
    lib = {}
    for i in sorted(set(items) | set(man)):
        e, m, p = items.get(i, {}), man.get(i), prompts.get(i, {})
        if m and "anim" in m:
            kind = "anim"
        elif m:
            kind = "3d"
        elif e.get("compose") and e["compose"] in man:
            kind = "3d-group"
        else:
            kind = "flat"
        text = p.get("prompt") or (p.get("video") or {}).get("prompt") or ""
        lib[i] = dict(kind=kind, word=e.get("word", ""), prompt=text,
                      file=(m["anim"]["sheet"] if m and "anim" in m else m["src"]) if m else "",
                      engine=i in items)
    return lib


def find(words):
    lib = library()
    for w in words:
        w = w.lower()
        rx = re.compile(rf"\b{re.escape(w)}s?\b")
        hits = []
        for i, a in lib.items():
            base = re.sub(r"^s\d+_", "", i)
            score = 3 if base == w or a["word"].lower() == w else 2 if w in base.split("_") or rx.search(a["word"].lower()) \
                else 1 if rx.search(a["prompt"].lower()) else 0
            if score:
                hits.append((-score, i, a))
        print(f"== {w}: {len(hits)} match(es)" + ("" if hits else " -- nothing in the library, make a new 3D asset"))
        for _, i, a in sorted(hits)[:12]:
            note = "" if a["engine"] else "   (another picture for an item: episode.json \"skin\": {\"items\": {\"<item>\": \"<this>\"}})"
            print(f"  {a['kind']:8s} {i:22s} word={a['word']!r:14s} {a['file']}{note}")
            if a["prompt"]:
                print(f"           {a['prompt'][:110]}")


def episode(ep):
    from season_lib import used_items
    spec = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    lib = library()
    swap = spec["skin"].get("items", {}) if isinstance(spec.get("skin"), dict) else {}
    used = sorted(used_items(spec))
    targets = {w.lower() for w in spec.get("target_words", [])}
    problems = []
    print(f"== {ep.name}: {len(used)} items, target words: {', '.join(sorted(targets))}")
    if not used:
        print("  -> no items found: this episode.json is in an older format (season 1); check it by eye")
        return True
    for i in used:
        if i in ("fenlo", "hero"):
            continue
        a = lib.get(swap.get(i, i)) or {"kind": "missing", "word": ""}
        word = a["word"].lower()
        action = word in ACTION_WORDS and (word in targets or not targets)
        flag = ""
        if a["kind"] in ("flat", "missing"):
            flag = "NOT 3D: make a 3D sprite (tools/make_skin.py)"
        elif action and a["kind"] != "anim":
            flag = "ACTION, NOT ANIMATED: make an animation (tools/make_anim.py)"
        if flag:
            problems.append(i)
        print(f"  {a['kind']:8s} {i:22s} {word:12s} {flag}")
    print(f"  -> {'OK' if not problems else str(len(problems)) + ' to fix: ' + ' '.join(problems)}")
    return not problems


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("find", "episode", "list"):
        sys.exit(__doc__)
    if a[0] == "find":
        find(a[1:])
    elif a[0] == "episode":
        ok = all([episode(Path(p).resolve()) for p in a[1:]])
        sys.exit(0 if ok else 1)
    else:
        lib = library()
        for i, x in lib.items():
            if len(a) < 2 or x["kind"].startswith(a[1]):
                print(f"{x['kind']:8s} {i:22s} {x['word']}")
        kinds = {}
        for x in lib.values():
            kinds[x["kind"]] = kinds.get(x["kind"], 0) + 1
        print(kinds)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
