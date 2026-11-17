---
name: minimax-h3-service-caller
description: >-
  Client skill for calling the local mapped MiniMax H3 ComfyUI service
  (default http://127.0.0.1:8188 / http://localhost:8188). Supports service
  health/VRAM inspection, pure Text-to-Video (via MiniMax-H3-Image first-frame
  with multi-ref support or optional Qwen-Image-2512 + MiniMax H3), Image-to-Video (first-frame or first+last-frame to 720p 24fps
  video with joint native audio), multi-shot storyboard batch generation, and
  1080p video super-resolution / upscaling (RelayVSR x2 and RealESRGAN). Use
  this skill whenever the user wants to generate videos, upscale clips to 1080p,
  test prompts, check queue status, or batch-produce clips.
---

# MiniMax H3 Local Service Caller Skill (`localhost:8188`)

This skill calls the MiniMax H3 ComfyUI service mapped to local port `8188` (`http://127.0.0.1:8188`).
All operations are encapsulated in the zero-dependency Python client [h3_client.py](./scripts/h3_client.py), which runs on any Python 3 (Windows, WSL, Linux, macOS).
Paths in the examples are relative to this skill's folder; the examples use PowerShell line continuation (a backtick), use `\` in bash.
Deploy the service first with the `comfyui-h3-colab` or `comfyui-h3-autodl` skill of this plugin. If `127.0.0.1:8188` is not reachable from Windows while the tunnel runs in WSL,
pass `--url http://<WSL IP>:8188` or the `https://*.trycloudflare.com` address printed at deploy time.

---

## 1. Quick Commands (`h3_client.py`)

### 1.1 Check Service Health, GPU & Queue Status (`status`)
Always run this first to verify that `http://127.0.0.1:8188` is reachable and check which model tier (`quant` or `bf16`) is loaded on the remote GPU:
```powershell
python scripts/h3_client.py status
```

### 1.2 Pure Text-to-Video (`t2v` — Text -> First Frame -> Video + Native Audio)
Supports two first-frame generators (`--t2i-engine`):
- **`h3_image`** *(Default)*: Calls **`MiniMax-H3-Image`** (6 steps, >=4MP, shares `Qwen3-VL-32B` with H3 Video) and optionally accepts `--ref-image` (`<Picture 1>` in prompt) for multi-shot character consistency!
- **`qwen`**: Calls `Qwen-Image-2512` (4-step Lightning).

```powershell
python scripts/h3_client.py t2v `
  --t2i-engine h3_image `
  --image-prompt "Detailed visual description of the starting frame..." `
  --video-prompt "Detailed description of character motion, camera movement, ambient sound, and speech..." `
  --output outputs\clip_01.mp4
```

### 1.3 Image-to-Video (`i2v` — Local First Frame -> Video + Native Audio)
Uploads a local `.png`/`.jpg` first frame (and optional `--last-frame`) to generate a 5-second 720p video with joint native audio:
```powershell
python scripts/h3_client.py i2v `
  --first-frame inputs\shot_01.png `
  --video-prompt "Natural motion description and realistic ambient audio..." `
  --output outputs\shot_01.mp4
```

### 1.4 Multi-Shot Storyboard Batch Generation (`batch`)
Given a `prompts.json` file (containing `{"shots": [{"id": 1, "first_frame": "shot_01.png", "prompt_en": "..."}]}`) and a folder of first-frame images, generates all shots sequentially (skipping already completed shots unless `--overwrite` is passed):
```powershell
python scripts/h3_client.py batch `
  --prompts-json prompts.json `
  --frames-dir frames `
  --output-dir outputs\clips
```

### 1.5 Video Super-Resolution to 1080p (`upscale`)
Upscales an existing `.mp4` video (or an entire folder of `.mp4` clips) while preserving original `fps` and audio, using either ComfyUI's official LightX2V `RelayVSR x2` (`--method relayvsr`, default, specifically trained for post-H3 2x upscaling) or `RealESRGAN` (`--method esrgan`):

- **Single `.mp4` or Whole Directory via `RelayVSR x2` (Default, ~50s per 5s clip on A100 80GB)**:
```powershell
# Single clip -> 1920x1080
python scripts/h3_client.py upscale `
  --input episodes\ep01_colors\h3\clips\shot_01.mp4 `
  --output episodes\ep01_colors\h3\clips_1080p\shot_01.mp4 `
  --method relayvsr --width 1920 --height 1080

# Whole directory batch upscale -> 1920x1080
python scripts/h3_client.py upscale `
  --input episodes\ep01_colors\h3\clips `
  --output episodes\ep01_colors\h3\clips_1080p `
  --method relayvsr --width 1920 --height 1080
```

- **2D / Anime Crisp Linework Upscaling via `RealESRGAN` (~92s per 5s clip on A100 80GB)**:
```powershell
python scripts/h3_client.py upscale `
  --input episodes\ep01_colors\h3\clips\shot_01.mp4 `
  --output episodes\ep01_colors\h3\clips_1080p\shot_01_anime.mp4 `
  --method esrgan --esrgan-model RealESRGAN_x4plus_anime_6B.pth --width 1920 --height 1080
```

---

## 2. Common CLI Options

| Flag | Default | Description |
| :--- | :--- | :--- |
| `--url` | `http://127.0.0.1:8188` | Mapped ComfyUI HTTP endpoint |
| `--mode` | `quant` | `quant` (INT8-convrot + 8-step Turbo LoRA, `cfg=1.0`) or `bf16` (Full BF16 20-step, `cfg=4.0`) |
| `--width` | `720` | Video width (`720` for vertical 9:16, `1280` for horizontal 16:9) |
| `--height` | `1280` | Video height (`1280` for vertical 9:16, `720` for horizontal 16:9) |
| `--frames` | `121` | Frame count at 24fps (`121` frames = 5.04 seconds) |
| `--seed` | `20261112` | Random seed for reproducible generation |

> **Grid snapping**: the native H3 nodes require width/height on a 32px grid and frame count on the `17k+5` grid. The client snaps automatically and prints what it used (e.g. `1280x720/121f -> 1280x736/124f`, 5.17s). Crop/trim in ffmpeg afterwards if you need exact 720p / 5.0s.
>
> **`--last-frame`** (i2v only) is wired to the `last_frame` input of `MiniMaxH3ImageToVideo`.

### 2.1 `upscale` Subcommand Options & Method Comparison

| Flag | Default | Description |
| :--- | :--- | :--- |
| `--input` | *(required)* | Input `.mp4` file or directory containing `.mp4` files |
| `--output` | *(required)* | Output `.mp4` file or directory (automatically matched when `--input` is a directory) |
| `--method` | `relayvsr` | `relayvsr` (LightX2V 2x video VSR) or `esrgan` (frame-by-frame GAN upscaler) |
| `--width` / `--height` | `1920` / `1080` | Target output resolution after AI 2x/4x upscaling (`ImageScale` `lanczos`) |
| `--crop` | `center` | `center` (exact `1920×1080` crop, e.g. from `1280×736`) or `disabled` (stretch/exact fit) |
| `--detail` | `1.0` | `RelayVSR` `VSRDecode` detail blend factor (`0.0`–`1.0`) |
| `--esrgan-model` | `RealESRGAN_x2plus.pth` | Checkpoint in `models/upscale_models/` (`RealESRGAN_x2plus.pth` or `RealESRGAN_x4plus_anime_6B.pth`) |
| `--seed` | `42` | Random seed for `RelayVSR` 1-step `KSampler` |
| `--overwrite` | `False` | Re-run even if output `.mp4` already exists |

| Method / Model | A100 80GB Speed (`5.17s` / `124f`) | Characteristics & Best Use Case |
| :--- | :--- | :--- |
| **`relayvsr`** (`RelayVSR x2`) | **~49–54s** | **Recommended default**: specifically retrained for post-MiniMax-H3 upscaling, 1-step keyframe + Flash decoder, fastest & temporally consistent |
| **`esrgan`** (`RealESRGAN_x2plus.pth`) | **~92s** | General-purpose photographic/textured 2x spatial sharpening |
| **`esrgan`** (`RealESRGAN_x4plus_anime_6B.pth`) | **~92s+** | 2D illustration / anime crisp line-art & flat-color edge enhancement |

---

## 3. ComfyUI Node & Model Reference (Quantized Service + Super-Resolution)

If building custom ComfyUI workflows against `http://127.0.0.1:8188`:
- **Diffusion Model (`UNETLoader`)**: `minimax_h3_fl2va_pruned_int8_convrot.safetensors`
- **8-Step Turbo LoRA (`LoraLoaderModelOnly`)**: `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` (`strength_model: 1.0`)
- **Text Encoder (`CLIPLoader`, `type: "minimax"`)**: `qwen3vl_32b_minimax_h3_int8_convrot.safetensors`
- **Video VAE (`VAELoader`, 24ch)**: `minimax_h3_video_vae_int8_convrot.safetensors`
- **Audio VAE (`VAELoader`, 32ch)**: `minimax_h3_audio_vae_fp32.safetensors`
- **First-Frame T2I (`MiniMax-H3-Image`, Default)**:
  - UNet: `minimax_h3_image_pruned_int8_convrot.safetensors` (6 steps, `cfg=1.0`, `euler`/`simple`, >=4MP, supports `<Picture 1>` via `--ref-image`)
  - Text Encoder: shares `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` / `nvfp4_awq` with H3 Video
  - VAE: `minimax_h3_image_vae_fp16.safetensors`
- **First-Frame T2I (`Qwen-Image-2512`, Optional)**:
  - UNet: `qwen_image_2512_fp8_e4m3fn.safetensors`
  - LoRA: `Qwen-Image-Lightning-4steps-V1.0.safetensors` (4 steps, `cfg=1.0`, `ModelSamplingAuraFlow` `shift=3.1`)
  - Text Encoder: `qwen_2.5_vl_7b_fp8_scaled.safetensors` (`type: "qwen_image"`)
  - VAE: `qwen_image_vae.safetensors`
- **1080p Video Super-Resolution (`RelayVSR x2`)**:
  - Node chain: `LoadVideo` -> `GetVideoComponents` -> `UNETLoader` + `VAELoader` -> `RelayVSRConditioning` -> `KSampler` (`steps=1`, `cfg=1.0`, `euler`, `simple`) -> `VSRDecode` (`detail=1.0`) -> `ImageScale` (`lanczos`, `1920×1080`, `center`) -> `CreateVideo` -> `SaveVideo`
  - UNet: `relayvsr_x2_lightx2v_int8_convrot.safetensors`
  - VAE: `relayvsr_flash_vae_x2_fp32.safetensors`
- **1080p Video Super-Resolution (`RealESRGAN`)**:
  - Node chain: `LoadVideo` -> `GetVideoComponents` -> `UpscaleModelLoader` -> `ImageUpscaleWithModel` -> `ImageScale` (`lanczos`, `1920×1080`, `center`) -> `CreateVideo` -> `SaveVideo`
  - Checkpoints (`models/upscale_models/`): `RealESRGAN_x2plus.pth`, `RealESRGAN_x4plus_anime_6B.pth`
