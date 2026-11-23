# AutoDL 部署参考：文件、路径、日志

[SKILL.md](./SKILL.md) 讲流程，这里列出部署脚本具体装了什么、放在哪，排查问题时查这里。

## 脚本

| 文件 | 在哪运行 | 作用 |
|---|---|---|
| [scripts/autodl_pro_client.py](./scripts/autodl_pro_client.py) | 本机 | 调 AutoDL 开发者 API（`https://api.autodl.com`）：余额、库存、实例、开关机、释放、存镜像。只用 Python 标准库 |
| [scripts/setup_autodl_h3.sh](./scripts/setup_autodl_h3.sh) | 实例里 | 装 ComfyUI、从魔搭下载模型到共享存储、启动服务、后台同步。可重复运行 |
| `/root/autodl-fs/comfyui_models/link_models.sh` | 实例里 | 部署脚本生成，放在共享存储里。把共享存储的模型软链到 ComfyUI，参数是 ComfyUI 目录（默认 `/root/autodl-tmp/ComfyUI`） |

部署脚本的环境变量：

| 变量 | 默认 | 作用 |
|---|---|---|
| `WITH_H3_IMAGE` | `1` | MiniMax-H3-Image 生图 |
| `WITH_QWEN_T2I` | `0` | Qwen-Image 2512 生图 |
| `WITH_UPSCALE` | `1` | RelayVSR x2 + RealESRGAN 超分 |
| `DIRECT_SHARED` | `0` | `1` 表示模型一律直接下到共享存储（本地盘不足 80GB 时自动如此） |

AutoDL 版只装量化档（INT8 UNet + `nvfp4_awq` 文本编码器 + 8 步 Turbo LoRA），没有 Colab 版的 `bf16` 选项。

## 实例里的目录

```
/root/autodl-tmp/                  数据盘（释放实例后清空）
  ComfyUI/
    .deps_installed                Python 依赖已装的标记
    custom_nodes/                  ComfyUI-GGUF、ComfyUI-VideoHelperSuite、ComfyUI-KJNodes
    models/<子目录>/<文件>         大多是指向共享存储的软链
    output/                        生成结果
  comfyui.log                      ComfyUI 日志
  sync_to_fs.log                   后台同步日志（存镜像前确认已结束）

/root/autodl-fs/comfyui_models/    同一地区的持久化共享存储（释放实例后还在）
  diffusion_models/  text_encoders/  vae/  loras/  upscale_models/
  link_models.sh
```

## 模型文件

来源：魔搭 `Comfy-Org/MiniMax-H3`、`Comfy-Org/MiniMax-H3-Image`、`Comfy-Org/RelayVSR`、`Comfy-Org/Qwen-Image_ComfyUI`、
`lightx2v/Qwen-Image-Lightning`；RealESRGAN 来自其 GitHub Release（走学术加速）。

| 用途 | 文件 | 目录 | 开关 |
|---|---|---|---|
| H3 音频 VAE | `minimax_h3_audio_vae_fp32.safetensors` | `vae` | 总是 |
| H3 视频 VAE | `minimax_h3_video_vae_int8_convrot.safetensors` | `vae` | 总是 |
| H3 UNet | `minimax_h3_fl2va_pruned_int8_convrot.safetensors`（约 20 GB） | `diffusion_models` | 总是 |
| 8 步 Turbo LoRA | `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | `loras` | 总是 |
| H3 文本编码器 | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`（约 15 GB），另有同目录软链 `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` 指向它 | `text_encoders` | 总是 |
| H3-Image UNet / VAE | `minimax_h3_image_pruned_int8_convrot.safetensors`、`minimax_h3_image_vae_fp16.safetensors` | `diffusion_models` / `vae` | `WITH_H3_IMAGE=1` |
| RelayVSR x2 + 解码器 | `relayvsr_x2_lightx2v_int8_convrot.safetensors`、`relayvsr_flash_vae_x2_fp32.safetensors` | `diffusion_models` / `vae` | `WITH_UPSCALE=1` |
| RealESRGAN | `RealESRGAN_x2plus.pth`、`RealESRGAN_x4plus_anime_6B.pth` | `upscale_models` | `WITH_UPSCALE=1` |
| Qwen-Image 2512 全套 | 4 个文件 | 各自目录 | `WITH_QWEN_T2I=1` |

全开（不含 Qwen-Image）约 65 GB。

## 手动检查

SSH 登录用 `create` / `list` 打印的命令和 root 密码。常用检查：

```bash
nvidia-smi                                         # GPU 和显存占用
tail -n 50 /root/autodl-tmp/comfyui.log            # 服务日志
ls -lL /root/autodl-tmp/ComfyUI/models/*/          # 软链指向的文件是否都在（-L 跟随软链）
find /root/autodl-tmp/ComfyUI/models -xtype l      # 坏掉的软链（有输出就说明缺文件）
ls /root/autodl-fs/comfyui_models/*/ | grep -E '\.aria2$|\.tmp$'   # 没下完或没同步完的文件
pgrep -af main.py                                  # 服务进程
```

手动重启服务：

```bash
pkill -f "python.*main.py"
bash /root/autodl-fs/comfyui_models/link_models.sh
cd /root/autodl-tmp/ComfyUI && nohup /root/miniconda3/bin/python main.py --listen 0.0.0.0 --port 8188 \
  --enable-cors-header --disable-dynamic-vram > /root/autodl-tmp/comfyui.log 2>&1 < /dev/null &
```

## 换一个地区

共享存储和私有镜像都不跨地区。换地区等于在新地区重新做一遍“第一次部署”（SKILL.md 第 3 节）。
