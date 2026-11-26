---
name: kids-video-pipeline
description: >-
  制作一集儿童英语启蒙短视频的完整工作流：多模型互审加终审定稿剧本，MiniMax H3 生成 5 秒剧情镜头并超分到 1080p，
  数据驱动的 H5 网页动画逐帧录制，ElevenLabs 配音，按采样点精确合成，烧录中英字幕和 AI 生成标识。
  当用户要“做新的一集 / 下一集 / 再做一集某主题”、修改已有一集的剧本、配音、动画、字幕，或者重新出片时使用。
  End-to-end pipeline for one episode of a kids' English video series: script review, MiniMax H3 shots + RelayVSR 1080p,
  data-driven H5 animation capture, TTS, sample-accurate assembly, bilingual subtitles, AI-content marks.
---

# 儿童英语启蒙视频：单集制作工作流

一集 = **H3 漫剧镜头**（剧情和情绪）+ **H5 网页动画**（教学、互动、片头片尾）交替拼接，成片 1920x1080、24fps、约 2.5-3 分钟。
示例项目是一部 12 集的系列片（主角小狐狸 Fenlo，4-6 岁零基础）。代码模板在本插件的 `${CLAUDE_PLUGIN_ROOT}/project-template/`，里面带了两集的
`episode.json` 作样例（第 3 集水果、第 7 集动作），新的一集照着改。

**开始前**：项目里还没有 `tools/make_episode.py` 时，先运行 `/kids-video-studio:init-project` 把模板复制到用户的项目目录。
插件装在 Claude 的插件缓存里，不要在缓存目录里直接出片。下文路径都相对用户的项目根目录。

**思路**：视频模型擅长情绪和氛围，不擅长准确的颜色、数量和文字；网页动画正好相反。所以剧情镜头交给视频模型，教学和互动交给网页动画，两者用同一套配音时间轴拼在一起。

## 0. 目录和工具

```
seasons/s01/
  season_outline_final.md      季大纲（每集目标词、句型、复用关系）
  batchN_scripts_final.md      每批剧本的评审定稿
  common_lines.json            全季通用台词（m_hello、m_bye）
  voice_cache/<sha1>.wav       配音缓存，按 模型+参数+音色+变速+变调+文本 取键，同一句不会重复花字符
  previews/                    720p 预览（给用户在手机上看）
episodes/<epNN_slug>/
  episode.json                 整集的唯一数据源：台词、H5 段落、拼接顺序、字幕中文
  h3/prompts.json              H3 镜头（首帧提示词 + 动作提示词，或 reuse 复用别集的镜头）
  h3/frames/ clips/ clips_1080p/
  audio/tts/  h5/（自动生成，ep01 例外）  build/（可删可重建）
  output/<output_name>.mp4  _nosub.mp4  .srt
engine/h5/                     通用 H5 引擎：engine.js（段落类型）、items.js（物件和图形）、engine.css
tools/
  make_episode.py    一条命令跑完整集的各个步骤（见第 6 节）
  season_lib.py      读 episode.json、配音缓存、ElevenLabs 合成和后期
  assemble_episode.py  通用 1080p 合成
  preview_episode.py   不配音、按估算时长生成 H5 页面，用来先看排版
  make_asset_review.py 素材审核页：合成前逐项审素材，未通过的不让录制
  render_script.py     把 episode.json 渲染成可读剧本，用于评审
  capture.mjs        H5 逐帧录制（--scale 1.5 得到 1080p）
  h3_native.py       H3 图生视频批量（原生节点）
  clip_sheet.py      H3 镜头抽帧总览（每条首/中/尾 3 帧）
  contact_sheet.py / subs_sheet.py / audio_lag.py   检查用
  eleven.py  make_sub_font.py
assets/hero.png                主角头像（H5 片头和 ritual 段用）
assets/fonts/KidsSubSans-Bold.ttf   字幕字体（思源黑体粗体的静态导出，OFL）
```

依赖：Python（numpy、fonttools）、Node（`tools/` 下已装 puppeteer-core，用本机 Chrome/Edge）、ffmpeg。
配音密钥放在环境变量 `ELEVENLABS_API_KEY`，不要写进任何文件。

`episode.json` 里写 `custom_page: true` 的集是手写 H5 页面，流水线会保留它的 `h5/index.html` 不覆盖；其余各集全部由引擎生成。
`tools/new_episode.py` 是旧的复制脚本，只适用于手写页面，新集不要用。

模板里没有带的二进制素材要自己准备：`assets/hero.png`（主角头像）、`assets/fonts/KidsSubSans-Bold.ttf`（运行 `tools/make_sub_font.py`
从思源黑体导出）、`assets/skin/` 下的图片（见 `h5-3d-skin` 技能）。背景音乐由 `assemble_episode.py` 合成，不需要素材。

## 1. 定位

示例系列的设定（做自己的系列时逐条和用户确认）：

- 受众 4-6 岁、母语中文、英语零基础；横屏 16:9。
- 每集 4 个目标词 + 1 个问答句型 + 1 个互动指令；载体名词只靠画面理解，不考核。
- 复习集（第 6、12 集）不引入新的实词；复用的词必须在前面的集里真正教过。
- 主角 Fenlo：橙色小狐狸幼崽，白色尾巴尖，奶白色围巾。角色描述在 `tools/make_episode.py` 的 `CHARACTER`，画风在 `STYLE`，
  提示词里用 `{HERO}` `{STYLE}` 占位，全季一致。
- 正片全英文配音；中英字幕烧录在底部。

## 2. 剧本：初稿 → 多模型互审 → Codex 终审

一般按 3-4 集一批来做。下面的 `mcp__pal__*` 和 `mcp__codex__codex` 是作者环境里调用其他厂商模型的工具，
换成你手头任何能调用不同模型的方式都行，关键是“三个不同厂商、各带一个角色、再加一次独立终审”。

1. 直接写 `episode.json` 和 `h3/prompts.json`（格式见第 5 节，照着同季一集改），
   `python tools/render_script.py episodes/epA episodes/epB > seasons/s01/batchN_draft.md` 渲染成可读剧本。
2. **互审**：用 `mcp__pal__chat` 把渲染出的剧本路径（`absolute_file_paths`）同时发给三个不同厂商的模型，各给一个角色，
   要求问题标 MUST / NICE、给出精确替换台词、限 600 字。先 `mcp__pal__listmodels` 看当时可用的模型。第一季的分工：
   - 少儿英语课程设计师（教学法、词汇难度、重复次数、和前面各集的衔接）
   - 英语母语的儿童节目编剧（台词是否地道、节奏、情绪弧线、内容安全）
   - 中国家长兼制片人（孩子会不会看下去、家长视角的敏感点、AI 生成的制作风险）
3. 把采纳的意见改进 `episode.json`（多处修改写成 Python 补丁脚本），重新渲染。
4. **终审**：`mcp__codex__codex`（`sandbox: read-only`，`cwd` 设为项目根），要求给出“通过 / 有条件通过 / 不通过”，
   只列必须修改的条目（段落 id + 精确替换文本）。
5. 按终审修改，渲染存为 `seasons/s01/batchN_scripts_final.md`。

### 已经验证过的剧本规则（直接沿用）

- **H3 镜头里只有主角一个角色**，不要求精确道具、精确颜色，不做口型台词；台词都是画外音。
- 所有需要“颜色准确”“多个物体”“文字”的画面放 H5。
- 教学顺序：先呈现，再提问，再回答；**问句后停 2 秒，指令后停 4 秒**，示范轮也停 4 秒。“Do you like …?” 这类偏好问句按问句算 2 秒，不加指示手。
- 每次跟读后留空白；互动段第一轮先示范一次；停顿期间不提前高亮答案。
- 反馈用 “Here! It's red!”，不用无条件的 “Yes!”。
- 数数只到 3；避免 friend/me/four/five/picnic/birthday/party/cake/gift 这类超纲词。
- 家庭类内容加 `parent_note`（每个家庭都不一样）；动作类加安全提示 `notes`。
- 不使用高频闪烁；魔法效果不要表现成往动物身上涂颜料。
- 停顿只许加长，不许压缩。实际时长以配音合成后的音频长度为准。

## 3. H3 漫剧镜头（含 1080p 超分）

服务是映射到本机 `http://127.0.0.1:8188` 的 ComfyUI（部署见 `comfyui-h3-colab` 或 `comfyui-h3-autodl`，调用和超分见 `minimax-h3-service-caller`，都在 `comfyui-h3-cloud` 插件里；
项目的 `tools/h3_client.py` 是同一个调用脚本的副本）。

```powershell
python tools/h3_client.py status   # 先确认服务通
python -u tools/make_episode.py episodes/<ep> frames          # Qwen-Image 出首帧，Read 看一遍再继续
python -u tools/make_episode.py episodes/<ep> clips upscale   # 后台运行
python tools/clip_sheet.py check.jpg episodes/<ep>/h3/clips_1080p/shot_01.mp4 ...
```

- `prompts.json` 每个镜头：`id`、`image_prompt`（首帧）、`prompt_en`（动作 + 环境音，结尾写 `no speech, no music`），
  可选 `image_seed` / `video_seed`；或者只写 `reuse: "../epXX/h3/clips_1080p/shot_NN.mp4"` 复用别集的镜头。
- 输出 1280x736、124 帧；`upscale` 用 RelayVSR x2，再居中裁成 1920x1080（约 50 秒一条，保留音轨）。
- 耗时（A100）：首帧几秒，视频每条 2-4 分钟，超分约 50 秒。
- **超分可以不用模型，在本机做。** 用户对比过，ffmpeg 放大和 RelayVSR 效果差不多、快得多，还不占按小时计费的 GPU：
  `ffmpeg -i in.mp4 -vf "scale=1920:1104:flags=lanczos,crop=1920:1080" -c:v libx264 -crf 16 -c:a copy out.mp4`
  （想更锐可以再加 `,unsharp=5:5:0.7`）。GPU 只用来生成，整批生成完马上关机，再在本机超分。
- **用 8 步，不用 4 步加速包。** 4 步快将近一倍，但整集对照看，镜头会自己切机位、多出人物、冒出乱码字，动作演不完
  （测试和结论见 `comfyui-h3-autodl` 第 8 节）。
- **改了某个镜头的提示词或种子，直接重跑**：`frames/shot_NN.sig` 记录提示词签名，签名变了会自动删掉该镜头的首帧、视频和超分结果并重新生成。
- 出片后一定用 `clip_sheet.py` 看首/中/尾帧，有问题的再用 `ffmpeg -vf "select='not(mod(n\,20))',tile=3x2"` 抽更密的帧确认。
- **再查镜头原声**：H3 常常自己配一句话（英文胡话、中文），`python tools/h3_voice_check.py episodes/<ep>` 标出来，
  `tools/strip_h3_voices.sh` 在 Colab 上去掉人声，合成时自动改用 `h3/amb/` 里的环境音。见 `h3-voice-cleanup` 技能。

## 4. 配音（ElevenLabs）

台词在 `episode.json` 的 `lines`：`{"key": {"role": "narrator"|"hero", "text": "...", "zh": "..."}}`，键名约定 `n_` 旁白、`m_` 主角。

```powershell
python -u tools/make_episode.py episodes/<ep> tts
```

- 模型 `eleven_v4`，参数 `stability 0.4`、`similarity_boost 0.75`；不支持语速和 SSML。
- 用方括号情绪标签控制语气，标签不会被念出来：`[excited]` `[curious]` `[playfully]` `[gasps]` 等。
- 旁白 Jessica，后期放慢 7%；主角 Laura 升调 14% 模拟童声。
- **重复的词要各录一遍**（`n_red_1`、`n_red_2`，不同标签），不要同一个文件放两次。
- 后期：去首尾静音、归一化到 -3 dBFS、时长异常自动重录；写出 `audio/tts`、`durations.json`、`h5/durations.js`、`h5/episode.js`。
- 全季缓存在 `seasons/s01/voice_cache`，改一句只重录那一句。一集约 800-1,000 字符。
- **免费套餐录的音不能商用**。要发布就用付费套餐；换过账号或套餐后，清掉对应缓存重录。

### 开源配音对比（已做过，结论是继续用 ElevenLabs）

见 `colab-tts-compare` 技能：在 Colab 上生成 Kokoro / Chatterbox / Orpheus / Dia 各一版对比视频。
结论：Kokoro、Chatterbox、Orpheus 能用但不如 ElevenLabs；Dia 不适合短句。

## 5. H5 动画（数据驱动引擎）

`episode.json` 的结构：

```json
{ "id": "ep03_fruit", "output_name": "ep03_...", "title_en": "...", "title_zh": "...", "bg": "outdoor|indoor|party",
  "lines": { ... },
  "segments": [ {"id": "intro", "type": "intro"}, {"id": "ritual", "type": "ritual"}, {"id": "apple", "type": "teach", ...},
                {"id": "quiz", "type": "quiz", ...}, {"id": "chant", "type": "chant", ...}, {"id": "outro", "type": "outro", ...} ],
  "order": [ ["h5", "intro"], ["h3", 1, [["n_line", 0.5]]], ["h5", "ritual"], ... ],
  "parent_note": "可选，片头给家长的一行中文", "notes": {"segments": ["jump"], "text": "可选，某几段的安全提示"} }
```

段落类型（实现见 `engine/h5/engine.js`）：

- `intro`：画笔仪式、彩虹、FENLO 字母，主角说 `m_hello`。`ritual`：主角头像 + 画笔升起 + 光爆（第一季取代了 H3 第 2 镜）。
- `teach`：`item` / `items` / `count`；出现方式 `reveal: draw|pop|color|peek`（peek 用 `cover` 篮子或灌木）；
  `scale` `scales[]` `gap` `x` `y`（物件行高度，默认 360）`wordX` `wordY`（默认 350）`wordMax`（单词最大宽度，默认 600）`stagger` `word` `color`
  （多个物件并排、单词放中间时用 `wordY` 把单词放到物件下方，否则会压住物件）；`ghost[]` 先显示淡轮廓直到 `fill` 节拍；`swapTo` 在 `fill` 时换成另一个物件。
  节拍 `beats`：`{say, q, word, pulse, act, countPulse, point, grow, show, fill, hold, after}`。
- `quiz`：`items`（字符串或 `{key, id, scale, word}`），`rounds`：`{target, ask, answer（可为数组，依次说出）, demo, wait, act, word}`。
- `chant`：`items` + `lines {say, item, word}`，`repeat`、`gap`；分组模式 `lines {say, show[], word, color, scale}` 用于数数。
- `outro`：`items` `words` `scales`，标签宽度自动按列宽缩放。
- 物件在 `engine/h5/items.js`（`window.ITEMS`、`window.COVERS`）：颜色、水果、动物、脸部五官、家人头像、情绪脸、早餐、玩具等；
  新物件写成 SVG 函数加进去。`idleMotion`（float/swim/bob）和 `actMotion`（hop/run/swim/clap/wiggle）控制动作。

约定：

- **每一帧都是时间的纯函数**：不用 CSS 动画、`setTimeout`、`Math.random()`。页面暴露 `window.SEGMENTS` 和 `window.renderAt(id, 秒)`。
- 时间轴由配音时长推出，换配音后动画自动对齐。
- 舞台 1280x720（录制时 deviceScaleFactor 1.5 → 1080p）。底部 `y > 610` 是字幕区，左上角是 AI 标识，不要放元素。
- 先跑 `python tools/preview_episode.py episodes/<ep>`（估算时长），浏览器打开 `h5/index.html?seg=<id>` 或
  `node tools/capture.mjs <page> <dir> --still <seg>:<秒>` 截静帧看排版，确认后再配音和录制。

### 数数的高亮对准“念到数字”的那一刻

数数段（“一、二、三……”）的高亮、数字牌、指示手要落在每个数字念出来的瞬间，不能按整句时长平均分。做法：

1. **先用音量起点**：把这句配音按 10 毫秒算能量，超过峰值 8% 的位置算一个音节起点，相隔不到 0.32 秒的并成一个。
   每个数字是一个短音节，这样找到的起点就是数字的时刻，比 Whisper 的词时间戳准。
2. **按这句的结构取起点**，在剧集数据里给每句写一项 `[取法, 个数]`：
   - `first N`：句子以数数开头（“一、二、三！三个！”），取前 N 个；
   - `last N`：数数前面还有话（“我们一个一个点：一、二、三、四、五、六。”），取后 N 个；
   - `all N`：整句只有数字（“一……二……三……”）。拖长的字有时被切成两段、多出一个起点，这时反复删掉间隔最小那一对里靠后的一个，直到剩 N 个。
3. 起点不够 N 个才用 Whisper 词时间戳兜底，还不够就按整句平均分。**Whisper 会把重复的数字吞掉**（“三……三、四”只认出一个“三”），
   所以剧本故意让角色数错、数两遍时，一定要用音量起点。
4. 剧情里数错的情况（同一个东西点了两次），写一张“第几个数字 → 落在哪个物体上”的表，标签照念出来的数字写，让孩子能看见错在哪。

### 动画还没做时先出草片

H3 镜头和配音都有了、H5 还没做时，先拼一版草片给用户看节奏和配音：H3 镜头配上台词；每个 H5 段用它的底图做成一张卡片，
左上角写“H5 · 段名（动画待做）”，按台词时长和停顿播放。几分钟就能出，能早点发现台词太长、停顿不对、镜头不够长的问题，
不用等动画全做完。

## 5.6 素材审核页：用户审完素材再合成（必做）

素材（3D 物件图、动画、背景、H3 首帧和镜头）全部生成、`tts` 写好 `h5/episode.js` 之后，先让用户审素材，再录制合成。
否则像“土豆像石头、玉米叶子被抠掉、H3 镜头里多出一个人”这类问题要到看成片才发现，素材和成片都得返工。

```bash
python tools/make_asset_review.py seasons/<季> --serve      # 打开打印出的 http://127.0.0.1:8770/... ，审核结果自动存盘
python tools/make_asset_review.py seasons/<季> --check       # 全季是否都通过（--check <集名> 只看某几集）
```

- 列出每集真正录制和合成用到的素材：`h5/episode.js` 里的物件图、动画（循环 + 静态图 + 原始视频）、背景，`order` 里每条 H3 镜头（首帧 + 片段 + 提示词）。
  物件图同时显示抠图结果（紫格 / 白 / 黑底）和原图。
- 每项“通过”或“重做”（重做必须写意见），可导出重做清单（意见、提示词、重做命令）。素材重新生成后自动回到待审（按文件内容哈希比对）。
- 必审 = 本季前缀（如 `s3_`）的物件和背景、本季各集的 H3 镜头；旧素材只供参考。
- 关卡：`make_episode.py ... capture` 先检查本集素材，有未审、重做、缺文件或审核后又改过的就停下（结果在 `seasons/<季>/asset_review.json`）。
  只有生成过 `asset_review.html` 的季才启用；确需跳过设 `ASSET_REVIEW=skip`。
- 不用 `--serve` 直接打开 html 也能审，结果存在浏览器里，审完点“导出 JSON”存成上面的文件。

## 6. 一键出片和验证

```powershell
python -u tools/make_episode.py episodes/<ep>                       # 全部步骤
python -u tools/make_episode.py episodes/<ep> capture assemble check  # 只重录 H5 并重新合成
```

`assemble`：每段出无声视频 + PCM 音频（每句配音先按有声部分 RMS 统一到 -17 dB；H3 镜头自带的环境音统一到 -34 dB RMS，
有人说话时压低到 45%）→ 视频按帧拼接 → 音轨按采样点拼成一条（numpy 混音）→ 背景音乐 → 整轨 loudnorm -16 LUFS →
只编码一次 → 烧录 AI 标识、片尾署名、家长提示、中英字幕。输出字幕版、无字幕版和 `.srt`。

`check` 会跑 `audio_lag.py` 并生成 `build/check_subs.jpg`，每次都要看：

- 每个窗口的 lag 必须是 0 毫秒；分辨率 1920x1080；音视频两条流时长相等。
- 字幕帧总览：字幕没被画面挡住、中英对照正确、物件没有出界或重叠。
- **听不到声音**：发音、语气、有没有怪声只能请用户听，交付时明确说出来。

发给用户看时，用 ffmpeg 压一版 720p（`-vf scale=1280:720 -crf 27`）放到 `seasons/s01/previews/`，1080p 母版对手机端来说太大。
每集出片后再跑 `python tools/overview_sheet.py episodes/<ep>`，生成 `build/overview.jpg` 通览全片。
整季给用户审：`python tools/make_review_page.py seasons/<季>` 生成一个本地网页，切剧集、调倍速、按章节和台词跳转、记意见（`season-review-page` 技能）。

## 7. 发布前

已内置的：开源字体、左上角“内容由AI生成”、片尾 `Video: MiniMax H3 · Qwen-Image  Voice: ElevenLabs`、文件元数据说明。
需要用户做的：

- 确认 MiniMax H3 社区许可的部署地区限制（报道称不允许在美国、欧盟、英国、韩国本地部署），以 Hugging Face 上的 LICENSE 为准。
- 国内平台上传时勾选“AI 生成”声明；YouTube 标记为“面向儿童”。
- 新角色名、新频道名先检索同名儿童内容和商标。

## 踩过的坑

| 现象 | 原因 | 做法 |
|---|---|---|
| H3 镜头里狐狸有两条尾巴 | Qwen-Image 首帧在“正面全身 + 手里拿东西”的姿势下反复画出两条尾巴，换种子、写“exactly one tail”都没用 | 先看首帧；不行就改构图，比如胸部以上的中近景让尾巴出画 |
| H3 镜头比 H5 段落响约 11 dB | 早期把 H3 环境音放大 4 倍再限幅，超分后的片段环境音本身就不小，几乎顶满 | 环境音按固定电平拉齐并在台词下压低（`level_ambience`）；配音按响度而不是峰值对齐（`level_voice`）。用 ebur128 逐段测，H3/H5 段落应在 ±2 dB 内 |
| 合成时某一段 ffmpeg 一直不结束、没有任何输出 | ffmpeg 的 `amix` 在后台运行时偶发死锁 | 用 numpy 按采样点叠加（`mix_cues`）；所有 ffmpeg 加 `-nostdin` 和超时 |
| 播放时 H5 和 H3 切换后音画错开 | 每段单独编码 AAC 再拼接，接缝处音频时间戳不连续 | 音频全程 PCM，按采样点拼成一条，最后只编码一次。**不要改回分段 AAC** |
| 改了镜头提示词，后台任务还是用旧首帧出片 | 已有的首帧和视频被当成“已完成”跳过 | 现在靠 `shot_NN.sig` 自动失效；手动改文件时记得删旧的首帧/视频/超分 |
| H3 工作流被拒，HTTP 400 | 服务端是 ComfyUI 原生 H3 节点 | 用 `tools/h3_native.py` 或已更新的 `h3_client.py` |
| 字幕字很细或变成别的字体 | 字幕渲染库不支持可变字体的字重 | 用 `tools/make_sub_font.py` 导出的静态粗体，`fontsdir` 指向 `assets/fonts` |
| ffmpeg `drawtext` 报 Fontconfig 错误 | 本机 ffmpeg 没有 fontconfig 配置 | 不用 `drawtext`，文字一律走 ASS 字幕 |
| 片尾多个相同物件只显示一个 | 同一个物件 id 在页面里重复 | 引擎已改成复制节点；新段落类型也要注意 |
| 镜头里角色自己说了一句中文或英文胡话 | 提示词写了 no speech，H3 仍会配话 | `h3_voice_check.py` 查、`strip_h3_voices.sh` 去人声（`h3-voice-cleanup`） |
| 静态图分不清跑和跳、开和关 | 动作要看到才懂 | 动词和会动的天气做成逐帧动画（`video-to-animation`） |
| 难过的表情看起来像生气 | 眉毛朝中间向下倾斜 | 眉毛内端朝上 |
| PowerShell 里自定义函数 `R` 不执行 | `R` 是 `Invoke-History` 的别名 | 多处文本替换写成 Python 脚本，带出现次数断言 |
| ffmpeg 按小数秒定位失败 | PowerShell 把小数格式化成了本地格式 | 用 `InvariantCulture` 格式化，或在 Python 里调 ffmpeg |
| 互相关检测给出离谱的偏移 | 重复的短词会匹配到另一次出现 | 用 `audio_lag.py`（整段包络对比），不要逐句匹配 |
| 中文长字幕一整行冲出画面两边 | libass 只在空格处换行，中文没有空格，永远不换行 | 超过一行能放下的字数（56 号字、左右边距 80 时约 24 个字）就在句号、问号、感叹号、省略号处拆成几条依次显示，每条按字数分这句的时长；还太长再在逗号、冒号处拆。**不要在顿号处拆**，否则“一、二、三、四、”和“五、六”会被分到两条里 |
| 数数高亮和念的数字对不上 | 按整句时长平均分；或者用了 Whisper，重复的数字被吞掉 | 用音量起点找每个数字（见第 5 节“数数的高亮”） |

## 相关技能

- `h5-3d-skin`：把 H5 段落的物件和背景换成 3D 风格图片；先查公共素材库（`tools/asset_check.py`）。
- `video-to-animation`：动作词、开关推拉、会动的天气做成逐帧动画。
- `h3-voice-cleanup`：查出并去掉 H3 镜头原声里的人声。
- `season-review-page`：整季快速审查网页。
- `video-covers-and-copy`：任意一季的单集封面、全季封面、标题和简介，导出上传目录。
- `comfyui-h3-cloud` 插件的 `comfyui-h3-colab` / `comfyui-h3-autodl`：部署生图和生视频服务；`minimax-h3-service-caller`：调用服务（首帧、视频、超分）。
- `colab-tts-compare`：开源配音模型对比。
