---
name: comfyui-h3-colab
description: >-
  用本机的 colab 命令行工具在 Google Colab 上申请高速 GPU（A100 / H100，不降级到 L4 / T4），一条命令部署 ComfyUI 和
  MiniMax H3 音视频联合生成模型（量化版 8 步，或 BF16 全精度 20 步）、MiniMax-H3-Image 生图、RelayVSR 和 RealESRGAN 超分，
  把服务映射到本机 8188 端口，用完释放。当用户要在 Colab 上跑 MiniMax H3、ComfyUI、云端生视频、生图、视频超分，
  或者说“启动服务 / 释放”时使用。
  Provision a fast Google Colab GPU with the colab CLI, deploy ComfyUI + MiniMax H3 (video with native audio),
  MiniMax-H3-Image and 1080p upscalers, map it to local port 8188, and release it afterwards.
---

# 在 Google Colab 上部署 ComfyUI + MiniMax H3

部署好之后用 `minimax-h3-service-caller` 调用。国内网络或想按小时计费用 `comfyui-h3-autodl`。

## 前置

- Colab 付费账号（要能申请 A100 / H100）。
- `colab` 命令行工具（`google-colab-cli`，例如 `uv tool install google-colab-cli`），先完成它的 OAuth 登录。
  Windows 上装在 WSL 里；不在 PATH 上时设环境变量 `COLAB_BIN`。
- 本机有 `ssh`。脚本路径相对本技能目录。

## 1. 只用高速 GPU

| 规格 | 命令行参数 | 说明 |
|---|---|---|
| A100 80GB + 大内存（首选） | `--gpu A100 --high-mem` | 量化版每步约 13.6 秒，5 秒 720p 视频采样约 109 秒 |
| H100 80GB | `--gpu H100 --high-mem` / `--gpu H100` | |
| A100 40GB | `--gpu A100` | |

**不要用 L4 / T4**：L4（22GB 显存）装不下量化版整套模型，每步约 47 秒，一条视频 8-9 分钟。脚本申请不到高速 GPU 时会直接失败，不降级。

| 模型档位 | 下载量 | 采样 | 5 秒 720p 耗时（A100 80GB） |
|---|---|---|---|
| `quant`（默认）：INT8 量化 + 8 步 Turbo LoRA | 约 53 GB，约 2.5 分钟 | 8 步 | 约 109 秒 |
| `bf16`：全精度 | 约 118 GB，约 5.5 分钟 | 20 步，cfg 4.0 | 约 330 秒 |

ComfyUI 启动参数固定带 `--disable-dynamic-vram`：默认的动态显存管理不会卸载约 26 GB 的文本编码器，
它和约 20 GB 的 UNet 同时占显存。加上这个参数后，文本编码完就卸到内存，UNet 整个装进显存。

## 2. 一条命令申请并部署

```bash
python3 -u scripts/provision_fast_gpu.py --session minimax-h3 --mode quant --with-h3-image 1 --with-upscale 1
```

它依次尝试 `A100 --high-mem`、`H100 --high-mem`、`H100`、`A100`，申请成功后上传并运行 [setup_colab_h3.sh](./scripts/setup_colab_h3.sh)：
装 ComfyUI 和自定义节点，aria2c 16 线程下载模型，启动服务和 cloudflared 隧道。结束时打印：

```text
COMFYUI_READY_ON_8188
https://<随机子域名>.trycloudflare.com
```

可选项：`--with-qwen-t2i 1` 另装 Qwen-Image（4 步 Lightning，出首帧和物件图用）；`--mode bf16` 全精度。
提示账号已有最大数量的会话时，先 `colab status` 看看，停掉不用的。

## 3. 映射到本机 8188

```bash
bash scripts/keep_ssh_tunnel.sh minimax-h3        # 一直在后台跑，断了自动重连
```

之后 `http://127.0.0.1:8188` 就是服务。隧道跑在 WSL 里而 Windows 访问不到 `127.0.0.1:8188` 时，用 WSL 的 IP
（`hostname -I`）或上面的 trycloudflare 地址；项目脚本用环境变量 `COMFY_URL` 指定。

**隧道还有保活作用**：Colab 会话没有 SSH 连着时，十几分钟就会被回收，模型要重新下载。从部署完成到用完，隧道脚本要一直跑着。

## 4. 已装好的超分模型（`--with-upscale 1`）

| 方法 | 模型 | 特点 | 5 秒片段耗时（A100 80GB） |
|---|---|---|---|
| RelayVSR x2（默认推荐） | `relayvsr_x2_lightx2v_int8_convrot` + `relayvsr_flash_vae_x2_fp32` | 专为 H3 输出做的 2 倍视频超分，1 步采样，时间一致性好，保留帧率和音轨 | 约 50 秒 |
| RealESRGAN | `RealESRGAN_x2plus.pth`、`RealESRGAN_x4plus_anime_6B.pth` | 逐帧放大，二维线稿更锐，较慢 | 约 92 秒 |

## 5. 释放

用完就停，除非用户说要留着：

```bash
colab stop -s minimax-h3
colab status          # 确认没有活动会话
```

同时停掉隧道脚本。会话按计算单元持续计费，交付结果时告诉用户服务是否已释放。

## 常见问题

| 现象 | 做法 |
|---|---|
| 申请一直失败 | 高速 GPU 暂时没货，过一会儿再试；不要改成 L4 |
| 生成到一半连接断开、服务消失 | 会话被回收了（多半是隧道没连着）。重新部署，并保持隧道 |
| Windows 访问不到 127.0.0.1:8188 | 用 WSL IP 或 trycloudflare 地址 |
| 脚本在 Colab 上报 `\r` 相关错误 | 脚本是 CRLF 换行；部署脚本已用 `sed` 去掉，手工上传时注意 |
| 模型许可 | MiniMax H3 的社区许可对部署地区有限制，以模型仓库里的 LICENSE 为准，商用前自己确认 |
