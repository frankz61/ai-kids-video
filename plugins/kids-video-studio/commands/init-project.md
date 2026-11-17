---
description: 把儿童视频项目模板（流水线脚本、H5 引擎、样例集）复制到当前项目目录
argument-hint: "[目标目录，默认当前目录]"
---

把本插件自带的项目模板复制到用户的项目里，之后 `kids-video-pipeline`、`h5-3d-skin`、`video-covers-and-copy` 三个技能都在那个目录里工作。

模板位置：`${CLAUDE_PLUGIN_ROOT}/project-template`
目标目录：`$ARGUMENTS`（没有给就用当前工作目录）

步骤：

1. 先看目标目录里有没有 `tools/`、`engine/`、`episodes/`、`assets/`、`seasons/`。有同名目录时列出会冲突的文件并问用户，**不要覆盖已有文件**。
2. 把模板里的全部内容复制过去，保持目录结构。
3. 在目标目录的 `tools/` 下运行 `npm install`（装 puppeteer-core，用本机的 Chrome 或 Edge 录制网页动画）。
4. 检查并报告缺什么：Python 包（numpy、opencv-python、Pillow、fonttools）、ffmpeg、Node、环境变量 `ELEVENLABS_API_KEY`（只检查是否存在，不要打印它的值）。
5. 告诉用户模板里没有带、需要自己准备的素材：`assets/hero.png`、`assets/fonts/KidsSubSans-Bold.ttf`（用 `tools/make_sub_font.py` 导出）、
   `assets/skin/` 下的图片（按 `h5-3d-skin` 技能生成）。
6. 最后说明下一步：样例集在 `episodes/ep03_fruit` 和 `episodes/ep07_actions`，做新的一集时用 `kids-video-pipeline` 技能。
