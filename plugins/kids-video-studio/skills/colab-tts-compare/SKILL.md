---
name: colab-tts-compare
description: >-
  在 Google Colab 的一台 GPU 上并行安装多个开源语音合成模型（Kokoro、Chatterbox、Orpheus、Dia），用同一份台词各生成一版配音，
  套用和正式配音完全相同的后期处理，再各合成一版对比视频，用来判断开源配音能不能替代商业配音。
  当用户问“能不能换成开源 / 免费的配音”、要对比几种 TTS 的效果、或者要在 Colab 上批量跑开源 TTS 时使用。
  Run several open-source TTS engines side by side on one Colab GPU from the same script lines and build one
  comparison video per voice with identical post-processing.
---

# 在 Colab 上对比开源配音模型

前置：`colab` 命令行工具（见 `comfyui-h3-cloud` 插件里 `comfyui-h3-colab` 的前置一节）。脚本在本技能的 `scripts/`，下面的命令在本技能目录里运行。

## 思路

- 对比的应该是**声音**，不是后期。每个模型的原始输出都走和正式配音一样的处理（去首尾静音、旁白放慢、主角升调、归一化），
  再用各自的时长重录网页动画、重新合成，得到可以直接并排看的成片。
- 各模型的依赖互相冲突，所以**每个模型一个独立虚拟环境**，并行安装。
- `colab exec` 有超时，长任务必须脱离内核在后台跑，本机轮询标记文件。

## 步骤

台词文件 `lines.json` 的格式：`{"键": {"role": "narrator" | "hero", "text": "[tag] words"}}`，和 `episode.json` 的 `lines` 一致。

```bash
# 1. 开一台 GPU（L4 就够，TTS 不需要 A100），会话名默认 tts（环境变量 COLAB_SESSION 可改）
colab new -s tts --gpu L4

# 2. 上传脚本和台词
bash scripts/colab.sh upload scripts/setup_tts.sh /content/tts/setup_tts.sh
bash scripts/colab.sh upload scripts/gen_tts.py   /content/tts/gen_tts.py
bash scripts/colab.sh upload scripts/run_all.sh   /content/tts/run_all.sh
bash scripts/colab.sh upload lines.json           /content/tts/lines.json

# 3. 后台安装（每个模型一个 Python 3.11 虚拟环境），等标记文件出现
bash scripts/colab.sh exec scripts/vm_bg.py 60 "BG_CMD=bash setup_tts.sh" "BG_LOG=/content/tts/setup.log"
bash scripts/wait_for.sh /content/tts/setup.done 20 /content/tts/setup.log

# 4. 后台生成全部模型，结束后打包成 /content/tts/out.tgz
bash scripts/colab.sh exec scripts/vm_bg.py 60 "BG_CMD=bash run_all.sh" "BG_LOG=/content/tts/gen.log"
bash scripts/wait_for.sh /content/tts/gen.done 40 /content/tts/gen.log

# 5. 下载结果，然后释放
bash scripts/colab.sh download /content/tts/out.tgz ./out.tgz
bash scripts/colab.sh stop
```

辅助脚本：`vm_probe.py`（看 GPU、磁盘、工具）、`vm_tail.py`（看日志尾部）、`vm_ps.py`（看进程）、`vm_pack.py`（只打包部分模型的结果）。
`run_all.sh` 可以只跑指定的模型：`bash run_all.sh kokoro chatterbox`。

## 生成脚本做了什么（`gen_tts.py`）

- 方括号情绪标签不念出来；`excited`、`amazed`、`gasps` 这类标签对应更大的表现力参数。
- 每句最多生成 4 次，取第一个**时长合理**的结果。短句上模型容易念多或截断，按文本长度估一个范围来筛。
- 需要参考音色的模型（Chatterbox、Dia）用 Kokoro 生成的参考片段（`refs` 步骤），保证全片同一个声音。
  Dia 不给参考就每次随机换一个声音。

## 本机合成对比视频

`build_variants.py`、`import_variant.py`、`export_lines.py` 是在项目早期写的，绑定的是**手写页面那种集**的结构
（`<集>/audio/tts.py` 里的 `LINES` 和 `to_wav`、`<集>/assemble.py`，并假设脚本放在 `tools/colab_tts/`）。
用在引擎生成的集上需要改成读 `episode.json` 并调用 `season_lib` 的后期函数。流程本身不变：

1. 解包 `out.tgz`，每个模型一份原始 wav；
2. `import_variant.py` 做和正式配音相同的后期，写出 `durations_<模型>.js`；
3. `node tools/capture.mjs <页面> <目录> --dur durations_<模型>.js` 按这套时长重录网页动画；
4. 合成，并用 `audio_lag.py` 检查音画同步。

## 结论（示例项目，儿童英语短句）

- Kokoro、Chatterbox、Orpheus 都能用，但语气的可控性和自然度不如 ElevenLabs，示例项目最后继续用 ElevenLabs。
- Dia 不适合很短的句子（单词级的台词容易出怪声或念错）。
- 这个结论只对“很短、情绪标签多、面向幼儿”的台词成立；成人旁白类长句的结果可能不同，换场景要重新比。

## 踩过的坑

| 现象 | 做法 |
|---|---|
| Chatterbox 安装后导入失败 | 它的水印库依赖 `pkg_resources`，要装 `setuptools<81` |
| `colab exec` 偶尔卡住不返回 | 一律带超时；长任务用 `vm_bg.py` 放后台 |
| Kokoro 第一次运行时去下载 spaCy 模型失败 | 安装阶段先 `python -m spacy download en_core_web_sm` |
| PowerShell 里给 bash 传参数引号出错 | 统一通过 `colab.sh` 这层薄封装调用 |
| 忘了关会话 | 做完立刻 `colab.sh stop`，它会顺带打印 `colab status` |
