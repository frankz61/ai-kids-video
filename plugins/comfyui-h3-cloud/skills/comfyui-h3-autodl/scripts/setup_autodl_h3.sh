#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export PATH="/root/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

BASE_DIR="/root/autodl-tmp"
COMFY_DIR="${BASE_DIR}/ComfyUI"
SHARED_MODELS="/root/autodl-fs/comfyui_models"
WITH_H3_IMAGE="${WITH_H3_IMAGE:-1}"
WITH_QWEN_T2I="${WITH_QWEN_T2I:-0}"
WITH_UPSCALE="${WITH_UPSCALE:-1}"

echo "[1/6] Installing system tools (aria2, ffmpeg, git, curl)..."
if ! command -v aria2c >/dev/null 2>&1 || ! command -v ffmpeg >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq aria2 ffmpeg git curl > /dev/null
fi

echo "[2/6] Enabling /etc/network_turbo for GitHub clones & RealESRGAN..."
if [ -f /etc/network_turbo ]; then
  # shellcheck disable=SC1091
  source /etc/network_turbo || true
fi

mkdir -p "${BASE_DIR}" "${SHARED_MODELS}"
cd "${BASE_DIR}"
if [ ! -d "${COMFY_DIR}" ]; then
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git "${COMFY_DIR}"
fi

mkdir -p "${COMFY_DIR}/custom_nodes"
cd "${COMFY_DIR}/custom_nodes"
for repo in \
  "https://github.com/city96/ComfyUI-GGUF.git" \
  "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git" \
  "https://github.com/kijai/ComfyUI-KJNodes.git"; do
  name="$(basename "${repo}" .git)"
  if [ ! -d "${name}" ]; then
    git clone --depth 1 "${repo}" "${name}"
  fi
done

dl() {
  local url="$1"
  local sub="$2"
  local out="$3"
  local local_dir="${COMFY_DIR}/models/${sub}"
  local shared_dir="${SHARED_MODELS}/${sub}"
  mkdir -p "${local_dir}" "${shared_dir}"

  # 1. If already cached in /root/autodl-fs/comfyui_models, link it immediately!
  if [ -s "${shared_dir}/${out}" ] && [ ! -f "${shared_dir}/${out}.aria2" ]; then
    echo "  -> [CACHE HIT] Linking ${out} from ${shared_dir}..."
    ln -sf "${shared_dir}/${out}" "${local_dir}/${out}"
    return 0
  fi

  # 2. If /root/autodl-tmp has <80GB free (e.g. Pro instance without local data disk), download directly to /root/autodl-fs
  local tmp_avail_kb
  tmp_avail_kb=$(df -Pk "${BASE_DIR}" | awk 'NR==2 {print $4}')
  if [ "${DIRECT_SHARED:-0}" = "1" ] || [ "${tmp_avail_kb:-0}" -lt 83886080 ]; then
    echo "  -> Downloading/Resuming ${out} directly into ${shared_dir}..."
    aria2c -c -x 16 -s 16 -k 1M --file-allocation=none --console-log-level=warn -d "${shared_dir}" -o "${out}" "${url}"
    ln -sf "${shared_dir}/${out}" "${local_dir}/${out}"
    return 0
  fi

  # 3. Otherwise download/resume (-c) in local NVMe SSD first
  if [ ! -s "${local_dir}/${out}" ] || [ -f "${local_dir}/${out}.aria2" ]; then
    echo "  -> Downloading/Resuming ${out}..."
    aria2c -c -x 16 -s 16 -k 1M --console-log-level=warn -d "${local_dir}" -o "${out}" "${url}"
  else
    echo "  -> [LOCAL HIT] ${out} already downloaded locally."
  fi
}

if [ "${WITH_UPSCALE}" = "1" ]; then
  dl "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth" \
     "upscale_models" "RealESRGAN_x2plus.pth"
  dl "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth" \
     "upscale_models" "RealESRGAN_x4plus_anime_6B.pth"
fi

echo "[3/6] Installing Python dependencies..."
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY || true

if [ ! -f "${COMFY_DIR}/.deps_installed" ]; then
  cd "${COMFY_DIR}"
  PIP_IDX="https://mirrors.cloud.tencent.com/pypi/simple"
  /root/miniconda3/bin/pip install --no-input -i "${PIP_IDX}" -r requirements.txt
  /root/miniconda3/bin/pip install --no-input -i "${PIP_IDX}" gguf huggingface_hub comfy-kitchen hf_transfer
  for req in "${COMFY_DIR}"/custom_nodes/*/requirements.txt; do
    if [ -f "${req}" ]; then
      /root/miniconda3/bin/pip install --no-input -i "${PIP_IDX}" -r "${req}" || true
    fi
  done
  touch "${COMFY_DIR}/.deps_installed"
else
  echo "  -> [SKIP] Python dependencies already installed (.deps_installed)."
fi

echo "[4/6] Downloading models (WITH_H3_IMAGE=${WITH_H3_IMAGE}, WITH_QWEN_T2I=${WITH_QWEN_T2I}, WITH_UPSCALE=${WITH_UPSCALE})..."
MS_BASE="https://modelscope.cn/models"

# 4a. MiniMax H3 Video (quantized INT8-convrot + 8-step Turbo LoRA + NVFP4 Blackwell text encoder)
H3_MS="${MS_BASE}/Comfy-Org/MiniMax-H3/resolve/master"
dl "${H3_MS}/vae/minimax_h3_audio_vae_fp32.safetensors" \
   "vae" "minimax_h3_audio_vae_fp32.safetensors"
dl "${H3_MS}/vae/minimax_h3_video_vae_int8_convrot.safetensors" \
   "vae" "minimax_h3_video_vae_int8_convrot.safetensors"
dl "${H3_MS}/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors" \
   "diffusion_models" "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
dl "${H3_MS}/loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors" \
   "loras" "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
dl "${H3_MS}/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors" \
   "text_encoders" "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
ln -sf qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors \
   "${COMFY_DIR}/models/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors"

# 4b. MiniMax-H3-Image (6-step distilled T2I + multi-ref editing, shares Qwen3-VL-32B text encoder)
if [ "${WITH_H3_IMAGE}" = "1" ]; then
  H3IMG_MS="${MS_BASE}/Comfy-Org/MiniMax-H3-Image/resolve/master"
  dl "${H3IMG_MS}/diffusion_models/minimax_h3_image_pruned_int8_convrot.safetensors" \
     "diffusion_models" "minimax_h3_image_pruned_int8_convrot.safetensors"
  dl "${H3IMG_MS}/vae/minimax_h3_image_vae_fp16.safetensors" \
     "vae" "minimax_h3_image_vae_fp16.safetensors"
fi

# 4c. Qwen-Image-2512 T2I (optional; disabled by default when using MiniMax-H3-Image)
if [ "${WITH_QWEN_T2I}" = "1" ]; then
  QWEN_MS="${MS_BASE}/Comfy-Org/Qwen-Image_ComfyUI/resolve/master"
  dl "${QWEN_MS}/split_files/diffusion_models/qwen_image_2512_fp8_e4m3fn.safetensors" \
     "diffusion_models" "qwen_image_2512_fp8_e4m3fn.safetensors"
  dl "${QWEN_MS}/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
     "text_encoders" "qwen_2.5_vl_7b_fp8_scaled.safetensors"
  dl "${QWEN_MS}/split_files/vae/qwen_image_vae.safetensors" \
     "vae" "qwen_image_vae.safetensors"
  dl "${MS_BASE}/lightx2v/Qwen-Image-Lightning/resolve/master/Qwen-Image-Lightning-4steps-V1.0.safetensors" \
     "loras" "Qwen-Image-Lightning-4steps-V1.0.safetensors"
fi

# 4d. RelayVSR x2 1080p Video Super-Resolution
if [ "${WITH_UPSCALE}" = "1" ]; then
  VSR_MS="${MS_BASE}/Comfy-Org/RelayVSR/resolve/master"
  dl "${VSR_MS}/diffusion_models/relayvsr_x2_lightx2v_int8_convrot.safetensors" \
     "diffusion_models" "relayvsr_x2_lightx2v_int8_convrot.safetensors"
  dl "${VSR_MS}/vae/relayvsr_flash_vae_x2_fp32.safetensors" \
     "vae" "relayvsr_flash_vae_x2_fp32.safetensors"
fi

# Write helper script in shared storage for instant linking on any future AutoDL machine
cat << 'LINK_EOF' > "${SHARED_MODELS}/link_models.sh"
#!/usr/bin/env bash
set -euo pipefail
TARGET_COMFY="${1:-/root/autodl-tmp/ComfyUI}"
SHARED_ROOT="/root/autodl-fs/comfyui_models"
for sub in diffusion_models text_encoders vae loras upscale_models; do
  mkdir -p "${TARGET_COMFY}/models/${sub}"
  if [ -d "${SHARED_ROOT}/${sub}" ]; then
    for f in "${SHARED_ROOT}/${sub}"/*; do
      [ -e "$f" ] || continue
      ln -sf "$f" "${TARGET_COMFY}/models/${sub}/$(basename "$f")"
    done
  fi
done
if [ -e "${TARGET_COMFY}/models/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors" ]; then
  ln -sf qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors \
     "${TARGET_COMFY}/models/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
fi
echo "Linked shared models from ${SHARED_ROOT} -> ${TARGET_COMFY}/models"
LINK_EOF
chmod +x "${SHARED_MODELS}/link_models.sh"

echo "[5/6] Starting ComfyUI on port 8188 (--disable-dynamic-vram)..."
if ! nvidia-smi >/dev/null 2>&1; then
  echo "NO_GPU_DETECTED: Running in CPU/non-GPU mode. Dependencies & shared models are initialized!"
  exit 0
fi
pkill -f "python.*main.py" || true
sleep 1
cd "${COMFY_DIR}"
nohup /root/miniconda3/bin/python main.py --listen 0.0.0.0 --port 8188 --enable-cors-header --disable-dynamic-vram > "${BASE_DIR}/comfyui.log" 2>&1 < /dev/null &

echo "[6/6] Waiting for ComfyUI HTTP readiness..."
for i in $(seq 1 45); do
  if curl -s http://127.0.0.1:8188/system_stats >/dev/null 2>&1; then
    echo "COMFYUI_READY_ON_8188"
    curl -s http://127.0.0.1:8188/system_stats | head -c 500
    echo ""
    echo "[Post] Launching background sync to persistent shared store (${SHARED_MODELS})..."
    nohup bash -c "
      for sub in diffusion_models text_encoders vae loras upscale_models; do
        mkdir -p '${SHARED_MODELS}'/\${sub}
        for src in '${COMFY_DIR}'/models/\${sub}/*.safetensors '${COMFY_DIR}'/models/\${sub}/*.pth; do
          [ -f \"\${src}\" ] && [ ! -L \"\${src}\" ] || continue
          base=\$(basename \"\${src}\")
          [ -f \"\${src}.aria2\" ] && continue
          dst='${SHARED_MODELS}'/\${sub}/\${base}
          if [ ! -s \"\${dst}\" ]; then
            echo \"[SYNC] Copying \${base} -> \${dst}...\"
            cp -f \"\${src}\" \"\${dst}.tmp\" && mv -f \"\${dst}.tmp\" \"\${dst}\"
          fi
          ln -sf \"\${dst}\" \"\${src}\"
        done
      done
      echo \"[SYNC] All models cached in ${SHARED_MODELS} and symlinked.\"
    " > "${BASE_DIR}/sync_to_fs.log" 2>&1 < /dev/null &
    exit 0
  fi
  sleep 2
done

echo "ERROR: ComfyUI did not become ready within 90s"
tail -n 60 "${BASE_DIR}/comfyui.log" || true
exit 1
