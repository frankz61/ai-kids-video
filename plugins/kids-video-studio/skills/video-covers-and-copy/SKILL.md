---
name: video-covers-and-copy
description: >-
  为系列短视频批量制作封面和发布文案：每集封面和全季封面各出 16:9（1920x1080）和 4:3（1440x1080）两版，
  用 HTML 模板加无头浏览器渲染；按集生成标题、简介和标签，并整理成一个导出目录。当用户要“做封面 / 重做封面 /
  全季封面 / 合集封面”、要 4:3 或 16:9 的封面、要每集的标题和简介、或者要导出整季成片时使用。
  Batch-render episode covers and a season cover (16:9 and 4:3) from an HTML template with headless Chrome, write
  per-episode titles, descriptions and tags, and export the finished season into one folder.
---

# 封面、标题和简介

前置：`kids-video-pipeline`（各集已出片）。路径相对用户的项目根目录（用 `/kids-video-studio:init-project` 从模板复制出来的那个目录）。依赖 Node（`tools/` 下 `npm install`，
用本机 Chrome 或 Edge）、Python（Pillow）、ffmpeg。

## 思路

- 封面是**一张网页的截图**，不是生成图：标题、单词卡片、配色全部由数据决定，12 集风格统一，改一个字重新渲染即可。
- 左半边是主角的大图（直接用该集视频镜头的首帧），右半边是中文大标题、英文副标题和 4 张目标词卡片。
  孩子认主角，家长看标题和词，缩略图缩得很小时也能读。
- 卡片上的物件用和正片同一套图（`assets/skin/`），封面和正片不会两张皮。

## 单集封面

```bash
python tools/make_covers.py [导出目录] [--aspect 16x9|4x3|all]      # 默认导出到 <项目>/export
```

每集的配置在 `tools/make_covers.py` 的 `EPISODE_COVERS`：

```python
"ep03_fruit": {
    "frame": "shot_04.png",                       # episodes/<ep>/h3/frames/ 里的一张首帧，当主角大图
    "hero": {"width": 1120, "left": -145, "top": 90, "fade_start": 42, "fade_end": 58},      # 16:9 下大图的位置和右侧渐隐
    "hero_4x3": {"width": 900, "left": -125, "top": 214, "fade_start": 44, "fade_end": 55},  # 4:3 单独调
    "theme": {"primary": "#E8413C", "pill": "#49A842", "wash1": "rgba(...)", "wash2": "rgba(...)"},
    "cards": [{"label": "apple", "color": "#E8413C", "bg": "#FFF2F1", "items": [("apple", 124, 0, 0, 0)]}, ...],
    # 卡片物件 = (物件 id, 大小 px, 旋转角度, x 偏移, y 偏移)；数数的卡片放 2-3 个；可选 "badge": "1"
    # 可选 "rainbow": True（彩虹装饰）、"party": True（彩旗）
}
```

标题取自 `episode.json` 的 `title_zh` / `title_en`，字号按字数自动降档。输出：

- `episodes/<ep>/output/<output_name>_cover.png` 和 `_cover_4x3.png`
- `<导出目录>/S01Exx_<名字>.jpg`（16:9）、`covers/*.png`、`covers_4x3/*.png + *.jpg`
- 两张总览拼图 `season1_covers_overview.jpg` 和 `season1_covers_4x3_overview.jpg`，**渲染后看总览图**

一集里某个物件换了图（`"skin": {"items": {...}}`）时封面会跟着换。

## 全季封面

```bash
python tools/make_season_cover.py [导出目录]
```

配置在脚本顶部的 `SEASON`：标题、副标题、角标文字、主角大图取自哪一集、12 个小格（每集一个：图片、两个字的主题、颜色）。
它复用单集封面的版式，只是把 4 张词卡换成 4x3 的小格。输出 `seasons/s01/cover/season1_cover.png` 和 `_4x3.png`，并复制到导出目录。

## 排版检查

- 4:3 比 16:9 窄，主角大图要单独调位置；手里的道具（画笔）不要伸进右侧卡片区。
- 小格左上角的序号不要压住图片：图片缩小一点比挪序号省事。
- 两个比例都要打开看一眼，不要只看 16:9。

## 标题和简介

每集一份，另加全季（合集）一份，写进 `seasons/s01/publish_titles.md`，再复制到导出目录。样例见项目里的 `seasons/s01/publish_titles.md`。

写法：

- **标题**：`【品类词】主题：本集 4 个目标词｜系列名 第N集`。目标词是家长最常搜的内容，放在标题里。
- **简介前 50 字**放搜索词：年龄段、零基础、英语启蒙、磨耳朵、本集目标词。很多平台只展示前一两行。
- 之后依次是：一两句故事、句型、互动指令（配中文说明）、本集复现的旧词、配音和字幕语言。
- 复习集的标题和简介里**不出现“复习”**，写成“闯关”“一起玩”“大联欢”，并说明“本集没有新词”。
- 需要对家长说明的内容（家庭构成、活动空间）写进简介。
- 每集配 5-6 个标签；另备一行“本片画面与配音为 AI 辅助制作”，按平台要求加上。
- 时长用 `ffprobe` 读成片，不要估。

写完要核对：简介里提到的每个词和指令，都要在该集 `episode.json` 的台词里真的出现过。可以用几行脚本把台词拼起来做包含检查，
核对不上的宁可删掉。不同平台的标题和简介字数上限不同，确定平台后再裁剪。

## 导出整季

```bash
python tools/export_season.py <导出目录>
```

得到：`S01Exx_<名字>.mp4`（带字幕）、`nosub/`（无字幕）、`srt/`、`covers/`、`covers_4x3/`、同名 `.jpg` 封面。
