"""Turn a skin sprite into a short looping animation (a real moving rabbit / dog) with MiniMax H3 image-to-video.

Usage: python tools/make_anim.py <name> [--force] [--offline]
Reads  assets/skin/prompts.json  items[<name>]["video"]:
  {"from": "rabbit_jump",            # sprite (assets/skin/<from>.png) placed on a flat colour screen as the first frame
   "prompt": "The rabbit hops ...",  # what moves; the camera and the plain background must stay still
   "seed": 1, "key": "blue", "keySat": 0.5,
   "place": [0.5, 0.86, 0.5],        # sprite centre x, bottom y, height, as fractions of the 1280x736 frame
   "frames": 56,                     # clip length (17k+5); the first frame is also given as the last frame, so it loops
   "loop": [0, 55],                  # optional: first / last frame of the loop (default: the whole clip)
   "step": 2, "cell": 320}           # use every 2nd frame (12 fps), sheet cell size in px
Writes assets/skin/raw/anim_<name>.mp4 (as generated), assets/skin/<name>_anim.png (sprite sheet, cut out),
raw/<name>_cut.png (one frame, the still picture used on covers), and items[<name>]["anim"] in prompts.json.
Then run `python tools/make_skin.py --offline` to refresh manifest.json.
"""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_skin import SKIN, key_out  # noqa: E402

URL = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
W, H = 1280, 736
SCREEN = {"blue": (214, 80, 28), "green": (60, 190, 40)}          # BGR
STILL = ("Static locked-off camera, no camera movement, no zoom. The plain flat solid {key} background stays exactly the same, "
         "empty and unchanged, no floor, no shadow, no other objects. Pixar-style 3D cartoon animation. No speech, no music.")


def first_frame(v, dest):
    spr = cv2.imread(str(SKIN / f"{v['from']}.png"), cv2.IMREAD_UNCHANGED)
    ys, xs = np.where(spr[..., 3] > 127)
    spr = spr[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)
    cx, by, hh = v.get("place", [0.5, 0.8, 0.5])
    sc = hh * H / spr.shape[0]
    spr = cv2.resize(spr, (round(spr.shape[1] * sc), round(spr.shape[0] * sc)), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((H, W, 3), np.float32)
    canvas[:] = SCREEN[v.get("key", "blue")]
    x0, y0 = round(cx * W - spr.shape[1] / 2), round(by * H - spr.shape[0])
    a = spr[..., 3:] / 255
    canvas[y0:y0 + spr.shape[0], x0:x0 + spr.shape[1]] = spr[..., :3] * a + canvas[y0:y0 + spr.shape[0], x0:x0 + spr.shape[1]] * (1 - a)
    cv2.imwrite(str(dest), canvas.round().astype(np.uint8))


def generate(name, v, mp4):
    import h3_client as h3
    ff = SKIN / "raw" / f"anim_{name}_first.png"
    first_frame(v, ff)
    up = h3.upload_image(URL, ff, f"anim_{name}_first.png")
    wf = h3.build_h3_workflow(up, f"{v['prompt']} {STILL.format(key=v.get('key', 'blue'))}", "quant", W, H, v.get("frames", 56), v.get("seed", 1), f"anim_{name}",
                               last_frame_name=up)       # same first and last frame: the background cannot drift, and the clip loops
    info = h3.queue_and_wait(URL, wf, output_node="16")
    h3.download_output(URL, info, mp4)


def find_loop(thumbs, lo=16, hi=80, skip=6):
    """Pair of frames (a, b) that look most alike, b - a in [lo, hi]: playing a..b-1 on repeat has the smallest jump."""
    best = None
    for a in range(skip, len(thumbs) - lo):
        for b in range(a + lo, min(len(thumbs), a + hi + 1)):
            d = float(np.abs(thumbs[a] - thumbs[b]).mean()) - 0.02 * (b - a) / hi      # slightly prefer longer loops
            if best is None or d < best[0]:
                best = (d, a, b)
    return best[1], best[2]


def main():
    name = [a for a in sys.argv[1:] if not a.startswith("--")][0]
    p = SKIN / "prompts.json"
    spec = json.loads(p.read_text(encoding="utf-8"))
    j = spec["items"][name]
    v = j["video"]
    mp4 = SKIN / "raw" / f"anim_{name}.mp4"
    if ("--force" in sys.argv or not mp4.exists()) and "--offline" not in sys.argv:
        generate(name, v, mp4)
        print(f"  generated {mp4.name}", flush=True)
    cap = cv2.VideoCapture(str(mp4))
    frames = []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        frames.append(key_out(fr, v.get("key", "blue"), v.get("keySat", 0.0))[0])
    print(f"  {len(frames)} frames keyed", flush=True)
    thumbs = [cv2.resize(f[..., 3], (80, 46), interpolation=cv2.INTER_AREA).astype(np.float32) / 255 for f in frames]
    a, b = v["loop"] if "loop" in v else (0, len(frames) - 1)       # first frame == last frame, so the whole clip is the loop
    step = v.get("step", 2)
    sel = frames[a:b:step]
    # one fixed square window around everything the subject touches during the loop, so its movement is kept
    union = np.max([f[..., 3] for f in sel], axis=0) > 100
    ys, xs = np.where(union)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    side = max(x1 - x0, y1 - y0) + 12
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    sx, sy = cx - side // 2, cy - side // 2
    cell = v.get("cell", 320)
    cols = int(np.ceil(np.sqrt(len(sel))))
    rows = int(np.ceil(len(sel) / cols))
    sheet = np.zeros((rows * cell, cols * cell, 4), np.uint8)
    for i, f in enumerate(sel):
        pad = cv2.copyMakeBorder(f, side, side, side, side, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
        crop = pad[sy + side:sy + 2 * side, sx + side:sx + 2 * side].astype(np.float32)
        crop[..., :3] *= crop[..., 3:] / 255
        small = cv2.resize(crop, (cell, cell), interpolation=cv2.INTER_AREA)
        al = np.maximum(small[..., 3:], 1e-3)
        small[..., :3] = np.clip(small[..., :3] / al * 255, 0, 255)
        sheet[(i // cols) * cell:(i // cols + 1) * cell, (i % cols) * cell:(i % cols + 1) * cell] = small.round().astype(np.uint8)
        if i == v.get("still", 0):
            cv2.imwrite(str(SKIN / "raw" / f"{name}_cut.png"), pad[sy + side:sy + 2 * side, sx + side:sx + 2 * side])
    cv2.imwrite(str(SKIN / f"{name}_anim.png"), sheet)
    j["anim"] = {"sheet": f"{name}_anim.png", "cols": cols, "rows": rows, "n": len(sel), "fps": v.get("fps", round(24 / step)), "zoom": v.get("zoom", 1)}      # fps below 24 / step = slow motion
    j["box"] = [0, 0, 200, 200]
    p.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    print(f"  loop frames {a}..{b} step {step}: {len(sel)} frames, {cols}x{rows} sheet, window {side}px -> {name}_anim.png")
    # a strip of every few frames to check by eye
    pick = sel[::max(1, len(sel) // 8)][:8]
    strip = []
    for f in pick:
        pad = cv2.copyMakeBorder(f, side, side, side, side, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
        c = cv2.resize(pad[sy + side:sy + 2 * side, sx + side:sx + 2 * side], (240, 240), interpolation=cv2.INTER_AREA)
        al = c[..., 3:] / 255.0
        bg = np.full((240, 240, 3), (60, 150, 60), np.uint8)
        strip.append((c[..., :3] * al + bg * (1 - al)).astype(np.uint8))
    cv2.imwrite(str(SKIN / f"anim_{name}_check.jpg"), np.hstack(strip))


if __name__ == "__main__":
    main()
