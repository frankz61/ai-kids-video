"""Render episode.json (+ h3/prompts.json) as a readable script for review.
Usage: python tools/render_script.py <episode_dir> [<episode_dir> ...] > script.md
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from season_lib import load_episode  # noqa: E402

for arg in sys.argv[1:]:
    ep = Path(arg).resolve()
    spec = load_episode(ep)
    L = spec["lines"]
    shots = {}
    pj = ep / "h3" / "prompts.json"
    if pj.exists():
        shots = {s["id"]: s for s in json.loads(pj.read_text(encoding="utf-8"))["shots"]}
    segs = {s["id"]: s for s in spec["segments"]}
    say = lambda k: f'{"Fenlo" if L[k]["role"] == "hero" else "Narrator"}: {L[k]["text"]}  （{L[k].get("zh", "")}）'  # noqa: E731
    print(f"# {spec['id']}  《{spec.get('title_zh', '')}》 {spec.get('title_en', '')}\n")
    print(f"背景：{spec.get('bg', 'outdoor')}　输出：{spec['output_name']}\n")
    for n, item in enumerate(spec["order"], 1):
        if item[0] == "h3":
            s = shots.get(item[1], {})
            reuse = f"（复用：{item[3]}）" if len(item) > 3 else ""
            print(f"**{n}. H3 镜头 {item[1]}**{reuse} 画面：{s.get('prompt_en', '(reused clip)')}")
            for k, at in item[2]:
                print(f"   - {at:.1f}s  {say(k)}")
            continue
        seg = segs[item[1]]
        t = seg["type"]
        if t == "ritual":
            print(f"**{n}. H5 画笔仪式**（Fenlo 举起画笔，笔尖金光） " + say(seg.get("say", "m_brush")))
        elif t in ("intro", "outro"):
            print(f"**{n}. H5 {t}** " + say(seg.get("say", "m_hello" if t == "intro" else "m_bye"))
                  + (f"　物体：{', '.join(seg.get('items', []))}" if seg.get("items") else ""))
        elif t == "teach":
            items = seg.get("items") or [seg["item"]] * seg.get("count", 1)
            print(f"**{n}. H5 教学 `{seg['id']}`** 画面：{' + '.join(items)}（{seg.get('reveal', 'draw')}"
                  + (f"，藏在 {seg['cover']} 后" if seg.get("cover") else "") + f"）　大字：{seg.get('word', '')}")
            for b in seg.get("beats", []):
                marks = [m for m in ("q", "word", "pulse", "act", "point", "countPulse", "show") if b.get(m)]
                print(f"   - {say(b['say']) if b.get('say') else '(停顿)'}  [{', '.join(marks)}] 之后停 {b.get('after', 1.0)}s")
        elif t == "quiz":
            row = [q if isinstance(q, str) else f"{q['id']}（{q.get('word', '')}，{q.get('scale', 1)}倍）" for q in seg["items"]]
            print(f"**{n}. H5 互动 `{seg['id']}`** 画面一排：{', '.join(row)}")
            for r in seg["rounds"]:
                wait = r.get("wait", 2.4 if r.get("demo") else 4.0)
                ans = r.get("answer") or []
                ans = ans if isinstance(ans, list) else [ans]
                print(f"   - {say(r['ask'])} → 停 {wait}s{'（手势示范）' if r.get('demo') else ''} → "
                      + (" → ".join(say(a) for a in ans) if ans else "(无)") + f"　高亮 {r['target']}" + ("，做动作" if r.get("act") else ""))
        elif t == "chant":
            print(f"**{n}. H5 念唱**（重复 {seg.get('repeat', 2)} 遍）")
            for ln in seg["lines"]:
                print(f"   - {say(ln['say'])}　画面 {ln.get('item') or ' + '.join(ln.get('show', []))}")
    print()
