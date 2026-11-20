"""Season quick-review page: every episode in one local page, switch episodes, change speed, jump by chapter or line,
write review notes with time stamps and export them.

  python tools/make_review_page.py seasons/s02        -> seasons/s02/review.html   (open it in a browser, no server)

Reads <season>/production_manifest.json (episodes: number, id, path; without it: the episodes whose episode.json
"season" is this season), each episode.json (titles, target words),
output/<name>.srt (lines), build/concat.txt + build/segments/ (chapters), previews/<id>_720p.mp4.
Notes and statuses are kept in the browser (localStorage) and can be exported as Markdown.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = {"intro": "开场", "problem": "故事·问题", "ritual": "魔法画笔", "solution": "故事·解决", "old_words": "复习旧词",
          "outro": "结尾", "chant": "儿歌"}


def duration(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def chapters(ep):
    """[(start, dur, kind, label)] from the order the episode was assembled in"""
    lst = ep / "build" / "concat.txt"
    if not lst.exists():
        return []
    out, t = [], 0.0
    for line in lst.read_text(encoding="utf-8").splitlines():
        m = re.match(r"file '(.+)'", line)
        if not m:
            continue
        seg = Path(m.group(1))
        d = duration(seg)
        name = re.sub(r"^\d+_", "", seg.stem)            # h5_teach_open / h3_2
        src, _, sid = name.partition("_")
        if src == "h3":
            kind, label = "h3", f"H3 镜头 {sid}"
        elif sid.startswith("teach_"):
            kind, label = "teach", "教 " + sid[6:]
        elif sid.startswith("quiz"):
            kind, label = "quiz", "小测 " + sid[4:]
        elif sid.startswith("chant"):
            kind, label = "chant", "儿歌 " + sid[6:] if sid != "chant" else "儿歌"
        elif sid in ("problem", "solution"):
            kind, label = "story", LABELS[sid]
        else:
            kind, label = "other", LABELS.get(sid, sid)
        out.append([round(t, 2), round(d, 2), kind, label])
        t += d
    return out


def srt(p):
    if not p.exists():
        return []
    cues = []
    for block in re.split(r"\n\s*\n", p.read_text(encoding="utf-8-sig").strip()):
        rows = block.strip().splitlines()
        if len(rows) < 3:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", rows[1])
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        a = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        b = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        cues.append([round(a, 2), round(b, 2), rows[2], rows[3] if len(rows) > 3 else ""])
    return cues


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    season = Path(sys.argv[1]).resolve()
    mf = season / "production_manifest.json"
    if mf.exists():
        man = json.loads(mf.read_text(encoding="utf-8"))
    else:   # no manifest: every episode whose episode.json says this season (no "season" key = s01), by folder name
        found = [p.parent for p in sorted((ROOT / "episodes").glob("*/episode.json"))
                 if json.loads(p.read_text(encoding="utf-8")).get("season", "s01") == season.name]
        man = {"episodes": [{"number": i, "id": p.name, "path": p.relative_to(ROOT).as_posix()} for i, p in enumerate(found, 1)]}
    eps = []
    for e in man["episodes"]:
        ep = ROOT / e["path"]
        spec = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
        name = spec["output_name"]
        master = ep / "output" / f"{name}.mp4"
        rel = lambda p: Path("../" * len(season.relative_to(ROOT).parts) + p.relative_to(ROOT).as_posix()).as_posix()
        preview = season / "previews" / f"{e['id']}_720p.mp4"
        eps.append(dict(
            n=e["number"], id=e["id"], zh=spec.get("title_zh") or e.get("title", ""), en=spec.get("title_en", ""),
            words=spec.get("target_words", []), dur=round(duration(master), 1),
            src={"720p 预览": preview.relative_to(season).as_posix() if preview.exists() else None,
                 "1080p 字幕版": rel(master) if master.exists() else None,
                 "1080p 无字幕": rel(master.with_name(f"{name}_nosub.mp4")) if master.with_name(f"{name}_nosub.mp4").exists() else None},
            overview=rel(ep / "build" / "overview.jpg") if (ep / "build" / "overview.jpg").exists() else None,
            chapters=chapters(ep), cues=srt(ep / "output" / f"{name}.srt")))
        print(f"  {e['id']}: {eps[-1]['dur']}s, {len(eps[-1]['chapters'])} chapters, {len(eps[-1]['cues'])} lines", flush=True)
    zh = {f"s{i:02d}": f"第{n}季" for i, n in enumerate("一二三四五六七八九十", 1)}
    data = dict(season=season.name, title=f"Fenlo {zh.get(season.name, season.name)}", episodes=eps)
    page = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    page = page.replace("__TITLE__", f"{season.name.upper()} 快速审查")
    out = season / "review.html"
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out}")


TEMPLATE = r"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --bg: #f7f3ec; --panel: #fffdf9; --ink: #26323a; --muted: #6c7780; --line: #e6dfd3; --accent: #d9622b;
  --accent-ink: #fff; --chip: #f0ebe2; --hover: #f3eee5;
  --k-h3: #e98a3a; --k-teach: #3f7fd0; --k-quiz: #2f9d6a; --k-chant: #9a5ad1; --k-story: #1c9aa6; --k-other: #9aa3ab;
  --ok: #2f9d6a; --fix: #d64545; --todo: #b8b0a3;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #15191c; --panel: #1d2226; --ink: #e8e4dd; --muted: #98a2aa; --line: #2e353a; --accent: #f08a4b;
    --accent-ink: #1a1a1a; --chip: #262c31; --hover: #252b30;
  }
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body { background: var(--bg); color: var(--ink); font: 14px/1.5 system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }
button { font: inherit; color: inherit; cursor: pointer; }
.app { display: grid; grid-template-columns: 260px minmax(0, 1fr) 360px; grid-template-rows: auto 1fr; height: 100vh; }
header { grid-column: 1 / -1; display: flex; align-items: center; gap: 16px; padding: 10px 18px; border-bottom: 1px solid var(--line); background: var(--panel); }
header h1 { font-size: 16px; margin: 0; font-weight: 650; }
header .sum { color: var(--muted); }
header .sp { flex: 1; }
.btn { border: 1px solid var(--line); background: var(--panel); border-radius: 8px; padding: 5px 12px; }
.btn:hover { background: var(--hover); }
.btn.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
/* episode list */
nav { overflow-y: auto; border-right: 1px solid var(--line); padding: 8px; }
.ep { display: grid; grid-template-columns: 30px 1fr auto; gap: 2px 10px; align-items: center; width: 100%; text-align: left;
      border: 0; background: none; border-radius: 10px; padding: 8px 10px; }
.ep:hover { background: var(--hover); }
.ep.on { background: var(--chip); box-shadow: inset 3px 0 0 var(--accent); }
.ep .num { grid-row: 1 / 3; font-weight: 700; font-size: 15px; color: var(--muted); text-align: center; }
.ep.on .num { color: var(--accent); }
.ep .t { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ep .w { grid-column: 2; color: var(--muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ep .st { grid-row: 1 / 3; grid-column: 3; display: flex; flex-direction: column; align-items: flex-end; gap: 4px; font-size: 12px; color: var(--muted); }
.dot { width: 9px; height: 9px; border-radius: 50%; background: var(--todo); }
.dot.ok { background: var(--ok); } .dot.fix { background: var(--fix); }
/* player */
main { overflow-y: auto; padding: 16px 20px 24px; min-width: 0; }
.vwrap { background: #000; border-radius: 12px; overflow: hidden; aspect-ratio: 16 / 9; }
video { width: 100%; height: 100%; display: block; }
.bar { margin-top: 10px; position: relative; height: 26px; border-radius: 6px; overflow: hidden; display: flex; background: var(--chip); cursor: pointer; }
.bar .c { height: 100%; border-right: 1px solid var(--panel); opacity: .78; }
.bar .c:hover, .bar .c.on { opacity: 1; }
.bar .ph { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--ink); pointer-events: none; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 6px; color: var(--muted); font-size: 12px; }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 5px; vertical-align: -1px; }
.now { margin-top: 10px; display: flex; align-items: baseline; gap: 12px; }
.now h2 { margin: 0; font-size: 18px; }
.now .chap { color: var(--muted); }
.ctrl { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 18px; margin-top: 10px; }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.seg button { border: 0; background: var(--panel); padding: 5px 11px; border-right: 1px solid var(--line); }
.seg button:last-child { border-right: 0; }
.seg button.on { background: var(--accent); color: var(--accent-ink); }
.seg button:disabled { opacity: .35; cursor: default; }
.lbl { color: var(--muted); margin-right: 6px; }
label.chk { display: inline-flex; gap: 6px; align-items: center; color: var(--muted); cursor: pointer; }
.keys { margin-top: 14px; color: var(--muted); font-size: 12px; }
kbd { font: 11px ui-monospace, monospace; border: 1px solid var(--line); border-bottom-width: 2px; border-radius: 4px; padding: 0 4px; background: var(--panel); }
/* side panel */
aside { border-left: 1px solid var(--line); display: flex; flex-direction: column; min-height: 0; background: var(--panel); }
.tabs { display: flex; border-bottom: 1px solid var(--line); }
.tabs button { flex: 1; border: 0; background: none; padding: 10px; color: var(--muted); border-bottom: 2px solid transparent; }
.tabs button.on { color: var(--ink); border-bottom-color: var(--accent); font-weight: 600; }
.pane { flex: 1; overflow-y: auto; padding: 8px; display: none; }
.pane.on { display: block; }
.cue { display: grid; grid-template-columns: 44px 1fr; gap: 0 8px; padding: 6px 8px; border-radius: 8px; cursor: pointer; }
.cue:hover { background: var(--hover); }
.cue.on { background: var(--chip); box-shadow: inset 3px 0 0 var(--accent); }
.cue .tm { color: var(--muted); font: 12px ui-monospace, monospace; padding-top: 2px; }
.cue .zh { grid-column: 2; color: var(--muted); font-size: 12.5px; }
.cue .ch { grid-column: 1 / -1; font-size: 11px; font-weight: 600; color: var(--muted); margin: 8px 0 2px; text-transform: none; }
.notes { padding: 6px; display: flex; flex-direction: column; gap: 10px; height: 100%; }
.status { display: flex; gap: 6px; }
.status button { flex: 1; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); padding: 6px; }
.status button.on.todo { background: var(--todo); color: #fff; border-color: var(--todo); }
.status button.on.ok { background: var(--ok); color: #fff; border-color: var(--ok); }
.status button.on.fix { background: var(--fix); color: #fff; border-color: var(--fix); }
textarea { flex: 1; min-height: 220px; width: 100%; resize: vertical; border: 1px solid var(--line); border-radius: 8px; padding: 10px;
           background: var(--bg); color: var(--ink); font: 13.5px/1.6 inherit; }
.hint { color: var(--muted); font-size: 12px; }
.ov img { width: 100%; border-radius: 8px; display: block; }
.toast { position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%); background: var(--ink); color: var(--bg);
         padding: 6px 14px; border-radius: 8px; opacity: 0; transition: opacity .2s; pointer-events: none; }
.toast.show { opacity: .92; }
@media (max-width: 1100px) {
  .app { grid-template-columns: 220px minmax(0, 1fr); grid-template-rows: auto 1fr auto; height: auto; min-height: 100vh; }
  aside { grid-column: 1 / -1; border-left: 0; border-top: 1px solid var(--line); height: 60vh; }
}
@media (max-width: 700px) {
  .app { grid-template-columns: 1fr; }
  header { flex-wrap: wrap; gap: 4px 12px; padding: 10px 16px; }
  header h1 { flex-basis: 100%; }
  header .sp { display: none; }
  #export { margin-left: auto; padding: 4px 10px; }
  nav { display: flex; overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--line); }
  .ep { min-width: 200px; }
  main { padding: 12px 16px; }
}
</style>
</head>
<body>
<div class="app">
  <header>
    <h1 id="ttl"></h1><span class="sum" id="sum"></span><span class="sp"></span>
    <span class="sum" id="prog"></span>
    <button class="btn primary" id="export">导出审查意见</button>
  </header>
  <nav id="list"></nav>
  <main>
    <div class="vwrap"><video id="v" controls playsinline preload="metadata"></video></div>
    <div class="bar" id="bar"><div class="ph" id="ph"></div></div>
    <div class="legend" id="legend"></div>
    <div class="now"><h2 id="eptitle"></h2><span class="chap" id="chap"></span></div>
    <div class="ctrl">
      <span><span class="lbl">倍速</span><span class="seg" id="speeds"></span></span>
      <span><span class="lbl">版本</span><span class="seg" id="srcs"></span></span>
      <span class="seg"><button id="prev">‹ 上一集</button><button id="next">下一集 ›</button></span>
      <label class="chk"><input type="checkbox" id="auto"> 播完自动下一集</label>
      <label class="chk"><input type="checkbox" id="skiph3"> 跳过 H3 镜头</label>
    </div>
    <div class="keys">
      <kbd>空格</kbd> 播放/暂停　<kbd>←</kbd><kbd>→</kbd> 5 秒　<kbd>,</kbd><kbd>.</kbd> 上/下一章节　<kbd>[</kbd><kbd>]</kbd> 减/加速
      　<kbd>P</kbd><kbd>N</kbd> 上/下一集　<kbd>M</kbd> 在审查意见里记下当前时间
    </div>
  </main>
  <aside>
    <div class="tabs"><button data-t="cues" class="on">台词</button><button data-t="notes">审查意见</button><button data-t="ov">总览图</button></div>
    <div class="pane on" id="p-cues"></div>
    <div class="pane" id="p-notes">
      <div class="notes">
        <div class="status" id="status">
          <button data-s="todo" class="todo">未审</button><button data-s="ok" class="ok">通过</button><button data-s="fix" class="fix">要改</button>
        </div>
        <button class="btn" id="mark">插入当前时间 [mm:ss]</button>
        <textarea id="note" placeholder="例如：[01:23] 第二个 open 箱子打开太快"></textarea>
        <div class="hint">只存在这个浏览器里。点右上角“导出审查意见”下载全部集的意见（Markdown）。</div>
      </div>
    </div>
    <div class="pane ov" id="p-ov"></div>
  </aside>
</div>
<div class="toast" id="toast"></div>
<script type="application/json" id="data">__DATA__</script>
<script>
"use strict";
const D = JSON.parse(document.getElementById("data").textContent);
const EPS = D.episodes, KEY = "review:" + D.season + ":";
const SPEEDS = [0.75, 1, 1.25, 1.5, 2, 3];
const KINDS = { h3: "H3 镜头", story: "故事", teach: "教学", quiz: "小测", chant: "儿歌", other: "其他" };
const $ = id => document.getElementById(id);
const v = $("v");
const store = {
  get(k, d) { try { const x = localStorage.getItem(KEY + k); return x === null ? d : JSON.parse(x); } catch (e) { return d; } },
  set(k, x) { try { localStorage.setItem(KEY + k, JSON.stringify(x)); } catch (e) {} },
};
const fmt = s => { s = Math.max(0, Math.floor(s)); return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); };
let cur = 0, speed = store.get("speed", 1), srcName = store.get("src", "720p 预览"), cueEls = [], chapEls = [];

function toast(t) { const e = $("toast"); e.textContent = t; e.classList.add("show"); clearTimeout(toast.h); toast.h = setTimeout(() => e.classList.remove("show"), 1200); }
const statusOf = i => store.get("status:" + EPS[i].id, "todo");

function renderList() {
  $("list").innerHTML = "";
  EPS.forEach((e, i) => {
    const b = document.createElement("button");
    b.className = "ep" + (i === cur ? " on" : "");
    b.innerHTML = `<span class="num">${String(e.n).padStart(2, "0")}</span><span class="t"></span><span class="w"></span>
      <span class="st"><span class="dot ${statusOf(i)}"></span><span>${fmt(e.dur)}</span></span>`;
    b.querySelector(".t").textContent = e.zh;
    b.querySelector(".w").textContent = e.words.join(" · ") || e.en;
    b.onclick = () => load(i, true);
    $("list").appendChild(b);
  });
  const done = EPS.filter((_, i) => statusOf(i) !== "todo").length, fix = EPS.filter((_, i) => statusOf(i) === "fix").length;
  $("prog").textContent = `已审 ${done}/${EPS.length}` + (fix ? `，要改 ${fix}` : "");
}

function renderSpeeds() {
  $("speeds").innerHTML = "";
  for (const s of SPEEDS) {
    const b = document.createElement("button");
    b.textContent = s + "×"; b.className = s === speed ? "on" : "";
    b.onclick = () => setSpeed(s);
    $("speeds").appendChild(b);
  }
}
function setSpeed(s) { speed = s; v.playbackRate = v.defaultPlaybackRate = s; store.set("speed", s); renderSpeeds(); toast(s + "× 倍速"); }

function renderSrcs() {
  const e = EPS[cur];
  $("srcs").innerHTML = "";
  for (const [name, path] of Object.entries(e.src)) {
    const b = document.createElement("button");
    b.textContent = name; b.disabled = !path; b.className = name === srcName ? "on" : "";
    b.onclick = () => { const t = v.currentTime, playing = !v.paused; srcName = name; store.set("src", name); setSrc(t, playing); renderSrcs(); };
    $("srcs").appendChild(b);
  }
}
function setSrc(t, playing) {
  const e = EPS[cur];
  const path = e.src[srcName] || Object.values(e.src).find(Boolean);
  v.src = path;
  v.addEventListener("loadedmetadata", () => { v.currentTime = t || 0; v.playbackRate = v.defaultPlaybackRate = speed; if (playing) v.play().catch(() => {}); }, { once: true });
}

function renderBar() {
  const e = EPS[cur], total = e.chapters.reduce((a, c) => a + c[1], 0) || e.dur || 1;
  const bar = $("bar"); bar.querySelectorAll(".c").forEach(x => x.remove()); chapEls = [];
  e.chapters.forEach(([st, d, kind, label]) => {
    const c = document.createElement("div");
    c.className = "c"; c.style.width = (100 * d / total) + "%"; c.style.background = `var(--k-${kind})`;
    c.title = `${label}　${fmt(st)}–${fmt(st + d)}`;
    c.onclick = ev => { ev.stopPropagation(); v.currentTime = st + 0.01; };
    bar.insertBefore(c, $("ph")); chapEls.push(c);
  });
  const used = [...new Set(e.chapters.map(c => c[2]))];
  $("legend").innerHTML = used.map(k => `<span><i style="background:var(--k-${k})"></i>${KINDS[k]}</span>`).join("");
}
$("bar").onclick = ev => { const r = $("bar").getBoundingClientRect(); const e = EPS[cur]; const total = e.chapters.reduce((a, c) => a + c[1], 0) || v.duration; v.currentTime = total * (ev.clientX - r.left) / r.width; };

function renderCues() {
  const e = EPS[cur], p = $("p-cues"); p.innerHTML = ""; cueEls = [];
  let ci = -1;
  e.cues.forEach(([a, b, en, zh]) => {
    const k = e.chapters.findIndex(c => a >= c[0] && a < c[0] + c[1]);
    if (k !== ci && k >= 0) { ci = k; const h = document.createElement("div"); h.className = "cue"; h.style.cursor = "default";
      h.innerHTML = `<span class="ch"></span>`; h.firstChild.textContent = e.chapters[k][3]; h.firstChild.style.color = `var(--k-${e.chapters[k][2]})`; p.appendChild(h); }
    const r = document.createElement("div");
    r.className = "cue"; r.innerHTML = `<span class="tm">${fmt(a)}</span><span class="en"></span><span class="zh"></span>`;
    r.querySelector(".en").textContent = en; r.querySelector(".zh").textContent = zh;
    r.onclick = () => { v.currentTime = a; v.play().catch(() => {}); };
    r._a = a; r._b = b; p.appendChild(r); cueEls.push(r);
  });
  if (!e.cues.length) p.innerHTML = `<div class="hint" style="padding:10px">这一集没有找到字幕文件。</div>`;
}

function renderNotes() {
  const e = EPS[cur];
  $("note").value = store.get("note:" + e.id, "");
  const s = statusOf(cur);
  $("status").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.s === s));
}
$("note").addEventListener("input", () => store.set("note:" + EPS[cur].id, $("note").value));
$("status").querySelectorAll("button").forEach(b => b.onclick = () => { store.set("status:" + EPS[cur].id, b.dataset.s); renderNotes(); renderList(); });
function mark() {
  const ta = $("note"), stamp = `[${fmt(v.currentTime)}] `;
  const pos = ta.selectionStart ?? ta.value.length;
  const before = ta.value.slice(0, pos), pre = before && !before.endsWith("\n") ? "\n" : "";
  ta.value = before + pre + stamp + ta.value.slice(pos);
  store.set("note:" + EPS[cur].id, ta.value);
  showTab("notes"); ta.focus(); ta.selectionStart = ta.selectionEnd = pos + pre.length + stamp.length;
}
$("mark").onclick = mark;

function renderOv() {
  const e = EPS[cur];
  $("p-ov").innerHTML = e.overview ? `<a href="${e.overview}" target="_blank"><img src="${e.overview}" alt="总览图"></a><div class="hint" style="margin-top:6px">每个片段一帧，点击看大图。</div>` : `<div class="hint">没有总览图。</div>`;
}

function showTab(t) {
  document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("on", b.dataset.t === t));
  document.querySelectorAll(".pane").forEach(p => p.classList.toggle("on", p.id === "p-" + t));
}
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => showTab(b.dataset.t));

function load(i, play) {
  if (EPS[cur]) store.set("t:" + EPS[cur].id, v.currentTime || 0);
  cur = (i + EPS.length) % EPS.length; store.set("ep", cur);
  const e = EPS[cur];
  $("eptitle").textContent = `${String(e.n).padStart(2, "0")} ${e.zh}`;
  renderList(); renderSrcs(); renderBar(); renderCues(); renderNotes(); renderOv();
  const t = store.get("t:" + e.id, 0);
  setSrc(t > e.dur - 3 ? 0 : t, play);
}

function tick() {
  const e = EPS[cur], t = v.currentTime, total = e.chapters.reduce((a, c) => a + c[1], 0) || v.duration || 1;
  $("ph").style.left = (100 * t / total) + "%";
  const k = e.chapters.findIndex(c => t >= c[0] && t < c[0] + c[1]);
  chapEls.forEach((c, i) => c.classList.toggle("on", i === k));
  $("chap").textContent = k >= 0 ? `${e.chapters[k][3]} · ${fmt(t)} / ${fmt(e.dur)}` : `${fmt(t)} / ${fmt(e.dur)}`;
  if ($("skiph3").checked && k >= 0 && e.chapters[k][2] === "h3" && !v.paused) v.currentTime = e.chapters[k][0] + e.chapters[k][1] + 0.02;
  let on = -1;
  cueEls.forEach((r, i) => { const a = t >= r._a && t < r._b + 0.3; r.classList.toggle("on", a); if (a) on = i; });
  if (on >= 0 && on !== tick.last) { tick.last = on; const r = cueEls[on], p = $("p-cues");
    if (p.classList.contains("on") && (r.offsetTop < p.scrollTop || r.offsetTop > p.scrollTop + p.clientHeight - 60)) p.scrollTop = r.offsetTop - p.clientHeight / 3; }
}
v.addEventListener("timeupdate", tick);
v.addEventListener("seeked", tick);
v.addEventListener("ended", () => { store.set("t:" + EPS[cur].id, 0); if ($("auto").checked) load(cur + 1, true); });
setInterval(() => { if (EPS[cur] && !v.paused) store.set("t:" + EPS[cur].id, v.currentTime); }, 2000);

function jumpChapter(dir) {
  const e = EPS[cur], t = v.currentTime;
  const k = e.chapters.findIndex(c => t >= c[0] && t < c[0] + c[1]);
  let j = dir > 0 ? k + 1 : (t - (e.chapters[k]?.[0] ?? 0) > 1.5 ? k : k - 1);
  j = Math.max(0, Math.min(e.chapters.length - 1, j));
  if (e.chapters[j]) { v.currentTime = e.chapters[j][0] + 0.01; toast(e.chapters[j][3]); }
}
$("prev").onclick = () => load(cur - 1, !v.paused);
$("next").onclick = () => load(cur + 1, !v.paused);
for (const id of ["auto", "skiph3"]) { $(id).checked = store.get(id, false); $(id).onchange = () => store.set(id, $(id).checked); }

document.addEventListener("keydown", ev => {
  if (ev.target.tagName === "TEXTAREA" || ev.target.tagName === "INPUT" && ev.target.type !== "checkbox") return;
  if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
  const k = ev.key;
  if (k === " ") { ev.preventDefault(); v.paused ? v.play().catch(() => {}) : v.pause(); }
  else if (k === "ArrowLeft") { ev.preventDefault(); v.currentTime = Math.max(0, v.currentTime - 5); }
  else if (k === "ArrowRight") { ev.preventDefault(); v.currentTime += 5; }
  else if (k === "[" || k === "]") { const i = SPEEDS.indexOf(speed); setSpeed(SPEEDS[Math.max(0, Math.min(SPEEDS.length - 1, (i < 0 ? 1 : i) + (k === "]" ? 1 : -1)))]); }
  else if (k === "," ) jumpChapter(-1);
  else if (k === ".") jumpChapter(1);
  else if (k === "n" || k === "N") load(cur + 1, !v.paused);
  else if (k === "p" || k === "P") load(cur - 1, !v.paused);
  else if (k === "m" || k === "M") { ev.preventDefault(); mark(); }
});

$("export").onclick = () => {
  const name = { todo: "未审", ok: "通过", fix: "要改" };
  let md = `# ${D.title} 审查意见\n\n导出时间：${new Date().toLocaleString()}\n\n`;
  EPS.forEach((e, i) => {
    const note = store.get("note:" + e.id, "").trim();
    md += `## ${String(e.n).padStart(2, "0")} ${e.zh}（${name[statusOf(i)]}）\n\n${note || "（无）"}\n\n`;
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
  a.download = `${D.season}_review_notes.md`; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
};

$("ttl").textContent = D.title + " · 快速审查";
$("sum").textContent = `${EPS.length} 集 · 共 ${fmt(EPS.reduce((a, e) => a + e.dur, 0))}`;
renderSpeeds();
load(Math.min(store.get("ep", 0), EPS.length - 1), false);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
