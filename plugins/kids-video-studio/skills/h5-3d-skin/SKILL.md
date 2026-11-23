---
name: h5-3d-skin
description: >-
  把 H5 网页动画里的扁平矢量物件、遮挡物和背景换成文生图模型预渲染的 3D 风格图片，并把动作词做成逐帧循环动画，
  让网页动画段落和视频模型生成的镜头画风一致。包含纯色幕布生成加色键抠图、白色和反光物体的抠图参数、前后分层、
  地面阴影，以及“首帧等于尾帧”的图生视频循环动画做法。当用户要给某一集或全季换 3D 风格、新增物件图片、
  修抠图问题（缺边、多抠、残留幕布色）、把跑跳拍手这类动作做成动画时使用。
  Re-skin the data-driven H5 scenes with pre-rendered 3D-style sprites (flat-screen generation + chroma key) and
  looping sprite-sheet animations made with image-to-video using the same image as first and last frame.
---

# H5 动画的 3D 风格换皮和逐帧动画

前置：`kids-video-pipeline`（项目结构和引擎）、本机 `http://127.0.0.1:8188` 上的 ComfyUI 服务（Qwen-Image 或 MiniMax-H3-Image
生图，MiniMax H3 生视频；部署见 `comfyui-h3-cloud` 插件的 `comfyui-h3-colab` / `comfyui-h3-autodl`）。
路径相对用户的项目根目录（用 `/kids-video-studio:init-project` 从模板复制出来的那个目录）。

## 思路

- 网页动画的优点是数量、颜色、文字都准确，缺点是扁平矢量图和视频镜头放在一起像两部片子。
  解决办法不是上真 3D，而是**把每个物件预渲染成一张 3D 风格的透明图**，引擎照旧摆放、移动、缩放。
- 不依赖抠图模型：让生图模型把物件画在**纯色幕布**上，用几十行 numpy 做色键。好处是可复现、可离线重抠。
- 素材全季共用（`assets/skin/`），每集只声明“用不用”和少量覆盖项。去掉开关就回到矢量图，渲染结果和原来一致。

## 文件

```
assets/skin/prompts.json     所有物件、遮挡物、画笔、背景的提示词和选项（唯一数据源）
assets/skin/raw/             模型原图；<名字>_cut.png 是手工抠好的图
assets/skin/<名字>.png       抠好并摆进 200x200 物件框的成品（800x800）
assets/skin/<遮挡物>_front.png  遮挡物的前壁图层
assets/skin/bg_<名字>.jpg    背景
assets/skin/<名字>_anim.png  逐帧动画的精灵表
assets/skin/manifest.json    引擎读取的清单（自动生成）
assets/skin/sheet_N.jpg      带网格的总览拼图，检查用
tools/make_skin.py  make_anim.py  season_lib.py（page_skin）  engine/h5/engine.js（换皮模式）
```

## 给一集开启

`episode.json`：

```json
"skin": true
"skin": {"bg": {"outdoor": "orchard"}}                      // 这一集的户外场景换成果园背景
"skin": {"items": {"rabbit": "rabbit_hop", "dog": "dog_gallop"}}   // 这一集里某个物件换一张图（或换成动画）
```

`tts` 步骤会按本集用到的物件从 `manifest.json` 生成页面配置，所以改了素材或开关后要重跑：

```bash
python -u tools/make_episode.py episodes/<ep> tts capture assemble check
```

手写页面的集（`custom_page: true`）要自己在 `h5/index.html` 里引用这些图，然后只跑 `capture assemble check`。

## 素材规则：先查公共库，默认 3D，动作用视频转动画

素材全项目共用一个库：物件定义在 `engine/h5/*items.js`，3D 图和动画在 `assets/skin/`。

1. **先查库，有就复用**，同一样东西各集长得一样：
   ```bash
   python tools/asset_check.py find socks umbrella     # 已有的物件和类型：anim / 3d / 3d-group / flat
   ```
2. **默认 3D**：新物件一律生成 3D 图，矢量图只是兜底。几样东西有空间关系（球在盒子里、下面、后面）时整体生成一张图，不要叠图。
3. **动词、动作、会动的天气用视频转动画**（见下面“动作词做成逐帧动画”）：静态图孩子分不清跑和跳、开和关。

出片前检查本集，有扁平图或动作词没有动画时会标出来并返回 1：

```bash
python tools/asset_check.py episode episodes/<ep>
```

动作词表在 `asset_check.py` 的 `ACTION_WORDS`，按需要补充。

## 新增或重做一个物件

在 `assets/skin/prompts.json` 的 `items` 里加一条，然后：

```bash
python tools/make_skin.py <名字> --sheet     # 生成 + 抠图 + 更新清单 + 出总览拼图
python tools/make_skin.py --offline          # 不连服务，只重新抠图和拼图（改了抠图参数时用）
python tools/make_skin.py <名字> --force     # 重新生成
```

服务地址可用环境变量 `COMFY_URL` 覆盖。

| 选项 | 作用 |
|---|---|
| `prompt`、`seed` | 只描述物件本身；画风和“纯色幕布、无阴影”由脚本统一追加 |
| `style` | `object`（默认，无脸）/ `animal` / `face`（角色头像）/ `raw`（相框画像等，不追加画风） |
| `key` | 幕布颜色，默认 `blue`；**蓝色的东西用 `green`**（小鸟、鱼、蓝气球、蓝汽车） |
| `keySat` | 0-1。只把饱和度高于它的幕布色当背景。白色或反光的东西用 0.5-0.6 |
| `box` | 物件在引擎 200x200 方框里的位置 `[x0, y0, x1, y1]`，底对齐 |
| `noShadow` | 不画地面阴影（鱼、摊在地上的东西） |
| `rot180` | 生成的图上下颠倒时转回来 |
| `from` + `glow` / `erase` | 派生图：在已有图上画高亮圈（五官）或抹掉一块（没有鼻子的画像）。坐标按总览拼图的网格读，每格 50 |
| `from` + `spot` | 派生图，身体部位用这个：`[[cx, cy, rx, ry], ...]` 里的部位保持原色并加一圈暖黄光边，身体其余部分变灰变浅。比 `glow` 的虚线圈醒目得多，一个列表可以同时标左右两只手 |
| `tone` / `sparkle` | 抠图后调色 `{"mul": [r, g, b], "gamma", "sat"}`、加闪光小星星 `[[x, y, 大小], ...]`。做对比词用：湿袜子调暗调冷，干袜子提亮加闪光。动画在 `video` 里写 `tone`，每一帧都调 |
| `focus` | 指示手指向的位置 |
| 遮挡物的 `front` | `{cx, cy, rx, ry}` 开口椭圆。切出前壁图层后，物件在后壁前面、前壁后面，看起来真的在篮子里 |
| 背景的 `blur`、`ground` | 虚化程度；地面阴影所在的 y |

手工抠好的图放到 `assets/skin/raw/<名字>_cut.png`（透明 PNG）就会原样使用，不再自动抠图。

## 抠图问题怎么判断

| 现象 | 原因 | 做法 |
|---|---|---|
| 白色物体缺一块（白兔的脸颊和尾巴、牛奶杯） | 白色表面反射幕布色，被当成背景 | 加 `keySat: 0.5`（玻璃杯 0.6） |
| 金属、玻璃边缘被吃掉或发蓝 | 镜面把幕布色原样映出来 | 换绿幕；还不行就让用户手工抠一张放到 `raw/<名字>_cut.png` |
| 蓝色物体整个消失 | 和蓝幕同色 | `key: "green"` |
| 边缘有光斑抠不干净 | 提示词里写了方向光 | 提示词不写光的方向 |
| 物件刚出现时被遮挡物挡住 | 遮挡物整体画在物件前面 | 给遮挡物加 `front`，分成后壁和前壁两层 |
| 草地上看不到阴影 | 阴影太淡 | 引擎里的阴影已加深加大；背景的 `ground` 要落在地面上 |
| 问答环节未选中的物件发黑 | 用了降低不透明度 | 引擎用 `grayscale + brightness + opacity` 的滤镜褪色 |

同一个物件自动抠图试两三次还不行，就别再调参数了：把原图交给用户手工抠，比继续试更快。

## 引擎在换皮模式下做的事

图层从后到前：背景 → 光效 → 阴影 → 遮挡物后壁 → 物件 → 遮挡物前壁 → 其余界面。
另外自动加：地面阴影（物件升高时变淡变小）、背景缓慢漂移的视差、物件轻微转动。所有效果仍然是时间的纯函数，逐帧录制结果可复现。

## 动作词做成逐帧动画

动词、动作和会动的天气做成逐帧动画（物件图当首帧 → H3 图生视频 → 逐帧抠图 → 精灵表），做法、选项和踩过的坑见
`video-to-animation` 技能。最短的用法：

```bash
python tools/make_anim.py rabbit_hop        # prompts.json 里带 "video" 的物件；需要本机 8188 的 MiniMax H3 视频服务
python tools/make_skin.py --offline         # 刷新清单
```

## 内容上的经验

- 表情要和起因放在同一屏：开心和冰淇淋一起出现，难过和掉在地上的冰淇淋一起出现。不要让孩子去联想另一屏的东西。
- 生成后必须逐张看总览拼图。见过的问题：香蕉被画上笑脸（提示词写 plain）；“耳朵耷拉”的狐狸变成狗；“两个鸡蛋”只画了一个（写 exactly two）；
  角色长得像某部现有动画的角色（换描述重出，不要用）。
- Colab 会话在没有 SSH 隧道连着时十几分钟就会被回收，出图期间让隧道脚本一直在后台跑。
- 换皮后每集都要重录、重新检查音画同步，并用 `python tools/overview_sheet.py episodes/<ep>` 通览一遍。
