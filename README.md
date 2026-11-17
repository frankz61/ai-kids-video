# AI 儿童英语启蒙短视频：制作技能包

一套给 Claude Code 用的插件（两个插件、7 个技能），记录了一部 12 集儿童英语启蒙系列片从剧本到发布的完整做法：
视频模型出剧情镜头，网页动画做教学和互动，配音驱动时间轴，最后合成、加字幕、出封面和文案。

> 状态：整理稿，尚未发布。发布前要做的事见文末“开源前的检查清单”。

## 制作思路

1. **让每种工具只做它擅长的事。** 视频模型擅长角色的情绪和氛围，画不准颜色、数量和文字；网页动画正好相反。
   一集由两者交替拼成：5 秒剧情镜头（MiniMax H3）+ 数据驱动的 H5 动画段落。
2. **一个数据源。** 一集的台词、动画段落、拼接顺序、字幕都在一个 `episode.json` 里。改一句台词，配音、动画时间、字幕一起变。
3. **配音驱动时间轴。** 先配音，动画的每个节拍由配音时长推出；网页的每一帧都是时间的纯函数，逐帧录制，结果可复现。
4. **多模型互审。** 剧本先让三个不同厂商的模型各扮一个角色（课程设计、母语编剧、家长兼制片）提意见，再由另一个模型独立终审。
5. **看得见的检查。** 每一步都产出一张拼图（首帧、镜头抽帧、字幕帧、全片总览）给人或模型看；音画同步用脚本量。
6. **画风统一靠预渲染。** 网页动画里的物件用同一个生图模型预渲染成 3D 风格透明图，动作词做成逐帧循环动画。
7. **算力按需租。** 生图和生视频服务部署在 Colab 或 AutoDL 上，映射到本机一个端口，用完就释放。

## 两个插件

这个仓库是一个 Claude Code 插件市场（`.claude-plugin/marketplace.json`），里面有两个插件，可以分开装。

### comfyui-h3-cloud：租 GPU、部署和调用（通用）

| 技能 | 做什么 |
|---|---|
| [comfyui-h3-colab](plugins/comfyui-h3-cloud/skills/comfyui-h3-colab/SKILL.md) | 在 Google Colab 上部署 ComfyUI + MiniMax H3，映射端口，释放 |
| [comfyui-h3-autodl](plugins/comfyui-h3-cloud/skills/comfyui-h3-autodl/SKILL.md) | 在 AutoDL 上用开发者 API 开实例、持久化模型、私有镜像快速启动 |
| [minimax-h3-service-caller](plugins/comfyui-h3-cloud/skills/minimax-h3-service-caller/SKILL.md) | 调用服务：文生视频、图生视频、分镜批量、1080p 超分 |

### kids-video-studio：儿童视频制作（带项目模板）

| 技能或命令 | 做什么 |
|---|---|
| `/kids-video-studio:init-project` | 把项目模板复制到你的项目目录 |
| [kids-video-pipeline](plugins/kids-video-studio/skills/kids-video-pipeline/SKILL.md) | 一集的完整流程：剧本评审、镜头、配音、H5 动画、合成、检查 |
| [h5-3d-skin](plugins/kids-video-studio/skills/h5-3d-skin/SKILL.md) | H5 物件和背景换成 3D 风格图，动作词做逐帧动画，抠图问题排查 |
| [video-covers-and-copy](plugins/kids-video-studio/skills/video-covers-and-copy/SKILL.md) | 单集封面、全季封面（16:9 和 4:3）、标题和简介、导出整季 |
| [colab-tts-compare](plugins/kids-video-studio/skills/colab-tts-compare/SKILL.md) | 在 Colab 上并排对比多个开源配音模型 |

依赖关系：`kids-video-studio` 出镜头和物件图时需要 `127.0.0.1:8188` 上有服务，这个服务由 `comfyui-h3-cloud` 部署。
两个插件在代码上互不依赖：项目模板自带一份调用脚本 `tools/h3_client.py`（和 `minimax-h3-service-caller` 里的是同一个文件，改一处要同步另一处）。

## 目录

```
.claude-plugin/marketplace.json        市场清单，列出两个插件
plugins/
  comfyui-h3-cloud/
    .claude-plugin/plugin.json
    skills/<3 个技能>/SKILL.md + scripts/
  kids-video-studio/
    .claude-plugin/plugin.json
    commands/init-project.md           复制项目模板的命令
    skills/<4 个技能>/SKILL.md (+ scripts/)
    project-template/                  复制到用户项目里使用
      tools/                流水线脚本（Python + Node）
      engine/h5/            数据驱动的 H5 动画引擎（engine.js、items.js、engine.css）
      episodes/             两集样例：ep03_fruit（基础）、ep07_actions（含逐帧动画）
      assets/skin/prompts.json   全部 3D 风格物件、遮挡物、背景的提示词和抠图参数
      seasons/s01/          季大纲、通用台词、标题与简介样例
```

## 安装和使用

发布到 GitHub 之后，在 Claude Code 里：

```
/plugin marketplace add <你的账号>/<仓库名>
/plugin install comfyui-h3-cloud@ai-kids-video
/plugin install kids-video-studio@ai-kids-video
```

发布前在本机试用：`/plugin marketplace add <这个目录的路径>`，再照上面安装。校验清单：`claude plugin validate .`

然后：

1. 在一个空的项目目录里运行 `/kids-video-studio:init-project`，得到 `tools/`、`engine/`、`episodes/` 等。
2. 环境：Python 3.10+（numpy、opencv-python、Pillow、fonttools）、Node 18+、ffmpeg、本机的 Chrome 或 Edge。
3. 密钥只放环境变量或用户目录下的配置文件：`ELEVENLABS_API_KEY`、`AUTODL_TOKEN`（或 `~/.config/autodl/token`）。
   Colab 用 `colab` 命令行工具自己的登录。不要把任何密钥写进仓库。
4. 说“在 Colab 上启动 H3 服务”“做下一集”“重做封面”之类的话，对应的技能会自动加载；也可以用 `/插件名:技能名` 直接调用。

不用插件机制也可以：把 `plugins/*/skills/` 下的目录复制到自己的 `.claude/skills/`，把 `project-template/` 复制到项目里。

## 没有包含的东西

为了控制体积和避免版权、授权问题，下面这些没有放进来，需要自己生成或准备：

- 生成的图片和视频：`assets/skin/` 下的物件图、背景、动画精灵表（用 `make_skin.py`、`make_anim.py` 按 `prompts.json` 重新生成）；
  主角头像 `assets/hero.png`；各集的镜头、配音缓存、成片和封面。
- 字幕字体 `assets/fonts/KidsSubSans-Bold.ttf`：用 `tools/make_sub_font.py` 从思源黑体导出静态粗体。
- 其余 10 集的 `episode.json` 和镜头提示词，以及评审过程稿。
- 模型权重：由部署脚本从 Hugging Face 或魔搭下载。

## 已知限制

- 脚本从一个真实项目里原样取出，只做了路径脱敏，**在这个目录结构下还没有从头到尾跑过一遍**；插件清单通过了 `claude plugin validate`，但还没有实际安装试用过。
- `colab-tts-compare` 的本机合成脚本绑定早期的手写页面结构，用在引擎生成的集上要改（技能文档里有说明）。
- 性能数字、价格、库存是作者当时的实测值，会变。
- 样例里的角色、台词、提示词是示例系列的内容；做自己的系列要换成自己的角色和设定。

## 开源前的检查清单

- [ ] 选定许可证并加 `LICENSE`（代码和文档可以分开授权），同时填好两个 `plugin.json` 里的 `license`。
- [ ] 仓库地址确定后，在两个 `plugin.json` 里补 `repository`、`homepage`（作者名已填）。
- [ ] 确定市场名（现在是 `ai-kids-video`）和插件名，发布后改名会影响已安装的用户。
- [ ] 决定样例里的角色名、台词、提示词是否一并公开，或换成中性示例。
- [ ] 核对各模型和服务的许可：MiniMax H3 社区许可的地区和商用限制、Qwen-Image、RelayVSR、RealESRGAN、ElevenLabs 的商用条款。
- [ ] 在一台干净的机器上按 README 走一遍，补上依赖版本（`requirements.txt`）。
- [ ] 再搜一遍个人信息：用户名、本机路径、邮箱、私有镜像 ID、任何密钥。
- [ ] 决定文档语言（现在是中文，技能的 `description` 带一句英文）。
