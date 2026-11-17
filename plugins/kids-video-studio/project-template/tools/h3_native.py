"""MiniMax H3 image-to-video batch runner for ComfyUI builds that ship the *native* H3 nodes
(MiniMaxH3ImageToVideo / SamplerCustomAdvanced / CreateVideo / SaveVideo).

The skill's h3_client.py targets the older custom-node pack (MiniMaxH3FirstLastFrameToVideo),
which the currently deployed service does not have. Graph below mirrors the server's own
video_minimax_h3_t2v.json template with the Lightning LoRA enabled.

Usage:
  python h3_native.py --prompts-json prompts.json --frames-dir frames --output-dir clips [--only 1 2] [--overwrite]
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import h3_client as h3  # noqa: E402


def build_workflow(first_frame, prompt, width, height, length, seed, steps, prefix):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["1", 0], "lora_name": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
            "strength_model": 1.0}},
        "3": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen3vl_32b_minimax_h3_int8_convrot.safetensors", "type": "minimax", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_int8_convrot.safetensors"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "6": {"class_type": "LoadImage", "inputs": {"image": first_frame}},
        "7": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {
            "clip": ["3", 0], "vae": ["4", 0], "prompt": prompt,
            "width": width, "height": height, "length": length, "first_frame": ["6", 0]}},
        "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "10": {"class_type": "BasicScheduler", "inputs": {
            "model": ["2", 0], "scheduler": "simple", "steps": steps, "denoise": 1.0}},
        "11": {"class_type": "BasicGuider", "inputs": {"model": ["2", 0], "conditioning": ["7", 0]}},
        "12": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["8", 0], "guider": ["11", 0], "sampler": ["9", 0], "sigmas": ["10", 0],
            "latent_image": ["7", 1]}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}},
        "14": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["12", 0], "vae": ["5", 0]}},
        "15": {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "audio": ["14", 0], "fps": 24.0}},
        "16": {"class_type": "SaveVideo", "inputs": {
            "video": ["15", 0], "filename_prefix": f"video/{prefix}", "format": "auto", "codec": "auto"}},
    }


def post(url, path, payload):
    req = urllib.request.Request(f"{url}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:2000]}") from None


def wait_video(url, prompt_id):
    while True:
        try:
            hist = h3.api_get(url, f"/history/{prompt_id}", timeout=15)
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            print(f"  [WARN] poll error ({e}), retrying", flush=True)
            time.sleep(5)
            continue
        if prompt_id in hist:
            entry = hist[prompt_id]
            if entry.get("status", {}).get("status_str") == "error":
                raise RuntimeError("ComfyUI error: " + json.dumps(entry["status"])[:3000])
            for out in entry.get("outputs", {}).values():
                for items in out.values():
                    if isinstance(items, list):
                        for it in items:
                            if isinstance(it, dict) and str(it.get("filename", "")).endswith((".mp4", ".webm")):
                                return it
            raise RuntimeError("no video in outputs: " + json.dumps(entry.get("outputs"))[:2000])
        time.sleep(4)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8188")
    p.add_argument("--prompts-json", required=True)
    p.add_argument("--frames-dir", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=736)
    p.add_argument("--length", type=int, default=124, help="frames on the 17k+5 grid (124 = 5.17s)")
    p.add_argument("--steps", type=int, default=8)
    p.add_argument("--seed", type=int, default=1000)
    p.add_argument("--only", type=int, nargs="*")
    p.add_argument("--overwrite", action="store_true")
    a = p.parse_args()
    url = a.url.rstrip("/")

    data = json.loads(Path(a.prompts_json).read_text(encoding="utf-8"))
    out_dir = Path(a.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for shot in data["shots"]:
        sid = shot["id"]
        if a.only and sid not in a.only:
            continue
        dest = out_dir / f"shot_{sid:02d}.mp4"
        if dest.exists() and dest.stat().st_size > 10000 and not a.overwrite:
            print(f"[SKIP] shot {sid:02d}", flush=True)
            continue
        t0 = time.time()
        uploaded = h3.upload_image(url, Path(a.frames_dir) / shot["first_frame"], f"ep_shot_{sid:02d}.png")
        seed = shot.get("video_seed", a.seed + sid)
        wf = build_workflow(uploaded, shot["prompt_en"], a.width, a.height, a.length, seed, a.steps, f"shot_{sid:02d}")
        pid = post(url, "/prompt", {"prompt": wf})["prompt_id"]
        print(f"[SHOT {sid:02d}] queued {pid} seed={seed}", flush=True)
        info = wait_video(url, pid)
        h3.download_output(url, info, dest)
        print(f"[DONE] shot {sid:02d} -> {dest} in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
