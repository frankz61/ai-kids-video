---
name: video-covers-and-copy
description: >-
  为系列短视频的任意一季批量制作封面和发布文案：每集封面和全季封面各出 16:9（1920x1080）和 4:3（1440x1080）两版，
  用 HTML 模板加无头浏览器渲染，配置写在 seasons/<季>/covers.json；按集写标题、简介和标签，并把成片、无字幕版、
  字幕、封面、文案导出成一个可以直接上传的目录。当用户要“做封面 / 重做封面 / 全季封面 / 合集封面 / 4:3 或 16:9 封面 /
  每集的标题和简介 / 季名和简介 / 我要发布这一季 / 导出整季”时使用。
  Batch-render episode and season covers (16:9 and 4:3) for any season from a covers.json, write per-episode titles,
  descriptions and tags, and export the finished season into one upload folder.
---

# 封面、标题和简介，导出整季

前置：`kids-video-pipeline`（各集已出片）。路径相对项目根目录。依赖 Node（`tools/` 下 `npm install`，用本机 Chrome 或 Edge）、
Python（Pillow）、ffmpeg。

## 思路

- 封面是**一张网页的截图**，不是生成图：标题、单词卡片、配色全部由数据决定，整季风格统一，改一个字重新渲染即可。
- 左半边是主角的大图（直接用该集某个 H3 镜头的首帧），右半边是中文大标题、英文副标题和 4 张目标词卡片。
  孩子认主角，家长看标题和词，缩略图缩得很小时也能读。
- 卡片上的物件用和正片同一套图（`assets/skin/`），封面和正片不会两张皮。动画物件用它的静态图。
- 全季封面复用同一个版式，4 张词卡换成每集一个小格。

## 1. 写 `seasons/<季>/covers.json`

样例：项目模板的 `seasons/s01/covers.json`。

```json
{ "code": "S02",                          // 文件名前缀：S02E01_my_bag.mp4
  "ep_tag": "第二季 · 第 {n} 集",          // 左上角 logo 旁的标签
  "export_dir": "../MySeries_Season2",    // 导出目录，相对项目根目录
  "hero": {"width": 1120, "left": -150, "top": 90, "fade_start": 42, "fade_end": 58},       // 16:9 大图位置和右侧渐隐
  "hero_4x3": {"width": 900, "left": -130, "top": 214, "fade_start": 44, "fade_end": 55},  // 4:3 单独调
  "episodes": [                           // 按集数顺序；标题取自各集 episode.json 的 title_zh / title_en
    {"dir": "s02e01_bag", "frame": "shot_01.png",                 // episodes/<dir>/h3/frames/ 里的一张首帧
     "theme": {"primary": "#2C7BE5", "pill": "#EA7B1E", "wash1": "rgba(...)", "wash2": "rgba(...)"},
     "cards": [{"label": "bag", "color": "#2C7BE5", "bg": "#EFF6FF", "items": [["s2_bag", 124, 0, 0, 0]]}, ...]}
     // 卡片物件 = [物件 id, 大小 px, 旋转角度, x 偏移, y 偏移]；数数的卡片放 4-5 个小的并加 "badge": "5"
     // 可选：单集的 "hero" / "hero_4x3" 覆盖默认位置，"rainbow": true 彩虹装饰，"party": true 彩旗
  ],
  "season_cover": {"title_zh": "…", "title_en": "英语启蒙 · Season 2", "tag": "第二季 · 全 12 集",
    "hero_episode": "s02e12_help", "theme": {...},
    "tiles": [["s2_bag", "书包", "#2C7BE5", "#EFF6FF"], ...]}       // 每集一格：物件、两个字的主题、颜色、底色
}
```

选图和选卡片：

- 首帧挑**主角表情最鲜明、手里拿着本集道具**的那张（书包、帽子、火车、彩虹）。主角在画面中间偏左的最合适。
- 卡片就是本集 4 个目标词。复习集没有新词，放 4 个本集考到的旧词（天气、帽子、书包、五只鸭子）。
- 卡片物件和台词一致：台词说 “A car. It's a toy.”，toy 卡片就放小汽车，不要放球。
- 图本身留白多的物件（帽子、公交车）把大小调到 150 左右。

## 2. 渲染

```bash
python tools/make_season_covers.py seasons/s02 covers            # 每集两个比例 → episodes/<ep>/output/<名字>_cover.png、_cover_4x3.png
python tools/make_season_covers.py seasons/s02 season            # 全季 → seasons/s02/cover/season_cover.png、season_cover_4x3.png
```

**渲染后看总览图** `seasons/s02/cover/covers_overview.jpg` 和 `covers_4x3_overview.jpg`，两个比例都看：

- 4:3 比 16:9 窄，主角大图要单独调位置；手里的道具不要伸进右侧卡片区。
- 道具被右侧面板挡住时，换一张首帧或调 `left`。
- 小格左上角的序号不要压住图片：图片缩小一点比挪序号省事。

第一季的老脚本 `make_covers.py`（单集，配置写在脚本里的 `EPISODE_COVERS`）和 `make_season_cover.py` 仍可用，
`make_season_covers.py` 复用它们的版式。物件从 `engine/h5/` 下所有 `*items.js` 读，每季新增的物件文件也能用。

## 3. 标题和简介

每集一份，另加全季（合集）一份，写进 `seasons/<季>/publish_titles.md`（样例见项目模板 `seasons/s01/publish_titles.md`），导出时复制成
`标题与简介.md`。

- **季名**：沿用系列名加“第二季”，频道认得出是同一部；副标题点出这一季的主题。季名没定时先这样写，交付时告诉用户可以改。
- **标题**：`【品类词】主题：本集 4 个目标词｜系列名 第N季 第N集`。目标词是家长最常搜的内容，放在标题里。
- **简介前 50 字**放搜索词：年龄段、零基础、英语启蒙、磨耳朵、本集目标词。很多平台只展示前一两行。
- 之后依次是：一两句故事、句型、互动指令（配中文说明）、本集复现的旧词、配音和字幕语言。
- 复习集的标题和简介里**不出现“复习”**，写成“闯关”“一起玩”“大联欢”，并说明“本集没有新词”。
- 偏好题（“你喜欢面条吗？”）写明没有标准答案；需要对家长说明的内容（家庭构成、活动空间）写进简介。
- 每集配 5-6 个标签；另备一行“本片画面与配音为 AI 辅助制作”，按平台要求加上。
- 时长用 `ffprobe` 读成片，不要估。

写完要核对：简介里提到的每个句型和指令，都要在该集 `episode.json` 的英文台词（`lines.*.text`，去掉方括号情绪标签）里真的出现过。
用几行脚本把台词拼起来做包含检查，核对不上的宁可删掉。不同平台的标题和简介字数上限不同，确定平台后再裁剪。

## 4. 导出整季

```bash
python tools/make_season_covers.py seasons/s02 export [目标目录]   # 默认 covers.json 的 export_dir
```

得到一个能直接上传的目录：

```
S02E01_my_bag.mp4 + S02E01_my_bag.jpg      1080p 字幕版 + 16:9 封面（英文名做文件名，撇号去掉）
nosub/  srt/  covers/  covers_4x3/          无字幕版、字幕文件、PNG 封面、4:3 封面
S02_season_cover.jpg                        全季封面（4:3 在 covers_4x3/）
标题与简介.md
```

导出后确认分辨率（`ffprobe` 看 1920x1080）。交付时说清楚：配音的发音和语气有没有人听过；
上传时要在平台上勾选“AI 生成”声明，儿童内容按平台要求标注。
