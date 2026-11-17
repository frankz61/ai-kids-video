#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

MODE="${MODE:-quant}"        # "quant" (52GB sweet-spot) or "bf16" (118GB full precision)
WITH_H3_IMAGE="${WITH_H3_IMAGE:-1}" # Set to "1" to download MiniMax-H3-Image (shares Qwen3-VL-32B)
WITH_QWEN_T2I="${WITH_QWEN_T2I:-0}" # Set to "1" to also download Qwen-Image-2512 T2I (off by default)
WITH_UPSCALE="${WITH_UPSCALE:-1}"   # Set to "1" to download RelayVSR x2 & RealESRGAN video upscalers

echo "[1/5] Installing system packages (aria2, ffmpeg, cloudflared)..."
apt-get update -qq && apt-get install -y -qq aria2 ffmpeg > /dev/null
if ! command -v cloudflared >/dev/null 2>&1; then
  wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared
  chmod +x /usr/local/bin/cloudflared
fi

echo "[2/5] Installing ComfyUI and custom nodes..."
mkdir -p /content
cd /content
if [ ! -d "/content/ComfyUI" ]; then
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git
fi
cd /content/ComfyUI
pip install -q -r requirements.txt
pip install -q gguf huggingface_hub hf_transfer

mkdir -p /content/ComfyUI/custom_nodes
cd /content/ComfyUI/custom_nodes
for repo in \
  "https://github.com/city96/ComfyUI-GGUF.git" \
  "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git" \
  "https://github.com/kijai/ComfyUI-KJNodes.git"; do
  name="$(basename "${repo}" .git)"
  if [ ! -d "${name}" ]; then
    git clone --depth 1 "${repo}" "${name}"
    if [ -f "${name}/requirements.txt" ]; then
      pip install -q -r "${name}/requirements.txt" || true
    fi
  fi
done

mkdir -p /content/ComfyUI/user/default/workflows
for wf in video_minimax_h3_t2v.json video_minimax_h3_fl2v.json image_minimax_h3_image_t2i.json utility_relayvsr_video_x2_upscale.json; do
  curl -sL "https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/${wf}" \
    -o "/content/ComfyUI/user/default/workflows/${wf}" || true
done

echo "[3/5] Downloading MiniMax H3 models from Comfy-Org/MiniMax-H3 (MODE=${MODE})..."
mkdir -p /content/ComfyUI/models/diffusion_models \
         /content/ComfyUI/models/text_encoders \
         /content/ComfyUI/models/vae \
         /content/ComfyUI/models/loras \
         /content/ComfyUI/models/upscale_models

dl() {
  local url="$1"
  local dir="$2"
  local out="$3"
  if [ ! -s "${dir}/${out}" ]; then
    echo "  -> Downloading ${out}..."
    aria2c -x 16 -s 16 -k 1M --console-log-level=warn -d "${dir}" -o "${out}" "${url}"
  else
    echo "  -> [SKIP] ${out} already exists."
  fi
}

HF_BASE="https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main"

# Audio VAE (shared by both modes)
dl "${HF_BASE}/vae/minimax_h3_audio_vae_fp32.safetensors" \
   "/content/ComfyUI/models/vae" "minimax_h3_audio_vae_fp32.safetensors"

if [ "${MODE}" = "bf16" ]; then
  dl "${HF_BASE}/diffusion_models/minimax_h3_fl2va_bf16.safetensors" \
     "/content/ComfyUI/models/diffusion_models" "minimax_h3_fl2va_bf16.safetensors"
  dl "${HF_BASE}/text_encoders/qwen3vl_32b_minimax_h3_bf16.safetensors" \
     "/content/ComfyUI/models/text_encoders" "qwen3vl_32b_minimax_h3_bf16.safetensors"
  dl "${HF_BASE}/vae/minimax_h3_video_vae_fp16.safetensors" \
     "/content/ComfyUI/models/vae" "minimax_h3_video_vae_fp16.safetensors"
  COMFY_FLAGS="--listen 0.0.0.0 --port 8188 --enable-cors-header --disable-dynamic-vram"
else
  dl "${HF_BASE}/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors" \
     "/content/ComfyUI/models/diffusion_models" "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
  dl "${HF_BASE}/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors" \
     "/content/ComfyUI/models/text_encoders" "qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
  dl "${HF_BASE}/vae/minimax_h3_video_vae_int8_convrot.safetensors" \
     "/content/ComfyUI/models/vae" "minimax_h3_video_vae_int8_convrot.safetensors"
  dl "${HF_BASE}/loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors" \
     "/content/ComfyUI/models/loras" "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
  COMFY_FLAGS="--listen 0.0.0.0 --port 8188 --enable-cors-header --disable-dynamic-vram"
fi

if [ "${WITH_H3_IMAGE}" = "1" ]; then
  echo "[3b/5] Downloading MiniMax-H3-Image T2I + multi-ref editing models..."
  H3IMG_HF="https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/main"
  dl "${H3IMG_HF}/diffusion_models/minimax_h3_image_pruned_int8_convrot.safetensors" \
     "/content/ComfyUI/models/diffusion_models" "minimax_h3_image_pruned_int8_convrot.safetensors"
  dl "${H3IMG_HF}/vae/minimax_h3_image_vae_fp16.safetensors" \
     "/content/ComfyUI/models/vae" "minimax_h3_image_vae_fp16.safetensors"
fi

if [ "${WITH_QWEN_T2I}" = "1" ]; then
  echo "[3b-alt/5] Downloading Qwen-Image-2512 T2I models (optional)..."
  dl "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_2512_fp8_e4m3fn.safetensors" \
     "/content/ComfyUI/models/diffusion_models" "qwen_image_2512_fp8_e4m3fn.safetensors"
  dl "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
     "/content/ComfyUI/models/text_encoders" "qwen_2.5_vl_7b_fp8_scaled.safetensors"
  dl "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors" \
     "/content/ComfyUI/models/vae" "qwen_image_vae.safetensors"
  dl "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Lightning-4steps-V1.0.safetensors" \
     "/content/ComfyUI/models/loras" "Qwen-Image-Lightning-4steps-V1.0.safetensors"
fi

if [ "${WITH_UPSCALE}" = "1" ]; then
  echo "[3c/5] Downloading Video Super-Resolution models (RelayVSR x2 + RealESRGAN)..."
  dl "https://huggingface.co/Comfy-Org/RelayVSR/resolve/main/diffusion_models/relayvsr_x2_lightx2v_int8_convrot.safetensors" \
     "/content/ComfyUI/models/diffusion_models" "relayvsr_x2_lightx2v_int8_convrot.safetensors"
  dl "https://huggingface.co/Comfy-Org/RelayVSR/resolve/main/vae/relayvsr_flash_vae_x2_fp32.safetensors" \
     "/content/ComfyUI/models/vae" "relayvsr_flash_vae_x2_fp32.safetensors"
  dl "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth" \
     "/content/ComfyUI/models/upscale_models" "RealESRGAN_x2plus.pth"
  dl "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth" \
     "/content/ComfyUI/models/upscale_models" "RealESRGAN_x4plus_anime_6B.pth"
fi

echo "[4/5] Starting ComfyUI (${COMFY_FLAGS})..."
pkill -f "python.*main.py" || true
cd /content/ComfyUI
nohup python3 main.py ${COMFY_FLAGS} > /content/comfyui.log 2>&1 < /dev/null &

echo "[5/5] Starting Cloudflared tunnel..."
pkill -f "cloudflared tunnel" || true
nohup cloudflared tunnel --url http://127.0.0.1:8188 > /content/cloudflared.log 2>&1 < /dev/null &

for i in $(seq 1 40); do
  if curl -s http://127.0.0.1:8188/system_stats >/dev/null 2>&1; then
    echo "COMFYUI_READY_ON_8188"
    sleep 3
    grep -o "https://[-a-z0-9]*\.trycloudflare\.com" /content/cloudflared.log | head -n 1 || true
    exit 0
  fi
  sleep 2
done
echo "ERROR: ComfyUI did not become ready within 80s"
cat /content/comfyui.log || true
exit 1
