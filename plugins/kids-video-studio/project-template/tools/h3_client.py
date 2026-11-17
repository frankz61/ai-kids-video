#!/usr/bin/env python3
"""
Unified Local Client for MiniMax H3 ComfyUI Service (default: http://127.0.0.1:8188)
Subcommands:
  status : Check GPU, VRAM, and queue status on the mapped local port
  i2v    : Generate 720p 24fps video + native audio from a local first-frame image
  t2v    : Generate first-frame image (Qwen-Image-2512) + MiniMax H3 video + native audio from text
  batch  : Batch-generate multi-shot storyboards from a prompts.json file
  upscale: Super-resolve an existing .mp4 video (or directory) to 1080p via RelayVSR x2 or RealESRGAN
"""
import argparse
import json
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_opener = urllib.request.build_opener()
_opener.addheaders = [("User-Agent", "Mozilla/5.0")]
urllib.request.install_opener(_opener)


def api_get(base_url: str, path: str, timeout: int = 15) -> dict:
    with urllib.request.urlopen(f"{base_url.rstrip('/')}{path}", timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def upload_image(base_url: str, filepath: Path, target_name: str | None = None) -> str:
    target = target_name or filepath.name
    ctype = b"video/mp4" if filepath.suffix.lower() == ".mp4" else b"image/png"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    data = [
        f"--{boundary}".encode(),
        f'Content-Disposition: form-data; name="image"; filename="{target}"'.encode(),
        b"Content-Type: " + ctype,
        b"",
        filepath.read_bytes(),
        f"--{boundary}".encode(),
        b'Content-Disposition: form-data; name="overwrite"',
        b"",
        b"true",
        f"--{boundary}--".encode(),
        b"",
    ]
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/upload/image",
        data=b"\r\n".join(data),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))["name"]


def build_t2i_workflow(prompt_text: str, width: int, height: int, seed: int, prefix: str) -> dict:
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "qwen_image_2512_fp8_e4m3fn.safetensors",
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["1", 0],
                "lora_name": "Qwen-Image-Lightning-4steps-V1.0.safetensors",
                "strength_model": 1.0,
            },
        },
        "3": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
                "type": "qwen_image",
                "device": "default",
            },
        },
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "5": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt_text, "clip": ["3", 0]},
        },
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["3", 0]}},
        "8": {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {"model": ["2", 0], "shift": 3.1},
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["8", 0],
                "seed": seed,
                "steps": 4,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
                "denoise": 1.0,
            },
        },
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["4", 0]}},
        "11": {
            "class_type": "SaveImage",
            "inputs": {"images": ["10", 0], "filename_prefix": prefix},
        },
    }


def build_h3_image_workflow(
    prompt_text: str,
    width: int,
    height: int,
    seed: int,
    prefix: str,
    ref_image_name: str | None = None,
) -> dict:
    # MiniMax-H3-Image works best at >= 4MP (~2048x2048 area) and multiple-of-32 dims.
    scale = max(1.0, (4194304 / max(1, width * height)) ** 0.5)
    t2i_w = max(32, round(width * scale / 32) * 32)
    t2i_h = max(32, round(height * scale / 32) * 32)
    wf = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "minimax_h3_image_pruned_int8_convrot.safetensors",
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
                "type": "minimax",
                "device": "default",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "minimax_h3_image_vae_fp16.safetensors"},
        },
        "4": {
            "class_type": "MiniMaxH3ImageConditioning",
            "inputs": {
                "clip": ["2", 0],
                "vae": ["3", 0],
                "prompt": prompt_text,
                "width": t2i_w,
                "height": t2i_h,
            },
        },
        "5": {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["4", 0]},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "seed": seed,
                "steps": 6,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["4", 1],
                "denoise": 1.0,
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        "11": {
            "class_type": "SaveImage",
            "inputs": {"images": ["7", 0], "filename_prefix": prefix},
        },
    }
    if ref_image_name:
        wf["12"] = {"class_type": "LoadImage", "inputs": {"image": ref_image_name}}
        wf["4"]["inputs"]["images.image_1"] = ["12", 0]
    return wf


def build_h3_workflow(
    first_frame_name: str,
    video_prompt: str,
    mode: str = "quant",
    width: int = 720,
    height: int = 1280,
    frames: int = 121,
    seed: int = 20261112,
    prefix: str = "minimax_h3_out",
    last_frame_name: str | None = None,
) -> dict:
    if mode == "bf16":
        unet_name = "minimax_h3_fl2va_bf16.safetensors"
        clip_name = "qwen3vl_32b_minimax_h3_bf16.safetensors"
        video_vae = "minimax_h3_video_vae_fp16.safetensors"
        steps, cfg = 20, 4.0
        model_ref = ["1", 0]
    else:
        unet_name = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
        clip_name = "qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
        video_vae = "minimax_h3_video_vae_int8_convrot.safetensors"
        steps, cfg = 8, 1.0
        model_ref = ["2", 0]

    # Native H3 nodes need width/height on a 32px grid and length on the 17k+5 frame grid.
    # Round up so the result can always be cropped back to the requested size.
    snapped = (max(32, -(-width // 32) * 32), max(32, -(-height // 32) * 32),
               max(5, frames) + (5 - max(5, frames) % 17) % 17)
    if snapped != (width, height, frames):
        print(f"  [H3] snapped {width}x{height}/{frames}f -> {snapped[0]}x{snapped[1]}/{snapped[2]}f", flush=True)
    width, height, frames = snapped

    wf = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
        },
        "3": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": clip_name, "type": "minimax", "device": "default"},
        },
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": video_vae}},
        "5": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"},
        },
        "6": {"class_type": "LoadImage", "inputs": {"image": first_frame_name}},
        "7": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {
                "clip": ["3", 0],
                "vae": ["4", 0],
                "prompt": video_prompt,
                "width": width,
                "height": height,
                "length": frames,
                "first_frame": ["6", 0],
            },
        },
        "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "10": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": model_ref,
                "scheduler": "simple",
                "steps": steps,
                "denoise": 1.0,
            },
        },
        "11": {
            "class_type": "BasicGuider",
            "inputs": {"model": model_ref, "conditioning": ["7", 0]},
        },
        "12": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["8", 0],
                "guider": ["11", 0],
                "sampler": ["9", 0],
                "sigmas": ["10", 0],
                "latent_image": ["7", 1],
            },
        },
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}},
        "14": {
            "class_type": "VAEDecodeAudio",
            "inputs": {"samples": ["12", 0], "vae": ["5", 0]},
        },
        "15": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["13", 0], "audio": ["14", 0], "fps": 24.0},
        },
        "16": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["15", 0],
                "filename_prefix": f"video/{prefix}",
                "format": "auto",
                "codec": "auto",
            },
        },
    }
    if mode != "bf16":
        wf["2"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["1", 0],
                "lora_name": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
                "strength_model": 1.0,
            },
        }
    if last_frame_name:
        wf["17"] = {"class_type": "LoadImage", "inputs": {"image": last_frame_name}}
        wf["7"]["inputs"]["last_frame"] = ["17", 0]
    return wf


def build_upscale_workflow(
    video_name: str,
    method: str = "relayvsr",
    width: int = 1920,
    height: int = 1080,
    crop: str = "center",
    detail: float = 1.0,
    esrgan_model: str = "RealESRGAN_x2plus.pth",
    seed: int = 42,
    prefix: str = "upscaled_1080p",
) -> tuple[dict, str]:
    if method == "relayvsr":
        wf = {
            "1": {"class_type": "LoadVideo", "inputs": {"file": video_name}},
            "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
            "3": {
                "class_type": "UNETLoader",
                "inputs": {
                    "unet_name": "relayvsr_x2_lightx2v_int8_convrot.safetensors",
                    "weight_dtype": "default",
                },
            },
            "4": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": "relayvsr_flash_vae_x2_fp32.safetensors"},
            },
            "5": {
                "class_type": "RelayVSRConditioning",
                "inputs": {"model": ["3", 0], "images": ["2", 0]},
            },
            "6": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["3", 0],
                    "positive": ["5", 0],
                    "negative": ["5", 0],
                    "latent_image": ["5", 1],
                    "seed": seed,
                    "steps": 1,
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                },
            },
            "7": {
                "class_type": "VSRDecode",
                "inputs": {
                    "vae": ["4", 0],
                    "samples": ["6", 0],
                    "images": ["2", 0],
                    "detail": detail,
                },
            },
            "8": {
                "class_type": "ImageScale",
                "inputs": {
                    "image": ["7", 0],
                    "upscale_method": "lanczos",
                    "width": width,
                    "height": height,
                    "crop": crop,
                },
            },
            "9": {
                "class_type": "CreateVideo",
                "inputs": {"images": ["8", 0], "audio": ["2", 1], "fps": ["2", 2]},
            },
            "10": {
                "class_type": "SaveVideo",
                "inputs": {
                    "video": ["9", 0],
                    "filename_prefix": f"video/{prefix}",
                    "format": "auto",
                    "codec": "auto",
                },
            },
        }
        return wf, "10"

    wf = {
        "1": {"class_type": "LoadVideo", "inputs": {"file": video_name}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "3": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": esrgan_model}},
        "4": {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {"upscale_model": ["3", 0], "image": ["2", 0]},
        },
        "5": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["4", 0],
                "upscale_method": "lanczos",
                "width": width,
                "height": height,
                "crop": crop,
            },
        },
        "6": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["5", 0], "audio": ["2", 1], "fps": ["2", 2]},
        },
        "7": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["6", 0],
                "filename_prefix": f"video/{prefix}",
                "format": "auto",
                "codec": "auto",
            },
        },
    }
    return wf, "7"


def queue_and_wait(base_url: str, workflow: dict, output_node: str) -> dict:
    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            prompt_id = json.loads(resp.read().decode("utf-8"))["prompt_id"]
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:2000]
        raise RuntimeError(f"ComfyUI rejected the workflow (HTTP {e.code}): {detail}") from None
    print(f"  Queued prompt_id={prompt_id}, waiting...", flush=True)
    while True:
        try:
            hist = api_get(base_url, f"/history/{prompt_id}", timeout=15)
            if prompt_id in hist:
                entry = hist[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI execution error: {json.dumps(status)}")
                outputs = entry.get("outputs", {})
                if output_node in outputs:
                    items = (
                        outputs[output_node].get("gifs", [])
                        + outputs[output_node].get("images", [])
                        + outputs[output_node].get("videos", [])
                    )
                    for item in items:
                        if output_node != "11" and not item["filename"].endswith((".mp4", ".webm")):
                            continue
                        return item
                raise RuntimeError(f"No valid output in node {output_node}: {outputs}")
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            print(f"  [WARN] transient poll error ({e}), retrying in 5s...", flush=True)
            time.sleep(5)
            continue
        time.sleep(3)


def download_output(base_url: str, file_info: dict, dest: Path):
    params = urllib.parse.urlencode(
        {
            "filename": file_info["filename"],
            "subfolder": file_info.get("subfolder", ""),
            "type": file_info.get("type", "output"),
        }
    )
    urllib.request.urlretrieve(f"{base_url.rstrip('/')}/view?{params}", dest)


def cmd_status(args):
    stats = api_get(args.url, "/system_stats")
    queue = api_get(args.url, "/queue")
    devs = stats.get("devices", [{}])
    dev = devs[0] if devs else {}
    vram_total = dev.get("vram_total", 0) / (1024**3)
    vram_free = dev.get("vram_free", 0) / (1024**3)
    print(f"Service URL : {args.url}")
    print(f"GPU Device  : {dev.get('name', 'unknown')} ({vram_free:.1f} GiB free / {vram_total:.1f} GiB total)")
    print(f"Queue       : {len(queue.get('queue_running', []))} running, {len(queue.get('queue_pending', []))} pending")


def cmd_i2v(args):
    t0 = time.time()
    first_path = Path(args.first_frame)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[1/2] Uploading first frame: {first_path.name}", flush=True)
    first_uploaded = upload_image(args.url, first_path)
    last_uploaded = upload_image(args.url, Path(args.last_frame)) if args.last_frame else None

    print(f"[2/2] Generating MiniMax H3 video ({args.mode}, {args.width}x{args.height}, {args.frames}f)...", flush=True)
    wf = build_h3_workflow(
        first_frame_name=first_uploaded,
        video_prompt=args.video_prompt,
        mode=args.mode,
        width=args.width,
        height=args.height,
        frames=args.frames,
        seed=args.seed,
        prefix=out_path.stem,
        last_frame_name=last_uploaded,
    )
    info = queue_and_wait(args.url, wf, output_node="16")
    download_output(args.url, info, out_path)
    print(f"[DONE] Saved video to {out_path} in {time.time() - t0:.1f}s", flush=True)


def cmd_t2v(args):
    t0 = time.time()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    first_frame_dest = out_path.with_name(f"{out_path.stem}_first_frame.png")

    if args.t2i_engine == "h3_image":
        ref_uploaded = upload_image(args.url, Path(args.ref_image)) if args.ref_image else None
        print(f"[1/3] Generating first frame via MiniMax-H3-Image ({args.width}x{args.height} -> >=4MP)...", flush=True)
        t2i_wf = build_h3_image_workflow(
            args.image_prompt,
            args.width,
            args.height,
            args.seed,
            f"{out_path.stem}_ff",
            ref_image_name=ref_uploaded,
        )
    else:
        print(f"[1/3] Generating first frame via Qwen-Image-2512 ({args.width}x{args.height})...", flush=True)
        t2i_wf = build_t2i_workflow(args.image_prompt, args.width, args.height, args.seed, f"{out_path.stem}_ff")
    img_info = queue_and_wait(args.url, t2i_wf, output_node="11")
    download_output(args.url, img_info, first_frame_dest)
    print(f"  First frame saved to {first_frame_dest}", flush=True)

    print(f"[2/3] Uploading first frame to input...", flush=True)
    uploaded_ff = upload_image(args.url, first_frame_dest)

    print(f"[3/3] Generating MiniMax H3 video + native audio ({args.mode})...", flush=True)
    h3_wf = build_h3_workflow(
        first_frame_name=uploaded_ff,
        video_prompt=args.video_prompt,
        mode=args.mode,
        width=args.width,
        height=args.height,
        frames=args.frames,
        seed=args.seed,
        prefix=out_path.stem,
    )
    vid_info = queue_and_wait(args.url, h3_wf, output_node="16")
    download_output(args.url, vid_info, out_path)
    print(f"[DONE] Saved video to {out_path} in {time.time() - t0:.1f}s", flush=True)


def cmd_batch(args):
    prompts_data = json.loads(Path(args.prompts_json).read_text(encoding="utf-8"))
    frames_dir = Path(args.frames_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for shot in prompts_data.get("shots", []):
        sid = shot["id"]
        out_clip = out_dir / f"shot_{sid:02d}.mp4"
        if out_clip.exists() and out_clip.stat().st_size > 10000 and not args.overwrite:
            print(f"[SKIP] Shot {sid:02d} already exists at {out_clip}", flush=True)
            continue
        ff_path = frames_dir / shot["first_frame"]
        print(f"[SHOT {sid:02d}] Uploading {ff_path.name}...", flush=True)
        t0 = time.time()
        uploaded = upload_image(args.url, ff_path, f"batch_shot_{sid:02d}.png")
        wf = build_h3_workflow(
            first_frame_name=uploaded,
            video_prompt=shot["prompt_en"],
            mode=args.mode,
            width=args.width,
            height=args.height,
            frames=args.frames,
            seed=args.seed + sid,
            prefix=f"batch_h3_shot_{sid:02d}",
        )
        info = queue_and_wait(args.url, wf, output_node="16")
        download_output(args.url, info, out_clip)
        print(f"[DONE] Shot {sid:02d} saved to {out_clip} in {time.time() - t0:.1f}s", flush=True)


def _upscale_single(args, in_file: Path, out_file: Path):
    if out_file.exists() and out_file.stat().st_size > 10000 and not args.overwrite:
        print(f"[SKIP] {out_file} already exists.", flush=True)
        return
    out_file.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print(f"[1/2] Uploading video: {in_file.name}", flush=True)
    uploaded_vid = upload_image(args.url, in_file, f"upscale_in_{in_file.name}")
    print(
        f"[2/2] Upscaling {in_file.name} -> {args.width}x{args.height} ({args.method})...",
        flush=True,
    )
    wf, out_node = build_upscale_workflow(
        video_name=uploaded_vid,
        method=args.method,
        width=args.width,
        height=args.height,
        crop=args.crop,
        detail=args.detail,
        esrgan_model=args.esrgan_model,
        seed=args.seed,
        prefix=out_file.stem,
    )
    info = queue_and_wait(args.url, wf, output_node=out_node)
    download_output(args.url, info, out_file)
    print(f"[DONE] Upscaled video saved to {out_file} in {time.time() - t0:.1f}s", flush=True)


def cmd_upscale(args):
    in_path = Path(args.input)
    out_path = Path(args.output)
    if in_path.is_dir():
        videos = sorted(in_path.glob("*.mp4"))
        if not videos:
            raise FileNotFoundError(f"No .mp4 files found in {in_path}")
        out_path.mkdir(parents=True, exist_ok=True)
        for vid in videos:
            _upscale_single(args, vid, out_path / vid.name)
    else:
        if not in_path.is_file():
            raise FileNotFoundError(f"Input video not found: {in_path}")
        target = out_path / in_path.name if out_path.is_dir() else out_path
        _upscale_single(args, in_path, target)


def main():
    parser = argparse.ArgumentParser(description="MiniMax H3 Local ComfyUI Service Client")
    parser.add_argument("--url", default="http://127.0.0.1:8188", help="Local ComfyUI service URL")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Check GPU, VRAM, and queue status")

    p_i2v = sub.add_parser("i2v", help="Image-to-Video + Native Audio")
    p_i2v.add_argument("--first-frame", required=True)
    p_i2v.add_argument("--last-frame", default=None)
    p_i2v.add_argument("--video-prompt", required=True)
    p_i2v.add_argument("--output", required=True)
    p_i2v.add_argument("--mode", choices=["quant", "bf16"], default="quant")
    p_i2v.add_argument("--width", type=int, default=720)
    p_i2v.add_argument("--height", type=int, default=1280)
    p_i2v.add_argument("--frames", type=int, default=121)
    p_i2v.add_argument("--seed", type=int, default=20261112)

    p_t2v = sub.add_parser("t2v", help="Text-to-First-Frame + MiniMax H3 Video + Native Audio")
    p_t2v.add_argument("--image-prompt", required=True)
    p_t2v.add_argument("--video-prompt", required=True)
    p_t2v.add_argument("--output", required=True)
    p_t2v.add_argument("--t2i-engine", choices=["qwen", "h3_image"], default="h3_image")
    p_t2v.add_argument("--ref-image", default=None, help="Optional <Picture 1> reference image for MiniMax-H3-Image")
    p_t2v.add_argument("--mode", choices=["quant", "bf16"], default="quant")
    p_t2v.add_argument("--width", type=int, default=720)
    p_t2v.add_argument("--height", type=int, default=1280)
    p_t2v.add_argument("--frames", type=int, default=121)
    p_t2v.add_argument("--seed", type=int, default=20261112)

    p_batch = sub.add_parser("batch", help="Batch-generate storyboard shots")
    p_batch.add_argument("--prompts-json", required=True)
    p_batch.add_argument("--frames-dir", required=True)
    p_batch.add_argument("--output-dir", required=True)
    p_batch.add_argument("--mode", choices=["quant", "bf16"], default="quant")
    p_batch.add_argument("--width", type=int, default=720)
    p_batch.add_argument("--height", type=int, default=1280)
    p_batch.add_argument("--frames", type=int, default=121)
    p_batch.add_argument("--seed", type=int, default=1000)
    p_batch.add_argument("--overwrite", action="store_true")

    p_up = sub.add_parser("upscale", help="Super-resolve existing .mp4 video(s) to 1080p")
    p_up.add_argument("--input", required=True, help="Input .mp4 file or directory of .mp4 files")
    p_up.add_argument("--output", required=True, help="Output .mp4 file or directory")
    p_up.add_argument("--method", choices=["relayvsr", "esrgan"], default="relayvsr")
    p_up.add_argument("--width", type=int, default=1920)
    p_up.add_argument("--height", type=int, default=1080)
    p_up.add_argument("--crop", choices=["center", "disabled"], default="center")
    p_up.add_argument("--detail", type=float, default=1.0, help="RelayVSR detail blend (0.0 - 1.0)")
    p_up.add_argument("--esrgan-model", default="RealESRGAN_x2plus.pth")
    p_up.add_argument("--seed", type=int, default=42)
    p_up.add_argument("--overwrite", action="store_true")

    args = parser.parse_args()
    if args.cmd == "status":
        cmd_status(args)
    elif args.cmd == "i2v":
        cmd_i2v(args)
    elif args.cmd == "t2v":
        cmd_t2v(args)
    elif args.cmd == "batch":
        cmd_batch(args)
    elif args.cmd == "upscale":
        cmd_upscale(args)


if __name__ == "__main__":
    main()
