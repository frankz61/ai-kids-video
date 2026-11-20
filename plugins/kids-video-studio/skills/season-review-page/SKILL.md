---
name: season-review-page
description: >-
  给一整季视频生成一个本地快速审查网页：左边切换剧集，播放器可调倍速（0.75-3 倍）、切换 720p 预览 / 1080p 字幕版 /
  无字幕版，按章节（H3 镜头、教学、小测、儿歌、故事）和台词点击跳转，可跳过 H3 镜头、自动下一集，边看边记带时间戳的审查意见并导出 Markdown。
  当用户说“我要快速审查这一季 / 做个预览网页 / 能调倍速切换剧集 / 一次看完全季”时使用；每次重新出片后重新生成。
  Generate a local quick-review page for a whole season: episode switcher, playback speed, chapter and line seeking,
  time-stamped review notes exported as Markdown.
---

# 整季快速审查页

前置：`kids-video-pipeline`（各集已合成，`build/concat.txt` 和 `output/*.srt` 在）。路径相对项目根目录。

```bash
python tools/make_review_page.py seasons/s02        # → seasons/s02/review.html，浏览器直接打开（file://）
```

## 读什么

- 剧集清单：`seasons/<季>/production_manifest.json`（`episodes: [{number, id, path, title}]`）；
  没有清单时，取 `episode.json` 里 `"season"` 等于这一季的所有集（没写 `season` 的算 `s01`），按目录名排序。
- 每集：`episode.json`（中英标题、目标词）、`output/<名字>.srt`（台词）、`build/concat.txt` + 各段时长（章节）、
  `seasons/<季>/previews/<id>_720p.mp4`（有就用，手机和慢网络更快）、`build/overview.jpg`（全片总览，在“总览图”页签）。
- 章节类型由合成顺序里的段名推出：`h3_N` 是 H3 镜头，`teach_*` 教学，`quiz*` 小测，`chant*` 儿歌，`problem` / `solution` 故事。

## 页面功能

- 剧集列表带状态点（未审 / 通过 / 要改），顶部显示已审几集、几集要改，倍速 0.75-3，三种版本切换（换版本保持当前时间）。
- 章节条和图例，点击跳转；台词列表跟随播放高亮，点击跳到那一句。
- 选项：跳过 H3 镜头（只看教学部分）、播完自动下一集。
- 审查意见：按 M 在当前时间插入 `[mm:ss]` 标记，意见和状态存在浏览器的 localStorage，“导出”生成 Markdown，贴给 Claude 改。
- 快捷键：空格播放/暂停，←/→ 5 秒，`[` `]` 调倍速，`,` `.` 上一章/下一章，P / N 上一集/下一集，M 记标记。
- 深色模式，窄屏自动改成上下布局。

## 注意

- **直接用 `file://` 打开**。Python 自带的 `python -m http.server` 不支持 HTTP Range，视频在它下面不能拖动进度条。
  确实要用服务器（比如在另一台设备上看）时用本技能的 `scripts/range_server.py`：
  `python scripts/range_server.py 8765 <项目根目录>`，然后打开 `http://127.0.0.1:8765/seasons/s02/review.html`。
- 页面里的视频是相对路径，不要把 `review.html` 单独挪走。
- 出片脚本跑完后重新生成一次，时长、章节、台词才是最新的（可以在批量出片脚本最后自动调用）。
- 审查意见只存在当前浏览器里，换浏览器或清缓存会丢；看完就导出。
