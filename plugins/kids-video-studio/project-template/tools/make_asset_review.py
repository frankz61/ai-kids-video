"""Asset review page: check every new picture, animation, backdrop and H3 shot BEFORE the episodes are recorded and assembled.

  python tools/make_asset_review.py seasons/s03            -> seasons/s03/asset_review.html
  python tools/make_asset_review.py seasons/s03 --serve    -> also serves it at http://127.0.0.1:8770/... and saves verdicts
                                                              straight into seasons/s03/asset_review.json
  python tools/make_asset_review.py seasons/s03 --check [episode ...]   -> exit 1 if a required asset is not approved

Where it sits:  script -> generator -> tts (writes h5/episode.js) -> assets (make_skin / make_anim / H3 frames, clips,
upscale) -> THIS PAGE -> capture, assemble.  `make_episode.py capture` runs the same check and stops while an asset of
that episode is unreviewed, marked "redo", missing, or changed after it was approved (each verdict stores a hash).

What is listed is what the episode really records and assembles:
  item / anim   every sprite and animation sheet in h5/episode.js "skin" (after the episode's item swaps and groups),
                with the cut-out on a purple checker next to the raw picture as generated; animations loop
  bg            the backdrops in that "skin"
  h3            every H3 shot in episode.json "order", with the clip the assembler will use (clips_1080p, or the
                explicit path of a reused shot) and its first frame and prompts
Required (the gate) = this season's own assets: sprite / backdrop ids with the season prefix ("s3_" for s03, derived
ones such as glows too) and the H3 shots of this season's episodes. Older library assets are listed under "旧素材".

Verdicts: seasons/<season>/asset_review.json {"season", "assets": {key: {"status": "pass"|"redo", "sig", "note", "at"}}}.
Opened as a file (no --serve) the page keeps verdicts in the browser and has "导出 JSON": save it as that file.
"""
import hashlib
import http.server
import json
import os
import re
import secrets
import socketserver
import sys
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from season_lib import used_items  # noqa: E402

SKIN = ROOT / "assets" / "skin"
PORT = 8770
RESULT = "asset_review.json"


# ---------------------------------------------------------------- what an episode records
def season_episodes(season):
    mf = season / "production_manifest.json"
    if mf.exists():
        return [ROOT / e["path"] for e in json.loads(mf.read_text(encoding="utf-8"))["episodes"]]
    return [p.parent for p in sorted((ROOT / "episodes").glob("*/episode.json"))
            if json.loads(p.read_text(encoding="utf-8")).get("season", "s01") == season.name]


def prefix(season_name):
    m = re.fullmatch(r"s0*(\d+)", season_name)
    return f"s{m.group(1)}_" if m else season_name + "_"


def sig(files, meta=None):
    h = hashlib.sha1(json.dumps(meta, sort_keys=True).encode())
    for f in files:
        h.update(f.name.encode())
        h.update(f.read_bytes() if f.exists() else b"<missing>")
    return h.hexdigest()[:16]


def page_js(ep):
    """window.EP from h5/episode.js: what capture records"""
    p = ep / "h5" / "episode.js"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8").split("=", 1)[1].strip().rstrip(";"))


def engine_words():
    try:
        from asset_check import engine_items
        return {k: v["word"] for k, v in engine_items().items()}
    except Exception as e:  # noqa: BLE001  node missing: words are only labels
        print(f"  (no item words: {e})")
        return {}


def tag_of(name):
    m = re.search(r"s\d+e(\d+)", name)
    return f"E{int(m.group(1))}" if m else name


class Lib:
    def __init__(self):
        self.man = json.loads((SKIN / "manifest.json").read_text(encoding="utf-8"))
        pj = json.loads((SKIN / "prompts.json").read_text(encoding="utf-8"))
        self.prompts, self.prompts_bg = pj.get("items", {}), pj.get("bg", {})
        self.by_file = {}                                 # sprite / sheet / backdrop file name -> (kind, manifest name)
        for n, m in self.man["items"].items():
            self.by_file[m["src"]] = ("item", n)
            if "anim" in m:
                self.by_file[m["anim"]["sheet"]] = ("anim", n)
        for n, b in self.man.get("bg", {}).items():
            self.by_file[b["src"]] = ("bg", n)
        self.words = engine_words()

    def root_of(self, name):
        """derived sprites ("from" chains: s3_hands <- s3_hands_l <- s3_fox_body): the generated ancestor"""
        seen = {name}
        while (self.prompts.get(name) or {}).get("from") and self.prompts[name]["from"] not in seen:
            name = self.prompts[name]["from"]
            seen.add(name)
        return name


def item_asset(lib, name, pre, src_file, page_anim):
    """src_file / page_anim: the sprite and animation entry h5/episode.js really uses (manifest only for labels)"""
    m, p = lib.man["items"][name], lib.prompts.get(name, {})
    base = lib.root_of(name)
    pb = lib.prompts.get(base, {})
    video = p.get("video") or {}
    a = dict(key=f"item:{name}", id=name, word=lib.words.get(name, ""), required=name.startswith(pre),
             prompt=p.get("prompt") or video.get("prompt") or pb.get("prompt") or "", seed=p.get("seed", video.get("seed")),
             src=src_file.relative_to(ROOT).as_posix())
    if p.get("from"):
        a["derived"] = " ← ".join([name] + [x for x in _chain(lib, name)][1:])
    files = [src_file]
    if page_anim:
        sheet = page_anim["_file"]
        a.update(kind="anim", sheet=sheet.relative_to(ROOT).as_posix(),
                 anim={k: page_anim[k] for k in ("cols", "rows", "n", "fps") if k in page_anim} | {"once": bool(page_anim.get("once"))})
        files.append(sheet)
        clip = SKIN / "raw" / f"anim_{video.get('reverse') or name}.mp4"
        if clip.exists():
            a["clip"], a["reverse"] = clip.relative_to(ROOT).as_posix(), bool(video.get("reverse"))
        a["fix"] = f"python tools/make_anim.py {name} --force  &&  python tools/make_skin.py --offline"
    else:
        a["kind"] = "item"
        raw = SKIN / "raw" / f"{base}.png"
        if raw.exists():
            a["raw"] = raw.relative_to(ROOT).as_posix()
        a["fix"] = (f"python tools/make_skin.py --offline   （派生图：改 prompts.json 里 {name} 的 glow / erase 坐标）" if p.get("from")
                    else f"python tools/make_skin.py {name} --force")
    a["missing"] = [f.relative_to(ROOT).as_posix() for f in files if not f.exists()]
    meta = {"focus": m.get("focus"), "noShadow": m.get("noShadow"),
            "anim": {k: v for k, v in page_anim.items() if k not in ("_file", "sheet")} if page_anim else None}
    a["sig"] = sig(files, meta)                          # settings that change the picture: fps, once, zoom, focus
    return a


def _chain(lib, name):
    out, seen = [name], {name}
    while (lib.prompts.get(name) or {}).get("from") and lib.prompts[name]["from"] not in seen:
        name = lib.prompts[name]["from"]
        out.append(name)
        seen.add(name)
    return out


def rel_any(f):
    try:
        return f.relative_to(ROOT).as_posix()
    except ValueError:
        return str(f)


def h3_asset(clip, src_ep, n, season_name):
    """clip = the file the assembler reads; src_ep / n = the episode and shot it was made for (None if unknown)"""
    frame = (src_ep / "h3" / "frames" / f"shot_{n:02d}.png") if src_ep else None
    shot = {}
    if src_ep and (src_ep / "h3" / "prompts.json").exists():
        shot = next((s for s in json.loads((src_ep / "h3" / "prompts.json").read_text(encoding="utf-8"))["shots"]
                     if s["id"] == n and not s.get("reuse")), {})
    src_season = json.loads((src_ep / "episode.json").read_text(encoding="utf-8")).get("season", "s01") if src_ep else ""
    files = [clip] + ([frame] if frame else [])
    standard = src_ep and clip == src_ep / "h3" / "clips_1080p" / f"shot_{n:02d}.mp4"
    key = f"h3:{src_ep.name}:{n}" if standard else "h3:" + rel_any(clip)
    return dict(key=key, id=(f"{tag_of(src_ep.name)} H3 第 {n} 镜" if src_ep else clip.name), kind="h3", word="",
                required=src_season == season_name or not src_ep,    # a clip of unknown origin is always checked
                src=frame.relative_to(ROOT).as_posix() if frame and frame.exists() else None,
                clip=rel_any(clip) if clip.exists() else None,
                prompt=shot.get("image_prompt", ""), prompt2=shot.get("prompt_en", ""), seed=shot.get("image_seed"),
                missing=[rel_any(f) for f in files if not f.exists()], sig=sig(files),
                fix=(f"改生成器里这一镜的提示词 → python tools/make_episode.py {src_ep.relative_to(ROOT).as_posix()} frames clips upscale"
                     if src_ep else "重新生成这条片段"))


def episode_assets(ep, lib, season_name):
    """{key: asset} for one episode, plus a list of blocking problems that are not about one asset"""
    spec = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    pre, tag, out, errors = prefix(season_name), tag_of(ep.name), {}, []
    seg_of = {}
    for s in spec.get("segments", []):
        for i in used_items({"segments": [s]}):
            seg_of.setdefault(i, []).append(s["id"])

    def add(a, where):
        a = out.setdefault(a["key"], a)
        a.setdefault("eps", [])
        a.setdefault("uses", [])
        if ep.name not in a["eps"]:
            a["eps"].append(ep.name)
        a["uses"].append(f"{tag} {where}".strip())

    page = page_js(ep)
    skin = (page or {}).get("skin") or {}
    if page is None:
        errors.append(("h5", "h5/episode.js 不存在：先跑 tts 步骤生成页面"))
    elif spec.get("skin") and not skin:
        errors.append(("h5", "episode.json 要用 3D 素材，但 h5/episode.js 里没有 skin：重跑 tts 步骤"))

    def lookup(path):                                     # a path in the page (relative to h5/) -> file, manifest name
        f = (ep / "h5" / path).resolve()
        try:
            return f, lib.by_file.get(f.relative_to(SKIN).as_posix(), (None, None))[1]
        except ValueError:
            return f, None

    for item, path in sorted(skin.get("items", {}).items()):
        f, name = lookup(path)
        if not name:
            errors.append((f"item:{item}", f"页面用的图 {path} 不在 manifest.json 里"))
            continue
        pa = skin.get("anim", {}).get(item)
        if pa:
            pa = dict(pa, _file=(ep / "h5" / pa["sheet"]).resolve())
        add(item_asset(lib, name, pre, f, pa), "、".join(seg_of.get(item, [])) + ("" if item == name else f"（{item} 用这张）"))
    for scene, path in sorted(skin.get("bg", {}).items()):
        f, name = lookup(path)
        if not name:
            errors.append((f"bg:{scene}", f"背景 {path} 不在 manifest.json 里"))
            continue
        pb = lib.prompts_bg.get(name, {})
        add(dict(key=f"bg:{name}", id=name, kind="bg", word=scene, required=name.startswith(pre),
                 src=rel_any(f), prompt=pb.get("prompt", ""), seed=pb.get("seed"),
                 missing=[] if f.exists() else [rel_any(f)], sig=sig([f], {"ground": skin.get("ground", {}).get(scene)}),
                 fix=f"python tools/make_skin.py {name} --force  （背景）"), f"{scene} 场景背景")
    for item in spec.get("order", []):
        if item[0] != "h3":
            continue
        n = item[1]
        if len(item) > 3:                                    # a reused clip: assemble_episode.py reads this path
            clip = (ep / item[3]).resolve()
            m = re.search(r"episodes[\\/]([^\\/]+)[\\/]h3[\\/]clips(?:_1080p)?[\\/]shot_(\d+)\.mp4$", str(clip))
            src_ep, sn = (ROOT / "episodes" / m.group(1), int(m.group(2))) if m else (None, n)
            if src_ep and not (src_ep / "episode.json").exists():
                src_ep = None
        else:
            clip, src_ep, sn = ep / "h3" / "clips_1080p" / f"shot_{n:02d}.mp4", ep, n
        add(h3_asset(clip, src_ep, sn, season_name), "" if src_ep == ep else f"（复用 {src_ep.name if src_ep else clip.name}）")
    return out, errors


def collect(season, eps=None):
    """eps: episode dirs (default: the season's). -> assets {key: asset}, per_ep {name: [keys]}, errors {name: [...]}"""
    lib = Lib()
    assets, per_ep, errors = {}, {}, {}
    for ep in eps or season_episodes(season):
        found, errs = episode_assets(ep, lib, season.name)
        per_ep[ep.name], errors[ep.name] = sorted(found), errs
        for k, a in found.items():
            if k in assets:
                assets[k]["uses"] += a["uses"]
                assets[k]["eps"] += [e for e in a["eps"] if e not in assets[k]["eps"]]
            else:
                assets[k] = a
    return assets, per_ep, errors


def load_result(season):
    p = season / RESULT
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"season": season.name, "assets": {}}


def problems(season, eps=None):
    """[(key, reason)] that block recording these episode dirs"""
    assets, per_ep, errors = collect(season, eps)
    verdicts = load_result(season)["assets"]
    bad = [e for errs in errors.values() for e in errs]
    for k in sorted({k for ks in per_ep.values() for k in ks}):
        a = assets[k]
        if not a["required"]:
            continue
        v = verdicts.get(k)
        if a["missing"]:
            bad.append((k, "文件缺失：" + "、".join(a["missing"])))
        elif not v or not v.get("status"):
            bad.append((k, "未审核"))
        elif v["status"] != "pass":
            bad.append((k, "标为重做" + (f"：{v['note']}" if v.get("note") else "")))
        elif v.get("sig") != a["sig"]:
            bad.append((k, "审核通过后素材又变了，要重审"))
    return bad


def gate(ep):
    """make_episode.py capture: stop while this episode has unapproved assets. Seasons without a review page: warn only."""
    spec = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    season = ROOT / "seasons" / spec.get("season", "s01")
    if not (season / "asset_review.html").exists():
        print(f"  !! 没有素材审核页（python tools/make_asset_review.py {season.relative_to(ROOT).as_posix()} --serve）；"
              "这一季未启用审核关卡", flush=True)
        return
    bad = problems(season, [ep])
    if bad:
        print(f"  素材审核未通过（{len(bad)} 项），不录制：", flush=True)
        for k, why in bad:
            print(f"    {k:40s} {why}")
        print(f"  打开审核页：python tools/make_asset_review.py {season.relative_to(ROOT).as_posix()} --serve\n"
              "  确实要跳过：设环境变量 ASSET_REVIEW=skip", flush=True)
        sys.exit(2)
    print("  素材审核：本集素材全部通过", flush=True)


# ---------------------------------------------------------------- page and server
def build(season):
    assets, per_ep, errors = collect(season)
    rel = "../" * len(season.relative_to(ROOT).parts)
    eps = [dict(id=e, tag=tag_of(e)) for e in per_ep]
    order = {"item": 0, "anim": 1, "bg": 2, "h3": 3}
    rows = sorted(assets.values(), key=lambda a: (not a["required"], order[a["kind"]], a["uses"][0], a["id"]))
    data = dict(season=season.name, root=rel, result=RESULT, episodes=eps, assets=rows, saved=load_result(season)["assets"],
                errors=[f"{tag_of(e)} {k}：{why}" for e, errs in errors.items() for k, why in errs])
    page = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    page = page.replace("__TITLE__", f"{season.name.upper()} 素材审核")
    out = season / "asset_review.html"
    out.write_text(page, encoding="utf-8")
    need = sum(a["required"] for a in rows)
    print(f"wrote {out}: {len(rows)} assets, {need} to review ({sum(a['kind'] == 'h3' for a in rows)} H3 shots)")
    for line in data["errors"]:
        print("  !!", line)
    return out


def serve(season, page):
    """127.0.0.1 only; checks Host (DNS rebinding) and a per-run token on saves; serves only the page, its season folder,
    assets/skin and episodes/*/h3 (the media the page shows)."""
    result, token, lock = season / RESULT, secrets.token_hex(16), threading.Lock()
    hosts = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
    page_rel = page.relative_to(ROOT).as_posix()
    allowed = [season.relative_to(ROOT).as_posix() + "/", "assets/skin/"]

    class H(http.server.SimpleHTTPRequestHandler):
        def _host_ok(self):
            if self.headers.get("Host") not in hosts:
                self.send_error(403, "bad host")
                return False
            return True

        def _path_ok(self):
            if not self._host_ok():
                return None
            path = unquote(urlsplit(self.path).path).lstrip("/")
            if ".." in path.split("/") or "\\" in path or not (any(path.startswith(a) for a in allowed)
                                                or re.fullmatch(r"episodes/[^/]+/h3/(frames|clips|clips_1080p)/[^/]+", path)):
                self.send_error(404)
                return None
            return path

        def do_HEAD(self):
            if self._path_ok() is not None:
                super().do_HEAD()

        def do_GET(self):
            path = self._path_ok()
            if path is None:
                return
            if path == page_rel:                     # inject the save token
                body = page.read_text(encoding="utf-8").replace("__TOKEN__", token).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def end_headers(self):
            if self.path.split("?")[0].endswith(".json"):
                self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_POST(self):
            if not self._host_ok():
                return
            if (self.path != "/__asset_review/save" or self.headers.get("X-Review-Token") != token
                    or not self.headers.get("Content-Type", "").startswith("application/json")):
                self.send_error(403)
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
                assert body.get("season") == season.name and isinstance(body.get("assets"), dict)
                for v in body["assets"].values():
                    assert isinstance(v, dict) and v.get("status") in ("pass", "redo", None)
            except Exception as e:  # noqa: BLE001
                self.send_error(400, str(e))
                return
            with lock:                               # one write at a time, never a half-written file
                tmp = result.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                os.replace(tmp, result)
            self.send_response(204)
            self.end_headers()

        def log_message(self, fmt, *args):
            if "POST" in (fmt % args):
                print("  saved", time.strftime("%H:%M:%S"), flush=True)

    class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = os.name != "nt"      # on Windows it lets a second server take the same port

    from functools import partial
    with Server(("127.0.0.1", PORT), partial(H, directory=str(ROOT))) as httpd:
        print(f"open http://127.0.0.1:{PORT}/{page_rel}   (Ctrl+C to stop; verdicts -> {result})", flush=True)
        httpd.serve_forever()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    season = Path(args[0]).resolve()
    if "--check" in sys.argv:
        eps = None
        if args[1:]:
            eps = [ROOT / "episodes" / Path(a).name for a in args[1:]]
            unknown = [e.name for e in eps if not (e / "episode.json").exists()]
            if unknown:
                sys.exit(f"no such episode: {' '.join(unknown)}")
            other = [e.name for e in eps if json.loads((e / "episode.json").read_text(encoding="utf-8")).get("season", "s01") != season.name]
            if other:
                sys.exit(f"not in {season.name}: {' '.join(other)}")
        bad = problems(season, eps)
        for k, why in bad:
            print(f"  {k:40s} {why}")
        print("OK: 全部通过" if not bad else f"{len(bad)} 项未通过")
        sys.exit(1 if bad else 0)
    page = build(season)
    if "--serve" in sys.argv:
        serve(season, page)


TEMPLATE = r"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f6f4ef;--card:#fff;--ink:#222;--mute:#777;--line:#e2ddd3;--pass:#2e8b57;--redo:#d1495b;--warn:#e09f3e;--acc:#3a6ea5}
@media (prefers-color-scheme:dark){:root{--bg:#1b1b1d;--card:#26262a;--ink:#eee;--mute:#999;--line:#3a3a40}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,"Microsoft YaHei",sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px}
h1{font-size:18px;margin:0 8px 6px 0;display:inline-block}
.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:4px}
.chip{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:14px;padding:3px 10px;cursor:pointer;font-size:13px}
.chip.on{background:var(--acc);border-color:var(--acc);color:#fff}
.stat b{margin:0 2px}.stat .p{color:var(--pass)}.stat .r{color:var(--redo)}.stat .t{color:var(--warn)}
#save{font-size:12px;color:var(--mute);margin-left:auto}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:14px;padding:14px 16px 60px}
.card{background:var(--card);border:2px solid var(--line);border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:8px}
.card.pass{border-color:var(--pass)}.card.redo{border-color:var(--redo)}.card.stale{border-color:var(--warn)}
.head{display:flex;gap:6px;align-items:baseline;flex-wrap:wrap}.head .id{font-weight:700;font-size:15px}
.kind{font-size:11px;padding:1px 6px;border-radius:8px;background:#e8e2f3;color:#5a3f8a}.kind.anim{background:#e0f0e6;color:#2e6b45}
.kind.bg{background:#e3edf7;color:#2d5a85}.kind.h3{background:#f7e8d9;color:#8a5a20}.old{font-size:11px;color:var(--mute)}
.word{color:var(--acc);font-weight:600}
.media{display:flex;gap:6px}.media>div{flex:1;min-width:0;text-align:center;font-size:11px;color:var(--mute)}
.pic{width:100%;aspect-ratio:1;object-fit:contain;border-radius:6px;cursor:zoom-in;display:block}
.checker{background-color:#8a5bb5;background-image:linear-gradient(45deg,#7a4ea5 25%,transparent 25%,transparent 75%,#7a4ea5 75%),linear-gradient(45deg,#7a4ea5 25%,transparent 25%,transparent 75%,#7a4ea5 75%);background-size:20px 20px;background-position:0 0,10px 10px}
.wide .pic,.wide video{aspect-ratio:16/9}video{width:100%;border-radius:6px;background:#000;display:block}
canvas{width:100%;aspect-ratio:1;border-radius:6px;display:block}
.uses{font-size:12px;color:var(--mute)}details{font-size:12px}details p{margin:4px 0;word-break:break-word}
code{font-size:11px;background:rgba(127,127,127,.15);padding:1px 4px;border-radius:4px;word-break:break-all}
.act{display:flex;gap:6px;align-items:flex-start}.act button{border:1px solid var(--line);border-radius:6px;padding:5px 12px;cursor:pointer;background:var(--card);color:var(--ink);font-weight:600}
.act .bp.on{background:var(--pass);color:#fff;border-color:var(--pass)}.act .br.on{background:var(--redo);color:#fff;border-color:var(--redo)}
textarea{flex:1;min-height:32px;resize:vertical;border:1px solid var(--line);border-radius:6px;padding:4px 6px;font:inherit;font-size:12px;background:var(--bg);color:var(--ink)}
.flag{font-size:12px;color:var(--warn);font-weight:600}
#zoom{position:fixed;inset:0;background:rgba(0,0,0,.85);display:none;align-items:center;justify-content:center;z-index:9;cursor:zoom-out}
#zoom img{max-width:94vw;max-height:94vh}#zoom.on{display:flex}
.empty{padding:40px;color:var(--mute)}
#errors div{margin:8px 16px 0;padding:8px 12px;border-radius:8px;background:#fdecea;color:#8a1c2b;font-size:13px}
@media (max-width:420px){main{grid-template-columns:1fr;padding:10px}}
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1><span class="stat" id="stat"></span>
  <div class="bar" id="filters"></div>
  <div class="bar" id="eps"></div>
  <div class="bar">
    <button class="chip" id="bgSwitch">抠图底色：紫格</button>
    <button class="chip" id="passAll">本页可见的待审全部通过</button>
    <button class="chip" id="exportRedo">导出重做清单</button>
    <button class="chip" id="exportJson">导出 JSON</button>
    <label class="chip">导入 JSON<input type="file" id="importJson" accept=".json" hidden></label>
    <span id="save"></span>
  </div>
</header>
<div id="errors"></div>
<main id="grid"></main>
<div id="zoom"><img alt=""></div>
<script>
const D = __DATA__;
const R = D.root, KEY = "asset_review:" + D.season;
const TOKEN = "__TOKEN__";
let V = {};                    // key -> {status, sig, note, at}
let served = location.protocol.startsWith("http") && TOKEN.length === 32;
let filter = "todo", ep = "", bgMode = 0;
const BGS = [["紫格", "checker"], ["白底", ""], ["黑底", ""]];
const state = a => { if (a.missing && a.missing.length) return "missing"; const v = V[a.key]; if (!v || !v.status) return "todo"; if (v.sig !== a.sig) return "stale"; return v.status; };
const inEp = a => !ep || a.eps.includes(ep);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const KIND = {item: "3D 物件", anim: "动画", bg: "背景", h3: "H3 镜头"};
let chain = Promise.resolve();
function hint() {
  document.getElementById("save").textContent = served ? "" : "本地文件打开：结果存在浏览器里，完成后点“导出 JSON”存为 " + D.result + "（或用 --serve 打开，自动保存）";
}
function save() {
  if (locked) return;
  if (!served) { try { localStorage.setItem(KEY, JSON.stringify(V)); } catch (e) {} hint(); return; }
  const body = JSON.stringify({season: D.season, assets: V}), s = document.getElementById("save");
  chain = chain.then(() => fetch("/__asset_review/save", {method: "POST", body,
      headers: {"Content-Type": "application/json", "X-Review-Token": TOKEN}}))      // one save at a time, in order
    .then(r => { s.textContent = r.ok ? "已保存到 " + D.result + " · " + new Date().toLocaleTimeString() : "保存失败 " + r.status + "，请导出 JSON"; })
    .catch(() => { s.textContent = "保存失败（服务停了？），请导出 JSON"; });
}
let locked = false;
async function load() {
  if (served) {
    try {
      const r = await fetch(D.result, {cache: "no-store"});
      if (r.status === 404) V = {};
      else if (r.ok) V = (await r.json()).assets || {};
      else throw new Error("HTTP " + r.status);
    } catch (e) {        // never save over verdicts we could not read
      locked = true; V = Object.assign({}, D.saved);
      document.getElementById("save").textContent = "读不到 " + D.result + "（" + e.message + "），已停止保存：刷新重试";
    }
  } else {               // browser drafts and the file baked into the page: per asset, the later verdict wins
    V = Object.assign({}, D.saved);
    let local = {};
    try { local = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
    for (const [k, v] of Object.entries(local)) if (!V[k] || (v.at || "") > (V[k].at || "")) V[k] = v;
  }
  if (!locked) hint();
  render();
}
function setV(a, patch) {
  V[a.key] = Object.assign({}, V[a.key] || {}, patch, {sig: a.sig, at: new Date().toISOString()});
  save(); render();
}
function stats() {
  const req = D.assets.filter(a => a.required && inEp(a));
  const c = {todo: 0, stale: 0, pass: 0, redo: 0, missing: 0}; req.forEach(a => c[state(a)]++);
  const errs = D.errors.filter(e => !ep || e.startsWith(D.episodes.find(x => x.id === ep).tag + " "));
  document.getElementById("stat").innerHTML = `必审 ${req.length}：<b class="p">通过 ${c.pass}</b>·<b class="r">重做 ${c.redo}</b>·<b class="t">待审 ${c.todo + c.stale}</b>` +
    (c.missing ? `·<b class="r">缺文件 ${c.missing}</b>` : "") + (c.pass === req.length && req.length && !errs.length ? " ✅ 可以合成" : "");
  document.getElementById("errors").innerHTML = errs.map(e => `<div>不能合成：${esc(e)}</div>`).join("");
  return c;
}
function chips() {
  const f = [["todo", "待审"], ["redo", "重做"], ["pass", "通过"], ["all", "全部必审"], ["old", "旧素材"]];
  document.getElementById("filters").innerHTML = f.map(([k, t]) => `<button class="chip ${filter === k ? "on" : ""}" data-f="${k}">${t}</button>`).join("") +
    ["item", "anim", "bg", "h3"].map(k => `<button class="chip ${filter === k ? "on" : ""}" data-f="${k}">${KIND[k]}</button>`).join("");
  const e = [["", "全部集"]].concat(D.episodes.map(x => [x.id, x.tag]));
  document.getElementById("eps").innerHTML = e.map(([k, t]) => `<button class="chip ${ep === k ? "on" : ""}" data-e="${k}">${t}</button>`).join("");
}
function visible() {
  return D.assets.filter(a => {
    if (!inEp(a)) return false;
    const s = state(a);
    if (filter === "old") return !a.required;
    if (!a.required) return false;
    if (filter === "todo") return s === "todo" || s === "stale" || s === "missing";
    if (filter === "redo" || filter === "pass") return s === filter;
    if (filter in KIND) return a.kind === filter;
    return true;
  });
}
function media(a) {
  const bgc = BGS[bgMode][1], style = bgMode === 1 ? "background:#fff" : bgMode === 2 ? "background:#111" : "";
  const pic = (src, label, wide) => src ? `<div class="${wide ? "wide" : ""}"><img class="pic ${wide ? "" : bgc}" style="${wide ? "" : style}" loading="lazy" src="${R + src}">${label}</div>` : "";
  if (a.kind === "h3") return a.clip ? `<video controls preload="none" src="${R + a.clip}" poster="${a.src ? R + a.src : ""}"></video>` +
      (a.src ? `<div class="uses"><a href="${R + a.src}" target="_blank">首帧大图</a>（视频封面就是首帧）</div>` : "")
    : `<div class="media wide">${pic(a.src, "首帧（还没有视频）", true)}</div>`;
  if (a.kind === "bg") return `<div class="media wide">${pic(a.src, "背景", true)}</div>`;
  if (a.kind === "anim") return `<div class="media"><div><canvas class="${bgc}" style="${style}" data-k="${a.key}"></canvas>动画循环</div>${pic(a.src, "静态图（单词卡、封面用）")}</div>` +
    (a.clip ? `<details><summary>原始 H3 视频${a.reverse ? "（本动画是它倒放）" : ""}</summary><video controls preload="none" src="${R + a.clip}"></video></details>` : "");
  return `<div class="media">${pic(a.src, "抠图后（画面里用的）")}${pic(a.raw, "原图")}</div>`;
}
function card(a) {
  const s = state(a), v = V[a.key] || {};
  return `<div class="card ${s}" data-k="${a.key}">
    <div class="head"><span class="kind ${a.kind}">${KIND[a.kind]}</span><span class="id">${esc(a.id)}</span>
      ${a.word ? `<span class="word">${esc(a.word)}</span>` : ""}${a.required ? "" : `<span class="old">旧素材，不卡合成</span>`}
      ${s === "stale" ? `<span class="flag">审核后素材变了</span>` : ""}${s === "missing" ? `<span class="flag">缺文件：${a.missing.map(esc).join("、")}</span>` : ""}</div>
    ${media(a)}
    <div class="uses">用在：${a.uses.map(esc).join("；")}${a.derived ? "　·　派生：" + esc(a.derived) : ""}</div>
    <details><summary>提示词与重做命令</summary>${a.prompt ? `<p>${esc(a.prompt)}</p>` : ""}${a.prompt2 ? `<p><b>视频：</b>${esc(a.prompt2)}</p>` : ""}
      ${a.seed != null ? `<p>seed ${a.seed}</p>` : ""}<p><code>${esc(a.fix)}</code></p></details>
    ${a.required && s !== "missing" ? `<div class="act"><button class="bp ${s === "pass" ? "on" : ""}" data-s="pass">通过</button><button class="br ${s === "redo" ? "on" : ""}" data-s="redo">重做</button>
      <textarea placeholder="意见（重做时写清楚哪里不对）">${esc(v.note || "")}</textarea></div>` : ""}
  </div>`;
}
const anims = [];
function render() {
  chips(); stats();
  const list = visible();
  const g = document.getElementById("grid");
  g.innerHTML = list.length ? list.map(card).join("") : `<div class="empty">这里没有素材。${filter === "todo" ? "待审的都审完了。" : ""}</div>`;
  anims.length = 0;
  g.querySelectorAll("canvas").forEach(c => {
    const a = D.assets.find(x => x.key === c.dataset.k), img = new Image();
    img.onload = () => anims.push({c, a, img, cw: img.naturalWidth / a.anim.cols, ch: img.naturalHeight / a.anim.rows});
    img.src = R + a.sheet;
  });
}
let t0 = performance.now();
function tick(t) {
  for (const x of anims) {
    const {c, a, img, cw, ch} = x, n = a.anim.n, fps = a.anim.fps || 12;
    let f = Math.floor((t - t0) / 1000 * fps);
    f = a.anim.once ? Math.min(f % (n + fps * 1.5), n - 1) : f % n;      // once: play, hold 1.5 s, replay
    if (c.width !== cw) { c.width = cw; c.height = ch; }
    const ctx = c.getContext("2d"); ctx.clearRect(0, 0, cw, ch);
    ctx.drawImage(img, (f % a.anim.cols) * cw, Math.floor(f / a.anim.cols) * ch, cw, ch, 0, 0, cw, ch);
  }
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
document.addEventListener("click", e => {
  const t = e.target;
  if (t.dataset.f) { filter = t.dataset.f; render(); }
  else if (t.dataset.e !== undefined && t.classList.contains("chip")) { ep = t.dataset.e; render(); }
  else if (t.dataset.s) {
    const a = D.assets.find(x => x.key === t.closest(".card").dataset.k);
    const note = t.closest(".card").querySelector("textarea").value;
    if (t.dataset.s === "redo" && !note.trim()) { t.closest(".card").querySelector("textarea").focus(); t.closest(".card").querySelector("textarea").placeholder = "先写一句哪里不对，再点重做"; return; }
    setV(a, {status: t.dataset.s, note});
  }
  else if (t.classList.contains("pic")) { const z = document.getElementById("zoom"); z.querySelector("img").src = t.src; z.classList.add("on"); }
  else if (t.closest("#zoom")) document.getElementById("zoom").classList.remove("on");
});
document.addEventListener("change", e => {
  if (e.target.tagName === "TEXTAREA") {
    const a = D.assets.find(x => x.key === e.target.closest(".card").dataset.k);
    V[a.key] = Object.assign({}, V[a.key] || {}, {note: e.target.value}); save();
  }
});
document.getElementById("bgSwitch").onclick = e => { bgMode = (bgMode + 1) % 3; e.target.textContent = "抠图底色：" + BGS[bgMode][0]; render(); };
document.getElementById("passAll").onclick = () => {
  const todo = visible().filter(a => a.required && ["todo", "stale"].includes(state(a)));
  if (!todo.length || !confirm(`把当前列出的 ${todo.length} 项待审素材全部标为通过？`)) return;
  todo.forEach(a => V[a.key] = Object.assign({}, V[a.key] || {}, {status: "pass", sig: a.sig, at: new Date().toISOString()}));
  save(); render();
};
function download(name, text, type) {
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], {type})); a.download = name; a.click();
}
document.getElementById("exportJson").onclick = () => download(D.result, JSON.stringify({season: D.season, assets: V}, null, 1), "application/json");
document.getElementById("exportRedo").onclick = () => {
  const r = D.assets.filter(a => a.required && state(a) === "redo");
  download(D.season + "_asset_redo.md", `# ${D.season} 素材重做清单（${r.length} 项）\n\n` + r.map(a =>
    `## ${a.id}（${KIND[a.kind]}${a.word ? " · " + a.word : ""}）\n- 意见：${(V[a.key] || {}).note || ""}\n- 用在：${a.uses.join("；")}\n` +
    `- 提示词：${a.prompt}${a.prompt2 ? "\n- 视频提示词：" + a.prompt2 : ""}\n- 重做：\`${a.fix}\`\n`).join("\n"), "text/markdown");
};
document.getElementById("importJson").onchange = e => {
  const f = e.target.files[0]; if (!f) return;
  f.text().then(t => { const j = JSON.parse(t); if (j.season !== D.season) { alert("不是 " + D.season + " 的审核结果"); return; } V = j.assets || {}; save(); render(); });
};
load();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
