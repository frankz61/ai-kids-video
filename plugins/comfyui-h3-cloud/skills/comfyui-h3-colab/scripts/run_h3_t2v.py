#!/usr/bin/env python3
"""
MiniMax H3 Video + Native Audio Generation Runner for ComfyUI on Colab
Supports:
  --mode quant : Sweet-Spot INT8-convrot + FP8 TE + 8-step Turbo LoRA (Recommended for A100 40GB / L4)
  --mode bf16  : Full-Blooded BF16 UNet + BF16 TE + FP16 Video VAE + 20 native steps (For A100 80GB)
"""
import argparse
import json
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_opener = urllib.request.build_opener()
_opener.addheaders = [("User-Agent", "Mozilla/5.0")]
urllib.request.install_opener(_opener)


def upload_image(comfy_url: str, filepath: Path, target_name: str) -> str:
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    data = [
        f"--{boundary}".encode(),
        f'Content-Disposition: form-data; name="image"; filename="{target_name}"'.encode(),
        b"Content-Type: image/png",
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
        f"{comfy_url}/upload/image",
        data=b"\r\n".join(data),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())["name"]


def build_h3_workflow(
    first_frame_name: str,
    prompt_text: str,
    mode: str = "quant",
    width: int = 720,
    height: int = 1280,
    frames: int = 121,
    seed: int = 20261112,
    prefix: str = "minimax_h3_out",
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
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt_text, "clip": ["3", 0]},
        },
        "8": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "low quality, blurry, deformed, watermark, text, static, frozen",
                "clip": ["3", 0],
            },
        },
        "9": {
            "class_type": "MiniMaxH3FirstLastFrameToVideo",
            "inputs": {
                "positive": ["7", 0],
                "negative": ["8", 0],
                "vae": ["4", 0],
                "width": width,
                "height": height,
                "length": frames,
                "batch_size": 1,
                "start_image": ["6", 0],
            },
        },
        "10": {"class_type": "EmptyH3LatentAudio", "inputs": {"length": frames}},
        "11": {
            "class_type": "LatentConcat",
            "inputs": {"samples1": ["9", 2], "samples2": ["10", 0], "dim": "t"},
        },
        "12": {
            "class_type": "KSampler",
            "inputs": {
                "model": model_ref,
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["9", 0],
                "negative": ["9", 1],
                "latent_image": ["11", 0],
                "denoise": 1.0,
            },
        },
        "13": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["12", 0], "vae": ["4", 0]},
        },
        "14": {
            "class_type": "MiniMaxH3LatentAudioDecoder",
            "inputs": {"samples": ["12", 0], "vae": ["5", 0]},
        },
        "15": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["13", 0],
                "audio": ["14", 0],
                "frame_rate": 24.0,
                "loop_count": 0,
                "filename_prefix": prefix,
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 18,
                "save_metadata": True,
                "trim_to_audio": False,
                "pingpong": False,
                "save_output": True,
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
    return wf


def queue_and_wait(comfy_url: str, workflow: dict, output_node: str = "15") -> dict:
    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(
        f"{comfy_url}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        prompt_id = json.loads(resp.read().decode())["prompt_id"]
    print(f"  Queued prompt_id={prompt_id}, waiting...", flush=True)
    while True:
        try:
            with urllib.request.urlopen(f"{comfy_url}/history/{prompt_id}", timeout=15) as resp:
                hist = json.loads(resp.read().decode())
            if prompt_id in hist:
                entry = hist[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI execution error: {json.dumps(status)}")
                outputs = entry.get("outputs", {})
                if output_node in outputs:
                    for item in outputs[output_node].get("gifs", []) + outputs[output_node].get("images", []):
                        return item
                raise RuntimeError(f"No output found in node {output_node}: {outputs}")
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            print(f"  [WARN] transient connection error ({e}), retrying in 5s...", flush=True)
            time.sleep(5)
            continue
        time.sleep(3)


def download_output(comfy_url: str, file_info: dict, dest: Path):
    params = urllib.parse.urlencode(
        {
            "filename": file_info["filename"],
            "subfolder": file_info.get("subfolder", ""),
            "type": file_info.get("type", "output"),
        }
    )
    urllib.request.urlretrieve(f"{comfy_url}/view?{params}", dest)


def main():
    parser = argparse.ArgumentParser(description="Run MiniMax H3 video generation via ComfyUI API")
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    parser.add_argument("--mode", choices=["quant", "bf16"], default="quant")
    parser.add_argument("--first-frame", required=True, help="Path to local first-frame PNG image")
    parser.add_argument("--prompt", required=True, help="Video motion + audio prompt")
    parser.add_argument("--output", required=True, help="Destination .mp4 file path")
    parser.add_argument("--seed", type=int, default=20261112)
    args = parser.parse_args()

    t0 = time.time()
    first_frame_path = Path(args.first_frame)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[1/2] Uploading first frame {first_frame_path.name}...")
    uploaded_name = upload_image(args.comfy_url, first_frame_path, first_frame_path.name)

    print(f"[2/2] Running MiniMax H3 ({args.mode})...")
    wf = build_h3_workflow(
        first_frame_name=uploaded_name,
        prompt_text=args.prompt,
        mode=args.mode,
        seed=args.seed,
        prefix=out_path.stem,
    )
    info = queue_and_wait(args.comfy_url, wf, output_node="15")
    download_output(args.comfy_url, info, out_path)
    print(f"[DONE] Saved {out_path} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
