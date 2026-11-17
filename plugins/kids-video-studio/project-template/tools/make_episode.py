"""Run the production steps for one episode.

Usage: python tools/make_episode.py <episode_dir> [step ...]
Steps (default: all, in this order):
  frames    Qwen-Image first frames for h3/prompts.json            -> h3/frames/shot_NN.png
  clips     MiniMax H3 image-to-video                              -> h3/clips/shot_NN.mp4
  upscale   RelayVSR x2 -> 1920x1080                               -> h3/clips_1080p/shot_NN.mp4
  tts       voice lines via the season cache (ElevenLabs)          -> audio/tts, h5/durations.js, h5/episode.js
  capture   H5 scenes at 1080p                                     -> build/h5/*.mp4 + timeline.json
  assemble  final video, no-subtitle copy, .srt                    -> output/
  check     A/V sync + subtitle frame sheet                        -> build/check_*.jpg
Shots listed with "reuse" in prompts.json are skipped by frames/clips/upscale (review episodes reuse earlier clips).
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from season_lib import ROOT, episode_tts, load_episode, run  # noqa: E402

H3 = ROOT / "tools"
sys.path.insert(0, str(H3))
URL = "http://127.0.0.1:8188"
STEPS = ["frames", "clips", "upscale", "tts", "capture", "assemble", "check"]
CHARACTER = ("Fenlo, a cute chubby baby fox cub with bright orange fur, a white muzzle, white belly and a white tail tip, "
             "big round brown eyes, small black nose, wearing a cream-white knitted scarf around his neck")
STYLE = ("Pixar-style 3D cartoon render, soft warm lighting, clean simple shapes, children's animation film still, "
         "wide 16:9 shot, no text, no letters, no watermark")


def shots(ep):
    p = ep / "h3" / "prompts.json"
    return [s for s in json.loads(p.read_text(encoding="utf-8"))["shots"] if not s.get("reuse")] if p.exists() else []


def shot_sig(s):
    import hashlib
    blob = json.dumps([s.get("image_prompt"), s.get("prompt_en"), s.get("image_seed"), s.get("video_seed"), CHARACTER, STYLE])
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def step_frames(ep):
    import h3_client as h3
    frames = ep / "h3" / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    for s in shots(ep):
        dest = frames / f"shot_{s['id']:02d}.png"
        sig = dest.with_suffix(".sig")
        if dest.exists() and sig.exists() and sig.read_text() != shot_sig(s):
            # the shot's prompt changed: drop its frame, clip and upscaled clip so they are regenerated
            for f in (dest, ep / "h3" / "clips" / f"shot_{s['id']:02d}.mp4", ep / "h3" / "clips_1080p" / f"shot_{s['id']:02d}.mp4"):
                f.unlink(missing_ok=True)
            print(f"  prompt changed -> regenerating shot {s['id']:02d}", flush=True)
        if dest.exists():
            if not sig.exists():
                sig.write_text(shot_sig(s))
            continue
        prompt = s["image_prompt"].replace("{HERO}", CHARACTER).replace("{STYLE}", STYLE)
        wf = h3.build_t2i_workflow(prompt, 1280, 720, s.get("image_seed", 4242), f"{ep.name}_ff_{s['id']:02d}")
        info = h3.queue_and_wait(URL, wf, output_node="11")
        h3.download_output(URL, info, dest)
        sig.write_text(shot_sig(s))
        print(f"  frame {dest.name}", flush=True)


def step_clips(ep):
    if not shots(ep):
        return
    # h3_native.py reads prompts.json "first_frame"; write a filtered copy with only the new shots
    p = ep / "h3" / "prompts.json"
    spec = json.loads(p.read_text(encoding="utf-8"))
    tmp = ep / "build" / "h3_new_shots.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps({"shots": [{**s, "first_frame": f"shot_{s['id']:02d}.png"} for s in spec["shots"] if not s.get("reuse")]}),
                   encoding="utf-8")
    subprocess.run([sys.executable, "-u", ROOT / "tools" / "h3_native.py", "--prompts-json", tmp,
                    "--frames-dir", ep / "h3" / "frames", "--output-dir", ep / "h3" / "clips"], check=True, stdin=subprocess.DEVNULL)


def step_upscale(ep):
    if not shots(ep):
        return
    subprocess.run([sys.executable, "-u", H3 / "h3_client.py", "upscale", "--input", ep / "h3" / "clips",
                    "--output", ep / "h3" / "clips_1080p", "--method", "relayvsr", "--width", "1920", "--height", "1080"],
                   check=True, stdin=subprocess.DEVNULL)


def step_capture(ep):
    subprocess.run(["node", "capture.mjs", ep / "h5" / "index.html", ep / "build" / "h5", "--scale", "1.5"],
                   cwd=ROOT / "tools", check=True, stdin=subprocess.DEVNULL)


def step_assemble(ep):
    subprocess.run([sys.executable, "-u", ROOT / "tools" / "assemble_episode.py", ep], check=True, stdin=subprocess.DEVNULL)


def step_check(ep):
    spec = load_episode(ep)
    name = spec["output_name"]
    video = ep / "output" / f"{name}.mp4"
    print(run([sys.executable, ROOT / "tools" / "audio_lag.py", ep / "build" / "mix_norm.wav", video, "40"]).strip())
    print(run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,start_time,duration", "-of", "compact", video]).strip())
    picks = [ln["text"].split("] ")[-1][:14] for k, ln in list(spec["lines"].items())[:: max(1, len(spec["lines"]) // 8)]]
    run([sys.executable, ROOT / "tools" / "subs_sheet.py", video, ep / "output" / f"{name}.srt", ep / "build" / "check_subs.jpg", *picks])
    print(f"check sheet: {ep / 'build' / 'check_subs.jpg'}")


def main():
    ep = Path(sys.argv[1]).resolve()
    steps = sys.argv[2:] or STEPS
    for s in steps:
        print(f"=== {ep.name}: {s}", flush=True)
        if s == "tts":
            episode_tts(ep)
        else:
            globals()[f"step_{s}"](ep)


if __name__ == "__main__":
    main()
