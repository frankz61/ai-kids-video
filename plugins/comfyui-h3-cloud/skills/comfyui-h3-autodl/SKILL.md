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

部署好之后用 `minimax-h3-service-caller` 调用。海外网络可以用 `comfyui-h3-colab`。脚本路径相对本技能目录。

## 思路

模型有几十 GB，每次开机重新下载又慢又费钱。所以把两样东西固化下来：

- **模型**放在该地区的持久化共享存储 `/root/autodl-fs/comfyui_models`，实例释放后还在；
- **环境**（Python、PyTorch、ComfyUI、自定义节点）存成**私有镜像**。

之后每次只需“用私有镜像开一台实例 → 软链模型 → 启动 ComfyUI”，十几秒可用，按小时计费，用完释放。

## 前置

- AutoDL 账号和开发者 Token。Token 存到 `~/.config/autodl/token`（`chmod 600`），或设环境变量 `AUTODL_TOKEN`，
  或用 `--token` 传入。**不要写进仓库或技能文件**。
- 共享存储和私有镜像都按地区隔离：模型放在哪个区，实例就开在哪个区。

## 1. 硬件选择

32 GB 显存是分水岭：带 `--disable-dynamic-vram` 时，约 20 GB 的 UNet 和约 15 GB 的 `nvfp4_awq` 文本编码器可以整个装进显存。
作者实测（32GB 档，当时约 ¥1.68 / 小时，价格和规格以 `stock` 查询结果为准）：

- MiniMax-H3-Image 4MP 6 步出图：约 4 秒
- MiniMax H3 1280x736、124 帧、8 步视频加原生音频：约 3 分钟

## 2. 命令（[autodl_pro_client.py](./scripts/autodl_pro_client.py)，只用标准库）

```bash
python3 scripts/autodl_pro_client.py balance                               # 余额
python3 scripts/autodl_pro_client.py stock --regions westDC3,beijingDC2    # 各区库存和价格
python3 scripts/autodl_pro_client.py list                                  # 现有实例、SSH 信息、计费

# 按规格从便宜到贵尝试，在指定区创建实例并启动 ComfyUI
python3 -u scripts/autodl_pro_client.py create \
  --regions <地区> \
  --specs v-32g-p,v-48g-350w,v-48g,5090d-p,5090-p \
  --image-uuid <你的私有镜像 uuid> \
  --cuda-from 113 \
  --start-command "nohup /root/miniconda3/envs/comfy/bin/python /root/autodl-tmp/ComfyUI/main.py --listen 0.0.0.0 --port 8188 --enable-cors-header --disable-dynamic-vram > /root/autodl-tmp/comfyui.log 2>&1 < /dev/null &"

python3 scripts/autodl_pro_client.py power-off --uuid <实例 uuid>           # 关机
python3 scripts/autodl_pro_client.py power-on  --uuid <实例 uuid> --start-command "..."
python3 scripts/autodl_pro_client.py release   --uuid <实例 uuid>           # 彻底释放
python3 scripts/autodl_pro_client.py save-image --uuid <实例 uuid> --image-name <名字>   # 存成私有镜像
```

`--start-command` 里的 Python 路径取决于你的镜像把环境装在哪里；用 `setup_autodl_h3.sh` 装的是 `/root/miniconda3/bin/python`。
创建会花钱：创建前先 `balance` 和 `stock`，把选中的规格和单价告诉用户。

## 3. 第一次在一个新地区部署

用官方基础镜像开一台 32GB 以上的实例，SSH 上去运行 [setup_autodl_h3.sh](./scripts/setup_autodl_h3.sh)：

```bash
WITH_H3_IMAGE=1 WITH_UPSCALE=1 bash setup_autodl_h3.sh
```

它会：打开 AutoDL 的学术加速来克隆 GitHub 仓库 → 装 ComfyUI 和自定义节点 → 从魔搭（ModelScope）镜像用 aria2c 断点续传下载模型，
沉淀到 `/root/autodl-fs/comfyui_models`（本地盘空间不够时直接下到共享存储）→ 生成一键软链脚本 `link_models.sh` →
启动 ComfyUI，就绪后打印 `COMFYUI_READY_ON_8188`。

确认出图出视频正常后，`save-image` 存成私有镜像，把镜像 uuid 记下来，以后创建实例时用。

## 4. 映射到本机 8188

`list` 会给出实例的 SSH 主机和端口：

```bash
while true; do
  ssh -N -L 0.0.0.0:8188:127.0.0.1:8188 -p <ssh 端口> \
    -o ServerAliveInterval=20 -o ExitOnForwardFailure=yes root@<ssh 主机>
  sleep 5
done
```

免密登录需要先在 AutoDL 控制台配好 SSH 公钥。

## 5. 用完

除非用户说要留着，任务完成就 `power-off`（短期还会再用）或 `release`（不再用），然后 `list` 确认状态，并告诉用户是否已经停止计费。
关机实例的保留期限和存储计费以 AutoDL 当前规则为准；模型在共享存储里，释放实例不影响。

## 常见问题

| 现象 | 做法 |
|---|---|
| 创建时报没有库存 | `--regions`、`--specs` 多给几个；或者换时间 |
| 新实例里找不到模型 | 实例和共享存储不在同一个地区；或者没运行 `link_models.sh` |
| GitHub 克隆很慢 | `source /etc/network_turbo`（脚本已做）；装 Python 包前要取消代理变量 |
| 下载到一半磁盘满 | 脚本在本地盘不足 80 GB 时会直接下到共享存储；也可以设 `DIRECT_SHARED=1` |
