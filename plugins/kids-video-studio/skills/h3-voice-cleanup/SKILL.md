---
name: h3-voice-cleanup
description: >-
  检查并清除 MiniMax H3 镜头自带音轨里的人声：用 faster-whisper 转写每条镜头，标出说了中文、英文胡话或怪话的镜头；
  在 Colab GPU 上用 Demucs 分离人声，只保留环境音给合成用，再复查。当用户说“H3 镜头里有人说话 / 配音有中文 /
  镜头里的声音很奇怪 / 检查镜头原声 / 去掉镜头人声”时使用，也在每批新镜头出片前使用。
  Find H3 shots whose native audio contains speech (Whisper) and strip the voices with Demucs on a Colab GPU, keeping only
  the ambience for the episode mix.
---

# H3 镜头原声检查和人声剥离

前置：`kids-video-pipeline`（镜头已生成）。路径相对项目根目录。剥离一步需要 Colab 会话（`comfyui-h3-cloud` 插件的
`comfyui-h3-colab`，已在跑生视频服务的会话也可以用）。

## 为什么要做

提示词里写了 `no speech, no music`，H3 仍然会时不时给角色配一句话：英文胡话（“Hi, homies!”）、中文（“哇！没想过……”）、
编出来的词。角色的台词由 TTS 配，镜头原声只该是环境音；合成时原声被压低但仍听得见，一部英语启蒙片里冒出一句中文很扎耳。
一季 36 条镜头里实测有一半以上带人声，所以**每批新镜头都要查**。

## 1. 检查

```bash
pip install faster-whisper
python tools/h3_voice_check.py episodes/s02e*                    # 默认 small 模型、CPU，约 3 秒一条
python tools/h3_voice_check.py episodes/s02e* --json h3_voice.json
```

每条镜头一行：`SPEECH`/`ok`、Whisper 判断的语言和置信度、听出的话。有人声的镜头数非 0 时退出码为 1。

判定规则（脚本里）：

- 段落 `no_speech_prob < 0.5` 才算话。
- Whisper 在音乐和底噪上常编出固定句子（“Thank you for watching”、“字幕由……提供”），这些按幻觉忽略。
- 语言置信度低于 0.5 时，少于 3 个词的一段也忽略（底噪被猜成一个单词）。
- 语言是 `zh` 一定有问题；`nn`（没听出语言）通常是干净的。

检查结果只是筛选，**最后要人听**：把标出来的镜头和剥离后的音频给用户试听。

## 2. 剥离

```bash
# Linux / WSL；Colab 会话在跑。会话名默认 minimax-h3，命令行工具不在 PATH 上时设 COLAB_BIN
bash tools/strip_h3_voices.sh episodes/s02e01_bag episodes/s02e02_positions ...
```

脚本抽出每条镜头的音频，打包上传到 Colab，用 Demucs `htdemucs` 两轨分离（人声 / 其余），下载回来写成：

- `episodes/<ep>/h3/amb/shot_NN.wav`：去掉人声的环境音。`assemble_episode.py` 发现它就用它代替镜头原声。
- `episodes/<ep>/h3/amb/shot_NN_removed_vocals.wav`：被去掉的部分，用来听是不是真的只去掉了说话。

整批送也可以（干净的镜头分离后几乎不变），省得挑。36 条在 A100 上约 1 分钟。之后重新合成：
`python -u tools/make_episode.py episodes/<ep> assemble check`。

## 3. 复查

```bash
python tools/h3_voice_check.py episodes/s02e* --amb
```

转写 `h3/amb/` 里的环境音，并打印环境音和被去掉部分的响度。正常结果：全部 `ok`，被去掉的部分比环境音响 10 dB 以上
（说明去掉的确实是说话）。还标出来的镜头：重新生成该镜头，或者整条用静音加通用环境音代替。

## 踩过的坑

| 现象 | 原因 | 做法 |
|---|---|---|
| 加载模型一直卡住、没有输出 | Hugging Face 缓存里的 large-v3 只下载了一半 | 删掉那个模型的缓存，或 `HF_HUB_OFFLINE=1` 只用已下载完整的 `small` |
| `--device cuda` 报找不到 `cublas64_12.dll` | Windows 上没装 CUDA 12 的 cuBLAS | 用 CPU：small 模型足够分辨有没有人说话 |
| Windows 控制台 `UnicodeEncodeError: 'gbk'` | 中文转写结果打到 GBK 控制台 | `PYTHONIOENCODING=utf-8` |
| 管道里看不到进度 | `grep` 等缓冲了输出 | 直接看输出或写文件；脚本本身每行 flush |
| SSH 返回 HTTP 429 | Colab 每个会话只允许一条 SSH 连接，`keep_ssh_tunnel.sh` 正占着 | 先停掉隧道脚本（必要时杀掉远端的 ssh），跑完再开回来 |
| 读 wav 报缺少 `soundfile` | | 脚本用 `scipy.io.wavfile` |

## 相关

- 生成镜头时提示词结尾仍写 `no speech, no music`：能减少，不能杜绝。
- 用完 Colab 记得释放（`colab stop -s <会话>`）。
