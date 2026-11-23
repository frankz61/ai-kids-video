# Colab 部署参考：文件、路径、日志

[SKILL.md](./SKILL.md) 讲流程，这里列出部署脚本具体装了什么、放在哪，排查问题时查这里。

## 脚本

| 文件 | 在哪运行 | 作用 |
|---|---|---|
| [scripts/provision_fast_gpu.py](./scripts/provision_fast_gpu.py) | 本机（WSL） | 申请高速 GPU，上传并远程执行部署脚本 |
| [scripts/setup_colab_h3.sh](./scripts/setup_colab_h3.sh) | Colab 会话 | 装 ComfyUI、下模型、启动服务和 cloudflared。可单独重跑，已下载的文件会跳过 |
| [scripts/keep_ssh_tunnel.sh](./scripts/keep_ssh_tunnel.sh) | 本机（WSL），常驻 | 把会话的 8188 映射到本机，断线自动重连，顺带保活 |
| [scripts/run_h3_t2v.py](./scripts/run_h3_t2v.py) | 本机 | 最小的独立测试：一张首帧 + 一句提示词出一条 5 秒视频，用来验证部署 |

部署脚本的环境变量（`provision_fast_gpu.py` 的同名参数会传进去）：

| 变量 | 默认 | 作用 |
|---|---|---|
| `MODE` | `quant` | `quant` 或 `bf16` |
| `WITH_H3_IMAGE` | `1` | MiniMax-H3-Image 生图 |
| `WITH_QWEN_T2I` | `0` | Qwen-Image 2512 生图 |
| `WITH_UPSCALE` | `1` | RelayVSR x2 + RealESRGAN 超分 |

## 会话里的目录

```
/content/
  setup_colab_h3.sh          上传的部署脚本
  comfyui.log                ComfyUI 日志（加载模型、每步耗时、报错都在这里）
  cloudflared.log            cloudflared 日志（trycloudflare 地址从这里取）
  ComfyUI/
    custom_nodes/            ComfyUI-GGUF、ComfyUI-VideoHelperSuite、ComfyUI-KJNodes
    user/default/workflows/  官方模板：H3 文生视频、首尾帧生视频、H3-Image 生图、RelayVSR 超分
    models/
      diffusion_models/  text_encoders/  vae/  loras/  upscale_models/
    output/                  生成结果（会话释放后消失，及时下载）
```

## 模型文件

来源：`Comfy-Org/MiniMax-H3`、`Comfy-Org/MiniMax-H3-Image`、`Comfy-Org/RelayVSR`、`Comfy-Org/Qwen-Image_ComfyUI`、
`lightx2v/Qwen-Image-Lightning`（Hugging Face），RealESRGAN 来自其 GitHub Release。

| 用途 | 文件 | 目录 | 档位 / 开关 |
|---|---|---|---|
| H3 音频 VAE | `minimax_h3_audio_vae_fp32.safetensors` | `vae` | 两档都装 |
| H3 UNet | `minimax_h3_fl2va_pruned_int8_convrot.safetensors`（约 20 GB） | `diffusion_models` | `quant` |
| H3 文本编码器（Qwen3-VL 32B） | `qwen3vl_32b_minimax_h3_int8_convrot.safetensors`（约 26 GB） | `text_encoders` | `quant` |
| H3 视频 VAE | `minimax_h3_video_vae_int8_convrot.safetensors` | `vae` | `quant` |
| 8 步 Turbo LoRA | `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | `loras` | `quant` |
| H3 UNet | `minimax_h3_fl2va_bf16.safetensors` | `diffusion_models` | `bf16` |
| H3 文本编码器 | `qwen3vl_32b_minimax_h3_bf16.safetensors` | `text_encoders` | `bf16` |
| H3 视频 VAE | `minimax_h3_video_vae_fp16.safetensors` | `vae` | `bf16` |
| H3-Image UNet | `minimax_h3_image_pruned_int8_convrot.safetensors` | `diffusion_models` | `WITH_H3_IMAGE=1` |
| H3-Image VAE | `minimax_h3_image_vae_fp16.safetensors` | `vae` | `WITH_H3_IMAGE=1` |
| RelayVSR x2 | `relayvsr_x2_lightx2v_int8_convrot.safetensors`（约 4.8 GB） | `diffusion_models` | `WITH_UPSCALE=1` |
| RelayVSR 解码器 | `relayvsr_flash_vae_x2_fp32.safetensors`（约 122 MB） | `vae` | `WITH_UPSCALE=1` |
| RealESRGAN 通用 2 倍 | `RealESRGAN_x2plus.pth`（约 64 MB） | `upscale_models` | `WITH_UPSCALE=1` |
| RealESRGAN 动漫 4 倍 | `RealESRGAN_x4plus_anime_6B.pth`（约 17 MB） | `upscale_models` | `WITH_UPSCALE=1` |
| Qwen-Image UNet / 文本编码器 / VAE / Lightning LoRA | `qwen_image_2512_fp8_e4m3fn` 等 4 个文件 | 各自目录 | `WITH_QWEN_T2I=1` |

## 超分怎么选

| 方法 | 特点 | 5 秒片段耗时（A100 80GB） |
|---|---|---|
| RelayVSR x2（默认推荐） | 专为 H3 输出训练的 2 倍视频超分，1 步采样，只在稀疏关键帧上采样再流式解码；时间一致性好，保留帧率和音轨 | 约 50 秒 |
| RealESRGAN | 逐帧分块放大；二维线稿更锐利，但更慢，帧间可能闪烁 | 约 92 秒 |

## 手动登录会话

`colab` 的 SSH 走代理模式，不需要密钥：

```bash
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ProxyCommand="colab ssh --proxy-mode -s minimax-h3" root@colab
```

常用检查：

```bash
nvidia-smi                                   # GPU 和显存占用
tail -n 50 /content/comfyui.log              # 服务日志
ls -lh /content/ComfyUI/models/*/            # 模型是否下全（大小为 0 或有 .aria2 文件说明没下完）
pgrep -af "main.py|cloudflared"              # 两个进程是否在跑
```

只重启 ComfyUI（不重新下载）：

```bash
pkill -f "python.*main.py"; cd /content/ComfyUI && \
nohup python3 main.py --listen 0.0.0.0 --port 8188 --enable-cors-header --disable-dynamic-vram \
  > /content/comfyui.log 2>&1 < /dev/null &
```
