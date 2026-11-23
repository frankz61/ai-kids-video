"""Generate the season's 3D-style "skin": pre-rendered item sprites, covers, brush and backdrops (Qwen-Image).

Usage: python tools/make_skin.py [name ...] [--force] [--sheet]
Reads  assets/skin/prompts.json:
  {"items":  {"apple": {"prompt": "one shiny red apple ...", "seed": 11, "style": "object"|"animal"|"face"|"raw",
                        "key": "blue"|"green", "box": [x0, y0, x1, y1], "focus": [x, y], "noShadow": true},
              "nose":  {"from": "fenlo", "glow": [cx, cy, rx, ry], "focus": [x, y]},      # derived: base sprite + highlight ring
              "hands": {"from": "hero_body", "spot": [[cx, cy, rx, ry], ...]},      # derived: rest grey, parts in colour + glow
              "dry":   {"prompt": "...", "tone": {"mul": [r, g, b], "sat": 1, "gamma": 1}, "sparkle": [[x, y, size]]},
              "fenlo_nonose": {"from": "fenlo", "erase": [cx, cy, rx, ry]}},              # derived: a patch painted over
   "covers": {"basket": {"prompt": "...", "front": {"cx": 100, "cy": 98, "rx": 88, "ry": 20}}},
   "brush":  {"prompt": "..."},
   "bg":     {"outdoor": {"prompt": "...", "seed": 7, "blur": 6, "ground": 548}}}
Writes assets/skin/raw/<name>.png (as generated), assets/skin/<name>.png (cut out, 800x800: the object fitted into "box" of
the engine's 200x200 item square, bottom-aligned), <cover>_front.png (the part of a cover that is in front of the items),
bg_<name>.jpg, and manifest.json (read by season_lib when an episode has "skin" in episode.json).
Sprites are generated on a flat blue (or green, for blue things) screen and keyed out here: no extra model needed.
All coordinates are in engine units of the 200x200 item square.
"""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from season_lib import ROOT  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
URL = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
SKIN = ROOT / "assets" / "skin"
ISOLATE = ("the whole subject fully visible and centered with empty space around it, floating in the air, no shadow, "
           "isolated on a perfectly flat uniform solid pure {key} backdrop, no gradient, no light rays, no lens flare, no glow, "
           "no text, no letters, no watermark")
STYLES = {
    "object": "Pixar-style 3D cartoon render, soft even studio lighting, glossy smooth surface, clean simple shapes, no face, no eyes, no mouth, ",
    "animal": "Pixar-style 3D cartoon character render, cute chubby baby animal with big round friendly eyes, soft fluffy look, "
              "soft even studio lighting, full body, ",
    "face": "Pixar-style 3D cartoon character render, soft fluffy fur, soft even studio lighting, head and neck only, front view, "
            "looking straight at the viewer, ",
    "raw": "Pixar-style 3D cartoon render, soft even studio lighting, clean simple shapes, ",
}
BG_STYLE = ("Pixar-style 3D cartoon render, soft warm light, shallow depth of field, "
            "children's animation film background, wide 16:9, no characters, no animals, no people, no text, no letters, no watermark")
SIZE = 800
K = SIZE / 200


def generate(prompt, w, h, seed, dest):
    import h3_client as h3
    info = h3.queue_and_wait(URL, h3.build_t2i_workflow(prompt, w, h, seed, f"skin_{dest.stem}"), output_node="11")
    h3.download_output(URL, info, dest)


def key_out(bgr, key="blue", sat_min=0.0):
    """Chroma key (blue or green screen). Returns BGRA and the object's bounding box (x0, y0, x1, y1)."""
    f = bgr.astype(np.float32) / 255
    ki = 0 if key == "blue" else 1
    kc = f[..., ki]
    oth = [f[..., c] for c in range(3) if c != ki]
    dom = kc - np.maximum(oth[0], oth[1])
    # background = key-dominant pixels connected to the image border (key-coloured reflections inside the object stay)
    # sat_min ("keySat" in prompts.json, about 0.5): white fur in shade picks up the screen colour and would be cut away
    # with it; the screen itself is far more saturated, so only strongly saturated key colour counts as background
    sat = (kc - np.minimum(oth[0], oth[1])) / np.maximum(kc, 1e-3)
    cand = ((dom > 0.10) & (sat > sat_min)).astype(np.uint8)
    _, lab = cv2.connectedComponents(cand, connectivity=4)
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    bg = np.isin(lab, edge[edge != 0])
    # the object is the largest non-background blob; flares and stray specks become background too
    n2, lab2, stats, _ = cv2.connectedComponentsWithStats((~bg).astype(np.uint8), connectivity=8)
    if n2 > 2:
        bg = lab2 != 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    soft = np.clip((dom - 0.04) / 0.22, 0, 1)                      # 0 = object colour, 1 = clearly key colour
    if sat_min:
        soft = soft * np.clip((sat - (sat_min - 0.15)) / 0.15, 0, 1)
    near = cv2.dilate(bg.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    alpha = np.where(bg, 0.0, np.where(near, 1 - soft, 1.0)).astype(np.float32)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.8)
    alpha[bg & (cv2.erode(bg.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)] = 0
    # despill: the screen also tints the edges and the underside of the object
    if key == "blue":
        f[..., 0] = np.minimum(kc, f[..., 1] * 1.08 + 0.02)       # nothing keyed on blue is bluer than it is green
    else:
        f[..., 1] = np.minimum(kc, np.maximum(oth[0], oth[1]) * 1.02 + 0.02)
    # key-coloured holes fully inside the object (the hole in a handle) are see-through as well
    hole = (dom > 0.25) & (sat > sat_min) & ~bg
    alpha = alpha * (1 - cv2.GaussianBlur(hole.astype(np.float32), (0, 0), 1.0))
    ys, xs = np.where(alpha > 0.5)
    out = np.dstack([f, alpha])
    return (out * 255).round().astype(np.uint8), (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)


def diff_matte(bgr, key="blue"):
    """Cut-out for shiny things (metal, glass) that mirror the screen colour: the plain screen is estimated behind the
    object from the screen around it, and whatever differs from that estimate is the object, whatever colour it has."""
    f = bgr.astype(np.float32) / 255
    ki = 0 if key == "blue" else 1
    oth = [f[..., c] for c in range(3) if c != ki]
    dom = f[..., ki] - np.maximum(oth[0], oth[1])
    _, lab = cv2.connectedComponents((dom > 0.10).astype(np.uint8), connectivity=4)
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    bg0 = np.isin(lab, edge[edge != 0])
    sure_bg = cv2.erode(bg0.astype(np.uint8), np.ones((41, 41), np.uint8)) > 0       # screen, well away from the object
    small = cv2.resize(bgr, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    hole = cv2.resize((~sure_bg).astype(np.uint8) * 255, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
    est = cv2.inpaint(small, hole, 9, cv2.INPAINT_TELEA)
    est = cv2.GaussianBlur(cv2.resize(est, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_CUBIC), (0, 0), 6).astype(np.float32) / 255
    dist = np.sqrt(((f - est) ** 2).sum(2))
    # only next to what the plain chroma key already found: this adds back the mirrored rim, not far-away screen noise
    base = key_out(bgr, key)[0][..., 3] > 127
    near = cv2.dilate(base.astype(np.uint8), np.ones((31, 31), np.uint8)) > 0
    fg = (base | ((dist > 0.17) & near & ~sure_bg)).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab2, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    obj = lab2 == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    obj = cv2.morphologyEx(obj.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8)) > 0
    inner = cv2.erode(obj.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    alpha = np.where(inner, 1.0, np.where(obj, np.clip((dist - 0.05) / 0.10, 0, 1), 0.0)).astype(np.float32)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.8)
    # despill: neutralise the screen colour the object mirrors
    if key == "blue":
        f[..., 0] = np.minimum(f[..., 0], f[..., 1] * 1.08 + 0.02)
    else:
        f[..., 1] = np.minimum(f[..., 1], np.maximum(f[..., 0], f[..., 2]) * 1.02 + 0.02)
    ys, xs = np.where(alpha > 0.5)
    out = np.dstack([f, alpha])
    return (out * 255).round().astype(np.uint8), (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)


def fit(bgra, bbox, box):
    """Place the cut-out object into `box`, centred, bottom-aligned."""
    x0, y0, x1, y1 = bbox
    obj = bgra[y0:y1, x0:x1].astype(np.float32)
    obj[..., :3] *= obj[..., 3:] / 255                       # premultiply so resizing does not pull in fringe colour
    bw, bh = (box[2] - box[0]) * K, (box[3] - box[1]) * K
    sc = min(bw / obj.shape[1], bh / obj.shape[0])
    w, h = max(1, round(obj.shape[1] * sc)), max(1, round(obj.shape[0] * sc))
    obj = cv2.resize(obj, (w, h), interpolation=cv2.INTER_AREA if sc < 1 else cv2.INTER_CUBIC)
    canvas = np.zeros((SIZE, SIZE, 4), np.float32)
    ox, oy = round(box[0] * K + (bw - w) / 2), round(box[3] * K - h)
    canvas[oy:oy + h, ox:ox + w] = obj
    a = np.maximum(canvas[..., 3:], 1e-3)
    canvas[..., :3] = np.clip(canvas[..., :3] / a * 255, 0, 255)
    return canvas.round().astype(np.uint8)


def ring(img, cx, cy, rx, ry):
    """Dashed yellow highlight ring with a white edge (the "touch your nose" marker)."""
    big = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
    k = K * 2
    for colour, width in (((255, 255, 255, 255), 11), ((63, 210, 255, 255), 7)):
        for a in range(0, 360, 30):
            cv2.ellipse(big, (round(cx * k), round(cy * k)), (round(rx * k), round(ry * k)), 0, a, a + 19, colour, round(width * k / 4 * 1.0), cv2.LINE_AA)
    return cv2.resize(big, (SIZE, SIZE), interpolation=cv2.INTER_AREA)


def tone(img, t):
    """Colour grade a cut-out (BGRA). t: {"mul": [r, g, b], "sat": 1.0, "gamma": 1.0} -- a soaked sock goes darker and
    cooler ({"mul": [0.62, 0.72, 0.95], "gamma": 1.25}), a dry one brighter and warmer."""
    bgr = img[..., :3].astype(np.float32) / 255
    if t.get("sat", 1) != 1:
        grey = bgr.mean(axis=2, keepdims=True)
        bgr = grey + (bgr - grey) * t["sat"]
    bgr = np.clip(bgr, 0, 1) ** t.get("gamma", 1)
    r, g, b = t.get("mul", [1, 1, 1])
    bgr = np.clip(bgr * np.array([b, g, r], np.float32), 0, 1)
    return np.dstack([(bgr * 255).round().astype(np.uint8), img[..., 3]])


def sparkle(img, stars):
    """Small four-point shine stars (white with a warm edge): "clean / dry / new". stars: [[x, y, size], ...]."""
    out = img.astype(np.float32)
    h, w = img.shape[:2]
    for x, y, r in stars:
        m = np.zeros((h, w), np.float32)
        c, rr = (round(x * K), round(y * K)), r * K
        pts = [(c[0], c[1] - rr), (c[0] + rr * .22, c[1] - rr * .22), (c[0] + rr, c[1]), (c[0] + rr * .22, c[1] + rr * .22),
               (c[0], c[1] + rr), (c[0] - rr * .22, c[1] + rr * .22), (c[0] - rr, c[1]), (c[0] - rr * .22, c[1] - rr * .22)]
        cv2.fillPoly(m, [np.array(pts, np.int32)], 1.0, cv2.LINE_AA)
        edge = np.clip(cv2.GaussianBlur(m, (0, 0), rr * .18) * 1.6, 0, 1)
        for colour, mask in (((40, 200, 255), edge), ((255, 255, 255), m)):
            out[..., :3] = out[..., :3] * (1 - mask[..., None]) + np.array(colour, np.float32) * mask[..., None]
            out[..., 3] = np.maximum(out[..., 3], mask * 255)
    return out.round().astype(np.uint8)


def spot(img, parts):
    """Spotlight: everything outside the ellipses goes grey and dim, the parts keep their colour and get a warm glow
    around their outline (a body part the child should look at: "Touch your hands!"). parts: [[cx, cy, rx, ry], ...]."""
    h, w = img.shape[:2]
    m = np.zeros((h, w), np.float32)
    for cx, cy, rx, ry in parts:
        cv2.ellipse(m, (round(cx * K), round(cy * K)), (round(rx * K), round(ry * K)), 0, 0, 360, 1.0, -1, cv2.LINE_AA)
    m = cv2.GaussianBlur(m, (0, 0), 3 * K)
    bgr, a = img[:, :, :3].astype(np.float32), img[:, :, 3].astype(np.float32) / 255
    grey = cv2.cvtColor(cv2.cvtColor(bgr.astype(np.uint8), cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR).astype(np.float32)
    dim = bgr * 0.3 + (grey * 0.6 + 75) * 0.7           # mostly grey and lighter: the part stands out in colour
    out = bgr * m[..., None] + dim * (1 - m[..., None])
    part = a * (m > 0.5)                                  # the part's own silhouette
    halo = cv2.GaussianBlur(cv2.dilate(part, np.ones((round(5 * K), round(5 * K)), np.uint8)), (0, 0), 2.5 * K)
    halo = np.clip(halo * 1.8, 0, 1) * (1 - np.clip(part * 1.5, 0, 1))   # a ring around the part, not over it
    glow = np.array([40, 205, 255], np.float32)           # warm yellow (BGR)
    out = out * (1 - halo[..., None]) + glow * halo[..., None]
    alpha = np.maximum(a, halo)
    res = np.dstack([np.clip(out, 0, 255), alpha * 255]).astype(np.uint8)
    return res


def erase(img, cx, cy, rx, ry):
    """Paint the area over with the surrounding colour (Fenlo's portrait without a nose)."""
    mask = np.zeros(img.shape[:2], np.uint8)
    cv2.ellipse(mask, (round(cx * K), round(cy * K)), (round(rx * K), round(ry * K)), 0, 0, 360, 255, -1)
    out = img.copy()
    out[..., :3] = cv2.inpaint(np.ascontiguousarray(img[..., :3]), mask, 9, cv2.INPAINT_TELEA)
    soft = cv2.GaussianBlur(mask, (0, 0), 3)[..., None] / 255.0
    blur = cv2.GaussianBlur(out[..., :3], (0, 0), 5)
    out[..., :3] = (out[..., :3] * (1 - soft) + blur * soft).round().astype(np.uint8)
    return out


def front_part(img, cx, cy, rx, ry):
    """The part of a cover in front of the things inside it: everything below the front rim of its opening,
    given as the lower half of the ellipse (cx, cy, rx, ry)."""
    ys, xs = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    u = np.clip((xs - cx * K) / (rx * K), -1, 1)
    rim = cy * K + ry * K * np.sqrt(1 - u * u)
    m = np.clip((ys - rim) / 2.0 + 0.5, 0, 1)
    out = img.copy()
    out[..., 3] = (img[..., 3] * m).round().astype(np.uint8)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force, only = "--force" in sys.argv, set(args)
    raw = SKIN / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    spec = json.loads((SKIN / "prompts.json").read_text(encoding="utf-8"))
    man = {"items": {}, "covers": {}, "bg": {}}
    jobs = [("items", k, v) for k, v in spec.get("items", {}).items()] + [("covers", k, v) for k, v in spec.get("covers", {}).items()]
    if "brush" in spec:
        jobs.append(("brush", "brush", spec["brush"]))
    made = {}
    for kind, name, j in sorted(jobs, key=lambda x: "from" in x[2]):       # base sprites first, derived ones after
        dst = SKIN / f"{name}.png"
        if "from" in j:
            if j["from"] not in made:
                continue
            img = made[j["from"]].copy()
            if "erase" in j:
                img = erase(img, *j["erase"])
            if "glow" in j:
                img = ring(img, *j["glow"])
            if "spot" in j:
                img = spot(img, j["spot"])
        else:
            src = raw / f"{name}.png"
            if "video" in j or "anim" in j:       # animated item (tools/make_anim.py): its still is raw/<name>_cut.png
                src = raw / f"{name}_cut.png"
            if (force or not src.exists()) and (not only or name in only) and "--offline" not in sys.argv:
                key = j.get("key", "blue")
                generate(f"{j['prompt']}. {STYLES[j.get('style', 'object')]}{ISOLATE.format(key=key)}", 1024, 1024, j.get("seed", 1), src)
                print(f"  generated {name}", flush=True)
            if not src.exists():
                continue
            cut = raw / f"{name}_cut.png"                         # hand-made cut-out (transparent PNG): used as it is
            raw_img = cv2.imread(str(cut if cut.exists() else src), cv2.IMREAD_UNCHANGED)
            if j.get("rot180"):                                   # generated pointing the wrong way round
                raw_img = cv2.rotate(raw_img, cv2.ROTATE_180)
            if raw_img.ndim == 3 and raw_img.shape[2] == 4 and raw_img[..., 3].min() < 250:
                ys, xs = np.where(raw_img[..., 3] > 127)
                bgra, bbox = raw_img, (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
            elif j.get("matte") == "diff":
                bgra, bbox = diff_matte(raw_img[..., :3], j.get("key", "blue"))
            else:
                bgra, bbox = key_out(raw_img[..., :3], j.get("key", "blue"), j.get("keySat", 0.0))
            img = fit(bgra, bbox, j.get("box", [10, 10, 190, 190]))
        if "tone" in j:
            img = tone(img, j["tone"])
        if "sparkle" in j:
            img = sparkle(img, j["sparkle"])
        made[name] = img
        cv2.imwrite(str(dst), img)
        if kind == "brush":
            man["brush"] = f"{name}.png"
            continue
        entry = {"src": f"{name}.png"}
        for k in ("focus", "noShadow", "anim"):
            if k in j:
                entry[k] = j[k]
        if "front" in j:
            fr = j["front"]
            cv2.imwrite(str(SKIN / f"{name}_front.png"), front_part(img, fr["cx"], fr["cy"], fr["rx"], fr["ry"]))
            entry["front"] = f"{name}_front.png"
        man[kind][name] = entry
    for name, j in spec.get("bg", {}).items():
        src, dst = raw / f"bg_{name}.png", SKIN / f"bg_{name}.jpg"
        if (force or not src.exists()) and (not only or f"bg_{name}" in only) and "--offline" not in sys.argv:
            generate(f"{j['prompt']}. {BG_STYLE}", 1664, 928, j.get("seed", 1), src)
            print(f"  generated bg_{name}", flush=True)
        if src.exists():
            im = cv2.imread(str(src))
            if j.get("blur"):
                im = cv2.GaussianBlur(im, (0, 0), j["blur"])
            if j.get("wash"):                                   # lift a dark backdrop towards white so words stay readable
                im = (im * (1 - j["wash"]) + 255 * j["wash"]).round().astype(np.uint8)
            cv2.imwrite(str(dst), im, [cv2.IMWRITE_JPEG_QUALITY, 93])
            man["bg"][name] = {"src": f"bg_{name}.jpg", "ground": j.get("ground", 548)}
    (SKIN / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    print(f"manifest: {len(man['items'])} items, {len(man['covers'])} covers, {len(man['bg'])} backdrops")
    if "--sheet" in sys.argv:
        sheet(man, only)


def sheet(man, only):
    """Contact sheets on a checkerboard (assets/skin/sheet_N.jpg) to check cut-outs and colours by eye."""
    names = [n for n in list(man["items"]) + list(man["covers"]) + [f"{c}_front" for c, e in man["covers"].items() if "front" in e]
             + (["brush"] if "brush" in man else []) if not only or n in only or n.replace("_front", "") in only]
    cell, per = 300, 12
    chk = np.full((cell, cell, 3), 235, np.uint8)
    chk[(np.indices((cell, cell)).sum(0) // 25) % 2 == 0] = (90, 90, 90)
    for old in SKIN.glob("sheet_*.jpg"):
        old.unlink()
    for p in range(0, len(names), per):
        tiles = []
        for n in names[p:p + per]:
            im = cv2.resize(cv2.imread(str(SKIN / f"{n}.png"), cv2.IMREAD_UNCHANGED), (cell, cell), interpolation=cv2.INTER_AREA)
            a = im[..., 3:] / 255.0
            t = (im[..., :3] * a + chk * (1 - a)).astype(np.uint8)
            for g in range(50, 200, 50):                       # grid every 50 engine units, to read coordinates off
                q = round(g * cell / 200)
                t[q, ::4] = (255, 0, 255); t[::4, q] = (255, 0, 255)
            cv2.putText(t, n, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(t, n, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
            tiles.append(t)
        while len(tiles) % 4:
            tiles.append(np.zeros_like(chk))
        rows = [np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]
        out = SKIN / f"sheet_{p // per + 1}.jpg"
        cv2.imwrite(str(out), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
        print(f"sheet: {out}")


if __name__ == "__main__":
    main()
