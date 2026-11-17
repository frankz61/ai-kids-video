"""Clapping-hands animation built by hand from one picture of two hands held apart: both hands are always on
screen, they only move together and apart (a video model made one hand turn away and vanish).

Usage: python tools/make_clap.py [--force]
Reads  assets/skin/prompts.json items["hands_clap"]["clap"] = {"prompt": ..., "seed": 1, "key": "green", "frames": 20, "fps": 12}
Writes raw/hands_apart.png (as generated), hands_clap_anim.png (sprite sheet), raw/hands_clap_cut.png (still), and
items["hands_clap"]["anim"].  Then run `python tools/make_skin.py --offline`.
"""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_skin import ISOLATE, SKIN, STYLES, key_out  # noqa: E402

URL = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
NAME = "hands_clap"


def main():
    p = SKIN / "prompts.json"
    spec = json.loads(p.read_text(encoding="utf-8"))
    j = spec["items"][NAME]
    c = j["clap"]
    src = SKIN / "raw" / "hands_apart.png"
    if "--force" in sys.argv or not src.exists():
        import h3_client as h3
        key = c.get("key", "green")
        text = f"{c['prompt']}. {STYLES['object']}{ISOLATE.format(key=key)}"
        models = h3.api_get(URL, "/object_info/UNETLoader")["UNETLoader"]["input"]["required"]["unet_name"][0]
        build = h3.build_t2i_workflow if any("qwen_image" in m for m in models) else h3.build_h3_image_workflow   # whichever is deployed
        wf = build(text, 1024, 1024, c.get("seed", 1), "skin_hands_apart")
        h3.download_output(URL, h3.queue_and_wait(URL, wf, output_node="11"), src)
        print("  generated hands_apart.png", flush=True)
    img = cv2.imread(str(src))
    img = cv2.resize(img, (1024, 1024), interpolation=cv2.INTER_AREA)
    # key each hand on its own: the two largest blobs
    f = img.astype(np.float32) / 255
    ki = 0 if c.get("key", "green") == "blue" else 1
    oth = [f[..., k] for k in range(3) if k != ki]
    dom = f[..., ki] - np.maximum(oth[0], oth[1])
    sat = (f[..., ki] - np.minimum(oth[0], oth[1])) / np.maximum(f[..., ki], 1e-3)
    fg = (~((dom > 0.03) & (sat > 0.45))).astype(np.uint8)        # 0.03: the dark shadow on the screen is screen too
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(fg, connectivity=8)
    big = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])[:2]
    assert len(big) == 2, "need two separate hands in the picture"
    big.sort(key=lambda i: cent[i][0])                      # left hand, right hand
    hands = []
    for i in big:
        m = (lab == i).astype(np.float32)
        a = cv2.GaussianBlur(m, (0, 0), 1.0)
        a = np.clip((a - 0.35) / 0.5, 0, 1)
        col = f.copy()
        if ki == 1:
            col[..., 1] = np.minimum(col[..., 1], np.maximum(col[..., 0], col[..., 2]) * 1.02 + 0.02)
        else:
            col[..., 0] = np.minimum(col[..., 0], col[..., 1] * 1.08 + 0.02)
        hands.append((np.dstack([col * a[..., None], a]), stats[i]))          # premultiplied
    (lh, ls), (rh, rs) = hands
    gap = rs[cv2.CC_STAT_LEFT] - (ls[cv2.CC_STAT_LEFT] + ls[cv2.CC_STAT_WIDTH])     # px between the hands
    size, n_fr, cell = 1024, c.get("frames", 20), c.get("cell", 320)
    cols = int(np.ceil(np.sqrt(n_fr)))
    rows = int(np.ceil(n_fr / cols))
    sheet = np.zeros((rows * cell, cols * cell, 4), np.uint8)
    cx = (ls[cv2.CC_STAT_LEFT] + rs[cv2.CC_STAT_LEFT] + rs[cv2.CC_STAT_WIDTH]) / 2
    cy = min(ls[cv2.CC_STAT_TOP], rs[cv2.CC_STAT_TOP]) + max(ls[cv2.CC_STAT_HEIGHT], rs[cv2.CC_STAT_HEIGHT]) / 2
    span = max(rs[cv2.CC_STAT_LEFT] + rs[cv2.CC_STAT_WIDTH] - ls[cv2.CC_STAT_LEFT], max(ls[cv2.CC_STAT_HEIGHT], rs[cv2.CC_STAT_HEIGHT])) * 1.12
    swing = c.get("open", 90)                                  # extra px each hand swings outwards when apart
    span += 2 * swing + 460
    for k in range(n_fr):
        u = k / n_fr                                         # one clap per loop: apart -> together (quick) -> apart (slower)
        close = np.sin(np.pi * min(u / 0.35, 1) / 2) ** 2 if u < 0.35 else np.cos(np.pi * (u - 0.35) / 0.65 / 2) ** 2
        hold = 1.0 if 0.30 < u < 0.45 else close             # stay together for a moment
        d = (gap / 2 + 14) * hold                            # +14 px: the palms press into each other a little
        canvas = np.zeros((size, size, 4), np.float32)
        for hand, st, sgn in ((lh, ls, 1), (rh, rs, -1)):
            hx, hy = st[cv2.CC_STAT_LEFT] + st[cv2.CC_STAT_WIDTH] / 2, st[cv2.CC_STAT_TOP] + st[cv2.CC_STAT_HEIGHT]
            M = cv2.getRotationMatrix2D((float(hx), float(hy)), float(sgn * c.get("tilt", 14) * (1 - hold)), 1.0)     # tilt outwards when apart
            M[0, 2] += sgn * d - sgn * swing * (1 - hold)       # apart: swung outwards; together: palms pressed
            w = cv2.warpAffine(hand, M, (size, size), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            canvas = w + canvas * (1 - w[..., 3:])
        x0, y0 = int(cx - span / 2), int(cy - span / 2)
        pad = cv2.copyMakeBorder(canvas, 600, 600, 600, 600, cv2.BORDER_CONSTANT, value=0)
        crop = pad[y0 + 600:y0 + 600 + int(span), x0 + 600:x0 + 600 + int(span)]
        small = cv2.resize(crop, (cell, cell), interpolation=cv2.INTER_AREA)
        al = np.maximum(small[..., 3:], 1e-3)
        out = np.dstack([np.clip(small[..., :3] / al, 0, 1), small[..., 3]])
        out = (out * 255).round().astype(np.uint8)
        sheet[(k // cols) * cell:(k // cols + 1) * cell, (k % cols) * cell:(k % cols + 1) * cell] = out
        if k == 0:
            big_al = np.maximum(crop[..., 3:], 1e-3)
            cv2.imwrite(str(SKIN / "raw" / f"{NAME}_cut.png"), (np.dstack([np.clip(crop[..., :3] / big_al, 0, 1), crop[..., 3]]) * 255).round().astype(np.uint8))
    cv2.imwrite(str(SKIN / f"{NAME}_anim.png"), sheet)
    j.pop("video", None)
    j["anim"] = {"sheet": f"{NAME}_anim.png", "cols": cols, "rows": rows, "n": n_fr, "fps": c.get("fps", 12), "zoom": c.get("zoom", 1.1)}
    j["box"] = [0, 0, 200, 200]
    p.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    strip = []
    for k in range(0, n_fr, max(1, n_fr // 8)):
        t = sheet[(k // cols) * cell:(k // cols + 1) * cell, (k % cols) * cell:(k % cols + 1) * cell]
        a = t[..., 3:] / 255.0
        strip.append((t[..., :3] * a + np.full((cell, cell, 3), (60, 150, 60), np.uint8) * (1 - a)).astype(np.uint8))
    cv2.imwrite(str(SKIN / f"anim_{NAME}_check.jpg"), np.hstack(strip[:8]))
    print(f"  {n_fr} frames, gap {gap}px -> {NAME}_anim.png")


if __name__ == "__main__":
    main()
