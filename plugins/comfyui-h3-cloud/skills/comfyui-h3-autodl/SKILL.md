---
name: comfyui-h3-autodl
description: >-
  通过 AutoDL 容器实例 Pro 的开发者 API 查余额和库存、按价格从低到高创建 32GB 以上显存的实例、开关机和释放，
  并用持久化共享存储加私有镜像把 ComfyUI + MiniMax H3（视频、生图、超分）做成十几秒就能拉起的服务，再映射到本机 8188。
  当用户要在 AutoDL 上部署或启动 MiniMax H3 / ComfyUI、想用国内算力按小时计费、要查 AutoDL 余额或库存、
  关机或释放实例时使用。
  Create, power on/off and release AutoDL Pro GPU instances through the developer API, and deploy ComfyUI +
  MiniMax H3 with models kept on persistent shared storage and a private image for fast restarts.
---

# 在 AutoDL 上部署 ComfyUI + MiniMax H3

部署好之后用 `minimax-h3-service-caller` 调用。海外网络可以用 `comfyui-h3-colab`。
脚本路径相对本技能目录；目录、模型清单、日志和手动排查见 [reference.md](./reference.md)。

## 思路：第一次慢，以后每次十几秒

模型有 60 多 GB，每次开机重新下载又慢又费钱。所以把两样东西固化下来：

| 固化什么 | 放在哪 | 释放实例后 |
|---|---|---|
| **模型** | 该地区的持久化共享存储 `/root/autodl-fs/comfyui_models` | 还在 |
| **环境**（Python、PyTorch、ComfyUI、自定义节点） | **私有镜像** | 还在 |

```
第一次（每个地区一次；大部分时间花在下载约 65GB 模型上，快慢取决于地区带宽）
  基础镜像开实例 → setup_autodl_h3.sh 装环境、下模型到共享存储 → 验证 → 等模型同步完 → 存私有镜像 → 释放

以后每次（十几秒到一两分钟）
  create --image-uuid <私有镜像> --start-command <软链模型 + 启动 ComfyUI> → SSH 隧道映射 8188 → 干活 → 关机或释放
```

## 0. 前置条件（一次性）

| 要准备的 | 说明 |
|---|---|
| AutoDL 账号并充值 | 容器实例 Pro 按小时计费，创建前余额要够 |
| 开发者 Token | 在 AutoDL 控制台的开发者设置里生成。三种放法，按优先级：`--token` 参数 > 环境变量 `AUTODL_TOKEN` > 文件 `~/.config/autodl/token`。推荐文件，并 `chmod 600`。**不要写进仓库或技能文件** |
| 本机 Python 3.10+ 和 `ssh` | [autodl_pro_client.py](./scripts/autodl_pro_client.py) 只用标准库，不用装依赖 |
| 选定一个地区 | 共享存储和私有镜像都**按地区隔离**：模型放在哪个区，以后实例就开在哪个区 |

存 Token（Linux / WSL / macOS）：

```bash
mkdir -p ~/.config/autodl && printf '%s' '<你的 Token>' > ~/.config/autodl/token && chmod 600 ~/.config/autodl/token
python3 scripts/autodl_pro_client.py balance        # 能显示余额就说明 Token 可用
```

## 1. 硬件和费用

32GB 显存是分水岭：带 `--disable-dynamic-vram` 启动时，约 20GB 的 UNet 和约 15GB 的 `nvfp4_awq` 文本编码器
可以轮流整个装进显存。所以从最便宜的 32GB 规格开始试。

| 规格 ID（`--specs`） | 说明 |
|---|---|
| `v-32g-p` | vGPU 32GB，作者用的档位，当时约 ¥1.68 / 小时 |
| `v-48g-350w`、`v-48g`、`5090d-p`、`5090-p`、`pro6000-p`、`4090D` | 更贵的备选，默认按这个顺序往后试 |

作者在 32GB 档的实测：MiniMax-H3-Image 4MP 6 步出图约 4 秒；MiniMax H3 1280x736、124 帧、8 步视频加原生音频约 3 分钟。
价格和库存会变，以 `stock` 和 `create` 打印的结果为准。

**创建实例会花钱。** 创建前先运行 `balance` 和 `stock`，把选中的地区、规格和单价告诉用户，得到同意再创建。

## 2. 命令速查（[autodl_pro_client.py](./scripts/autodl_pro_client.py)）

| 命令 | 作用 |
|---|---|
| `balance` | 余额 |
| `stock [--regions a,b] [--all]` | 各地区空闲卡数 / 总卡数；`--all` 连没空闲的也列出 |
| `list` | 所有实例：uuid、地区、规格、单价、状态、SSH 命令、root 密码 |
| `create ...` | 按候选地区和规格依次尝试创建，等到运行且 SSH 可用后打印连接信息（最多等约 3 分钟） |
| `power-off --uuid U` | 关机（停止 GPU 计费，实例保留） |
| `power-on --uuid U [--start-command C]` | 带卡开机 |
| `release --uuid U` | 先关机再彻底释放（不可恢复；共享存储里的模型不受影响） |
| `save-image --uuid U --image-name N` | 把实例存成私有镜像 |

`create` 的参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--regions` | `beijingDC2,auto` | 候选地区，逗号分隔；`auto` 表示不限地区（只在没有共享存储依赖时用） |
| `--specs` | 见上表 | 候选规格，按顺序尝试 |
| `--image-uuid` | `base-image-l2t43iu6uk` | 默认是作者测试时用的官方基础镜像；以后换成你的私有镜像 uuid。基础镜像 ID 会更新，创建被拒时去控制台查当前的 |
| `--cuda-from` | `113` | 最低 CUDA 版本要求 |
| `--name` | `minimax-h3-pro` | 实例名 |
| `--start-command` | 空 | 开机后自动执行的命令 |
| `--spec-first` / `--region-first` | `--spec-first` | 先按规格从便宜到贵遍历每个地区（默认），或先固定地区再遍历规格 |
| `--expand-disk` | `0` | 系统盘扩容 GB |

## 3. 第一次在一个地区部署

### 3.1 用基础镜像开一台实例

```bash
python3 scripts/autodl_pro_client.py stock --regions westDC3
python3 -u scripts/autodl_pro_client.py create --regions westDC3 --specs v-32g-p,v-48g
```

成功后打印 `=== PRO INSTANCE READY ===`，下面有实例 uuid、单价、`SSH Command`、`SSH Host/Port` 和 root 密码。
记下 uuid。之后随时可以用 `list` 再查。

### 3.2 上传并运行部署脚本

```bash
scp -P <ssh 端口> scripts/setup_autodl_h3.sh root@<ssh 主机>:/root/
ssh -p <ssh 端口> root@<ssh 主机>                     # 密码用 create / list 打印的 root 密码，或在控制台配好公钥
# 以下在实例里执行；用 tmux 或 nohup，SSH 断了也不会中断下载
sed -i 's/\r$//' /root/setup_autodl_h3.sh
WITH_H3_IMAGE=1 WITH_UPSCALE=1 bash /root/setup_autodl_h3.sh 2>&1 | tee /root/setup.log
```

脚本分 6 步（可以重复运行，已完成的部分会跳过）：

| 步骤 | 做什么 |
|---|---|
| `[1/6]` | 装 aria2、ffmpeg、git、curl |
| `[2/6]` | 打开 AutoDL 学术加速（`/etc/network_turbo`），克隆 ComfyUI 和 3 个自定义节点；下载 RealESRGAN（在 GitHub 上） |
| `[3/6]` | 关掉代理，从腾讯云 PyPI 镜像装 Python 依赖；装完写标记文件 `.deps_installed`，下次跳过 |
| `[4/6]` | 从魔搭（ModelScope）用 aria2c 断点续传下载模型，约 65 GB（全开时）；见下面“模型放哪里” |
| `[5/6]` | 在共享存储里生成 `link_models.sh`，然后启动 ComfyUI（没有 GPU 时到这一步就正常退出） |
| `[6/6]` | 最多等 90 秒服务就绪，打印 `COMFYUI_READY_ON_8188`，并在后台把本地盘上的模型复制到共享存储 |

模型放哪里：

- 共享存储里已经有这个文件 → 直接软链，不下载；
- 数据盘 `/root/autodl-tmp` 剩余不到 80GB（或设了 `DIRECT_SHARED=1`）→ 直接下到共享存储再软链；
- 否则先下到本地盘（更快），服务起来后由后台任务复制到共享存储并换成软链。

文本编码器下载的是 `nvfp4_awq` 版（约 15GB，适合 32GB 显存），脚本会建一个名为 `..._int8_convrot` 的软链指向它，
这样调用端的工作流不用改文件名。

### 3.3 验证

在本机建隧道（见第 5 节），然后：

```bash
curl -s http://127.0.0.1:8188/system_stats | head -c 300
python3 <minimax-h3-service-caller 目录>/scripts/h3_client.py status
```

再用 `minimax-h3-service-caller` 出一张图、一条视频，确认生图、生视频（带声音）、超分都正常。

### 3.4 等模型同步完，再存镜像

**存镜像或释放之前，必须确认后台同步已经结束**，否则共享存储里的模型不全，下次开机会缺文件：

```bash
tail -n 3 /root/autodl-tmp/sync_to_fs.log      # 最后一行是 “[SYNC] All models cached in ... and symlinked.”
ls -lh /root/autodl-fs/comfyui_models/*/       # 没有 .tmp 结尾的文件
```

然后在本机：

```bash
python3 scripts/autodl_pro_client.py save-image --uuid <实例 uuid> --image-name minimax-h3-comfy
```

存镜像需要一段时间（镜像约 12GB），在 AutoDL 控制台的镜像列表里看到状态完成后，记下**私有镜像 uuid**（形如 `image-xxxxxxxxxx`）。
如果 API 提示要先关机，就先 `power-off` 再存。确认镜像可用后，`release` 这台实例。

## 4. 以后每次启动

```bash
python3 scripts/autodl_pro_client.py balance
python3 scripts/autodl_pro_client.py stock --regions <你的地区>
python3 -u scripts/autodl_pro_client.py create \
  --regions <你的地区> \
  --specs v-32g-p,v-48g-350w,v-48g,5090d-p,5090-p \
  --image-uuid <你的私有镜像 uuid> \
  --start-command "bash /root/autodl-fs/comfyui_models/link_models.sh && nohup /root/miniconda3/bin/python /root/autodl-tmp/ComfyUI/main.py --listen 0.0.0.0 --port 8188 --enable-cors-header --disable-dynamic-vram > /root/autodl-tmp/comfyui.log 2>&1 < /dev/null &"
```

- `link_models.sh` 把共享存储里的模型软链到 ComfyUI 的 `models/` 下，重复运行无害。镜像里已有软链时也建议保留这一步，
  防止共享存储里后来新增的模型没链上。
- Python 路径取决于镜像把环境装在哪里：用 `setup_autodl_h3.sh` 装的是 `/root/miniconda3/bin/python`；
  如果你另建了 conda 环境（例如 `comfy`），改成 `/root/miniconda3/envs/comfy/bin/python`。
- 第一次加载模型要从共享存储读几十 GB，第一条任务会比之后慢。

关机后再开机，用 `power-on` 并带同样的 `--start-command`。

## 5. 映射到本机 8188

`create` 和 `list` 会打印 SSH 主机和端口。在本机另开一个终端，让下面的循环一直跑着：

```bash
while true; do
  ssh -N -L 0.0.0.0:8188:127.0.0.1:8188 -p <ssh 端口> \
    -o ServerAliveInterval=20 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
    root@<ssh 主机>
  sleep 5
done
```

要无人值守地重连，需要免密登录：在 AutoDL 控制台配好 SSH 公钥，并加上 `-o BatchMode=yes`。
AutoDL 没有 Colab 那样的“无连接回收”，隧道只负责转发；断了不影响实例上正在跑的任务。

## 6. 用完：关机还是释放

除非用户说要留着，任务完成就处理掉，并用 `list` 确认状态，告诉用户是否已经停止 GPU 计费：

| 情况 | 命令 | 结果 |
|---|---|---|
| 短期内还会再用 | `power-off --uuid U` | 停止 GPU 计费；实例和数据盘保留（保留期限和存储费用以 AutoDL 当前规则为准） |
| 不再用 | `release --uuid U` | 实例删除，不可恢复；共享存储里的模型和私有镜像都还在 |

生成结果先下载到本机：释放后实例本地盘（包括 `ComfyUI/output/`）全部清空。

## 7. 抢卡开机，生成完马上关机

热门卡（如 5090）关机后常常整区没有空闲，`power-on` 直接被拒；空出来的卡几秒内就被别人抢走。用
[power_on_retry.py](./scripts/power_on_retry.py) 每 15 秒试一次，接口说忙时放慢到 30 秒，开成功就退出：

```bash
python3 -u scripts/power_on_retry.py --uuid <实例 uuid> --start-command "<同第 4 节>" > boot.log 2>&1 &
```

开成功的那一刻开始计费，所以只在用户要用机器时跑它。

- **无卡模式只能在控制台开。** API 的 `power_on` 只认带卡开机，传 `non_gpu` 之类的模式会返回“不支持的启动模式”。
  只需要下载模型、不需要 GPU 时，请用户在控制台用“无卡模式开机”，下载完再关掉。
- **开机后第一次加载模型很慢。** 模型在共享存储（网络盘）上，5090 实测第一条任务要额外约 25 分钟读几十 GB。
  估算时间和费用时把这段算进去；一次开机尽量把整批镜头跑完，不要开开关关。
- **把关机写进同一条命令链。** 生成、关机、本机后处理串成一条后台命令，生成完不等人就停止计费：
  `生成整批 && power-off --uuid U && 本机超分 && 本机合成`。超分在本机用 ffmpeg 做
  （`scale=1920:1104:flags=lanczos,crop=1920:1080`，实测和 RelayVSR 模型效果差不多、快得多），不占 GPU 时间。
- 估一批镜头的耗时：生成时间大约和帧数的 1.8 次方成正比。5090 上 4 步 + sol 实测 124 帧 56 秒、209 帧 149 秒、
  362 帧 384 秒；8 步约是它的 1.8 倍。先用一条镜头测，再按帧数推算整批，长镜头拆短更省时间。

## 8. 选哪个量化版本、几步（实测）

2026-11-25 在 RTX 5090 32GB 上用同一条带参考图、参考音频的口型镜头（124 帧，1280×736）测过 Comfy-Org/MiniMax-H3
的几个版本，按预热后的生成时间算：

| 主模型 | 8 步 | 4 步加速包 | 4 步 + sol 解码器 |
|---|---|---|---|
| int8（默认） | 107 秒 | 60 秒 | 56 秒 |
| fp8 | 116 秒 | 64 秒 | |
| w6a8 | 107 秒 | 60 秒 | |

- **量化格式几乎不影响速度**：int8 和 w6a8 一样快，fp8 反而慢 5–10%。w6a8 只是文件小（16GB 对 21GB）。
- **4 步加速包快将近一倍，但不推荐用。** 整集对照看（同一集 15 条镜头，4 步在上、8 步在下同步播放）的结论：
  4 步的镜头会自己切机位、凭空多出人物、画面里冒出乱码字，提示词里的动作常常演不完；8 步镜头连贯、动作完整。
  原因是蒸馏到 4 步后构图在第一步就基本定了，后面没有机会修正。4 步画面看起来更锐、更饱和，也是加速包造成的。
- **sol 解码器只是更快的 VAE**：每条省约 4 秒；同一种子、同一 latent 下和默认解码器的平均像素差只有 3.7/255，看不出区别。
  构图和动作在解码之前就定了，解码器不影响这些。
- 默认用 int8 + 8 步。换版本前照这个办法测：**同一种子**跑出对照（每遍换种子，否则 ComfyUI 直接返回缓存），
  再把整集上下拼在一起从头看到尾，单看几帧看不出 4 步的问题。

## 常见问题

| 现象 | 原因和做法 |
|---|---|
| 创建时所有候选都被拒 | 没有库存。`--regions`、`--specs` 多给几个，或换个时间；看打印的 `code` 和 `msg` |
| 创建被拒，提示镜像不存在 | 私有镜像不在这个地区，或基础镜像 ID 已更新 |
| 实例进入 `starting_failed` / `create_failed` | `create` 会打印快照信息后退出；去控制台看原因，通常是镜像和 CUDA 版本不匹配，调整 `--cuda-from` |
| 新实例里 ComfyUI 报找不到模型 | 实例和共享存储不在同一地区；或者启动命令里没有运行 `link_models.sh` |
| `curl 127.0.0.1:8188` 连不上 | 看 `/root/autodl-tmp/comfyui.log`；检查启动命令里的 Python 路径是否存在 |
| GitHub 克隆很慢或失败 | 脚本已 `source /etc/network_turbo`；手动操作时也要先执行它 |
| 装 Python 包报代理错误 | 学术加速的代理变量还在：`unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY` |
| 下载到一半磁盘满 | 设 `DIRECT_SHARED=1` 重跑，直接下到共享存储；aria2c 会断点续传 |
| 下次开机缺模型 | 上次存镜像或释放时后台同步还没完成。在有模型的实例上补跑同步，或重跑部署脚本 |
| 生成很慢 | 看 ComfyUI 日志是否 `full load: True`，确认启动参数带 `--disable-dynamic-vram`、显存至少 32GB |
| 开机被拒，提示没有可用 GPU | 整区的卡都被占了：用 `scripts/power_on_retry.py` 轮询抢卡（第 7 节） |
| 测速时第二遍只用了一秒 | ComfyUI 对完全相同的工作流直接返回缓存，每遍换一个种子 |
| 系统盘只有 30GB，下载新模型时写满 | 直接下到共享存储 `/root/autodl-fs/comfyui_models/<子目录>`，再运行 `link_models.sh` |
| 模型许可 | MiniMax H3 的社区许可对部署地区有限制，以模型仓库里的 LICENSE 为准，商用前自己确认 |
