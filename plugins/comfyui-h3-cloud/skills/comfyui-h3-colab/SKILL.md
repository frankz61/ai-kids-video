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

部署好之后用 `minimax-h3-service-caller` 调用。国内网络或想按小时计费，用 `comfyui-h3-autodl`。
脚本路径相对本技能目录；装了什么、放在哪、日志在哪，见 [reference.md](./reference.md)。

## 全流程一览

```
本机                                    Colab 会话（A100 / H100）
────                                    ────────────────────────
1. provision_fast_gpu.py  ──申请 GPU──▶  colab new（按顺序试 4 种高速规格）
                          ──上传并运行─▶  setup_colab_h3.sh：装 ComfyUI → 下模型 → 启动 8188 → cloudflared
                          ◀──打印──────  COMFYUI_READY_ON_8188 + trycloudflare 地址
2. keep_ssh_tunnel.sh     ══SSH 隧道══▶  127.0.0.1:8188（同时给会话保活）
3. 验证：curl / h3_client.py status / run_h3_t2v.py 出一条测试视频
4. 干活（minimax-h3-service-caller）
5. colab stop + 停隧道    ──────────▶   会话结束，停止计费
```

整个部署约 5-10 分钟：申请 GPU 几十秒到几分钟，下载模型约 2.5 分钟（`quant`）或 5.5 分钟（`bf16`），装依赖和启动约 2-3 分钟。

## 0. 前置条件（一次性）

| 要准备的 | 说明 |
|---|---|
| Colab 付费账号 | 能申请 A100 / H100。按计算单元计费，用 `colab status` 看余量和消耗速度 |
| `colab` 命令行工具 | `google-colab-cli`，例如 `uv tool install google-colab-cli`；按它的说明完成一次 OAuth 登录 |
| Windows 用户 | 把 `colab` 和下面的脚本都放在 **WSL** 里运行。`colab` 不在 PATH 上时设 `export COLAB_BIN=/path/to/colab` |
| `ssh` 客户端 | 隧道和远程执行都走 `colab ssh --proxy-mode`，不需要额外配密钥 |

先确认登录正常、没有残留会话：

```bash
colab status          # 能列出账号信息；如有不用的旧会话先 colab stop -s <名字>
```

## 1. 选 GPU 和模型档位

**只用高速 GPU，不要用 L4 / T4。** L4 只有 22GB 显存，装不下量化版整套模型，每步约 47 秒，一条 5 秒视频要 8-9 分钟。
脚本申请不到高速 GPU 时直接失败退出，不会降级。

| 申请顺序 | 参数 | 规格 |
|---|---|---|
| 1（首选） | `--gpu A100 --high-mem` | A100 80GB + 约 171GB 内存 |
| 2 | `--gpu H100 --high-mem` | H100 80GB + 大内存 |
| 3 | `--gpu H100` | H100 80GB |
| 4 | `--gpu A100` | A100 40GB + 约 85GB 内存 |

| 模型档位 | 内容 | 下载量和时间 | 采样 | 5 秒 720p 视频（A100 80GB） |
|---|---|---|---|---|
| `quant`（默认，推荐） | INT8 量化 UNet、文本编码器、视频 VAE + 8 步 Turbo LoRA | 约 53 GB，约 2.5 分钟 | 8 步 | 约 109 秒（每步约 13.6 秒） |
| `bf16` | 全精度，不用 LoRA | 约 118 GB，约 5.5 分钟 | 20 步，cfg 4.0 | 约 330 秒 |

两档 ComfyUI 都带 `--disable-dynamic-vram` 启动。原因：默认的动态显存管理不会卸载约 26GB 的文本编码器，
它和约 20GB 的 UNet 同时占着显存；加上这个参数后，文本编码完就卸到内存，UNet 整个装进显存（日志里是 `full load: True`）。

## 2. 一条命令申请并部署

```bash
python3 -u scripts/provision_fast_gpu.py --session minimax-h3 --mode quant --with-h3-image 1 --with-upscale 1
```

| 参数 | 默认 | 作用 |
|---|---|---|
| `--session` / `-s` | `minimax-h3` | 会话名，后面的隧道、释放都用它 |
| `--mode` | `quant` | 模型档位，见上表 |
| `--with-h3-image` | `1` | 装 MiniMax-H3-Image 生图（和视频共用文本编码器，只多下 UNet 和 VAE） |
| `--with-qwen-t2i` | `0` | 另装 Qwen-Image 2512 + 4 步 Lightning LoRA（可选的另一个生图模型） |
| `--with-upscale` | `1` | 装 RelayVSR x2 和 RealESRGAN 超分模型 |
| `--rounds` | `4` | 4 种规格轮流申请几轮 |

脚本做的事：

1. 按上面的顺序 `colab new` 申请 GPU，每次最多等 75 秒；超时会用 `colab status` 确认是不是其实已经分到了。
2. 申请成功后，用 `colab upload` 把 [setup_colab_h3.sh](./scripts/setup_colab_h3.sh) 传到 `/content/`，去掉 Windows 换行符后通过 SSH 执行。
3. 部署脚本分 5 步，日志实时输出到本机终端：

   | 步骤 | 做什么 |
   |---|---|
   | `[1/5]` | `apt` 装 aria2、ffmpeg，下载 cloudflared |
   | `[2/5]` | 克隆 ComfyUI 和 3 个自定义节点（GGUF、VideoHelperSuite、KJNodes），装 Python 依赖，下载 4 个官方工作流模板 |
   | `[3/5]` | aria2c 16 线程从 Hugging Face 下载模型（已存在的文件跳过） |
   | `[4/5]` | 后台启动 ComfyUI，端口 8188 |
   | `[5/5]` | 启动 cloudflared 临时隧道，最多等 80 秒服务就绪 |

成功时最后两行是：

```text
COMFYUI_READY_ON_8188
https://<随机子域名>.trycloudflare.com
```

失败时的退出码：`1` 申请不到高速 GPU，或服务 80 秒内没起来（会打印 ComfyUI 日志）；`2` 账号的 GPU 会话数已到上限（先 `colab status`，停掉不用的）。

> **注意 trycloudflare 地址是公网可访问的，没有密码。** 拿到地址的人都能用你的 GPU。不要把它贴到公开的地方；
> 只用 SSH 隧道时，可以在会话里 `pkill -f "cloudflared tunnel"` 关掉它。

## 3. 把服务映射到本机 8188

另开一个终端（WSL），让隧道一直跑着：

```bash
bash scripts/keep_ssh_tunnel.sh minimax-h3          # 参数：会话名 [本机端口，默认 8188]
```

它在本机监听 `0.0.0.0:8188`，经 `colab ssh --proxy-mode` 转到会话里的 `127.0.0.1:8188`，断线 10 秒后自动重连。

**隧道同时是保活手段。** Colab 会话没有 SSH 连着时，十几分钟就会被回收，模型要重新下载。从部署完成到用完，隧道要一直开着。

Windows 上访问不到 `127.0.0.1:8188` 时（WSL 没有把端口转发给 Windows），改用 WSL 的 IP（在 WSL 里 `hostname -I`）
或 trycloudflare 地址。项目里的脚本用环境变量 `COMFY_URL` 指定服务地址，例如 `COMFY_URL=http://172.x.x.x:8188`。

## 4. 验证服务

按顺序做，前一步通过再做下一步：

```bash
curl -s http://127.0.0.1:8188/system_stats | head -c 300     # 1. 返回 JSON，里面有 GPU 型号和显存
python3 <minimax-h3-service-caller 目录>/scripts/h3_client.py status   # 2. GPU 型号、剩余显存、队列
python3 scripts/run_h3_t2v.py --first-frame test.png \
  --prompt "a small fox waves its paw, birdsong" --output test.mp4      # 3. 出一条 5 秒测试视频
```

第 3 步用任意一张 PNG 当首帧；能拿到带声音的 mp4，说明视频模型、文本编码器、VAE 和音频 VAE 都装对了。
`--mode` 要和部署档位一致（默认 `quant`）。

## 5. 释放（用完就停）

除非用户明确说要留着，任务一完成就释放，并告诉用户服务是否已停止计费：

```bash
colab stop -s minimax-h3
colab status          # 确认没有活动会话
```

然后停掉本机的 `keep_ssh_tunnel.sh`（Ctrl+C，或结束后台进程）。生成结果要先下载到本机：会话释放后 `/content` 里的东西全部消失。

## 常见问题

| 现象 | 原因和做法 |
|---|---|
| 一直申请不到 GPU | 高速 GPU 暂时没货。过一会儿再试，或调大 `--rounds`；不要改成 L4 |
| 退出码 2，提示会话数上限 | `colab status` 找到旧会话，`colab stop -s <名字>` 后重试 |
| 生成到一半连接断开、服务消失 | 会话被回收了（多半是隧道没连着）。重新部署，并保持隧道一直运行 |
| 服务起来了但出错，提示找不到模型 | 下载中断。重新运行部署命令，已下完的文件会跳过 |
| 生成特别慢，每步几十秒 | 看 ComfyUI 日志里是不是 `full load: False`：确认启动参数带 `--disable-dynamic-vram`，GPU 不是 L4 / T4 |
| Windows 访问不到 127.0.0.1:8188 | 用 WSL IP 或 trycloudflare 地址，并设 `COMFY_URL` |
| 手动上传脚本后报 `\r` 相关错误 | 脚本是 Windows 换行。先 `sed -i 's/\r$//' 脚本名` 再运行（`provision_fast_gpu.py` 已自动处理） |
| 想看服务端日志 | 用 [reference.md](./reference.md) 里的 SSH 命令登进会话，`tail -f /content/comfyui.log` |
| 模型许可 | MiniMax H3 的社区许可对部署地区有限制，以模型仓库里的 LICENSE 为准，商用前自己确认 |
