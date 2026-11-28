---
name: anim-explainer-video
description: 将一个技术主题做成带配音与字幕的讲解型动画视频（1080p/30fps）。采用契约驱动的 audio-first 管线：storyboard.json 为唯一事实源，逐句 TTS 实测时长驱动时间轴，确定性 Canvas 逐帧渲染，强制画面质检。当用户要求"做讲解动画视频""把某主题做成动画""生成教学视频"时使用本 Skill；不适用于真人实拍、照片级 3D 或复刻已有视频。
---

# Anim Explainer Video（v2 · 契约驱动重构版）

> **启动自检（重要）**：执行前先用文件读取工具直接打开本文件的绝对路径，确认开头为 `v2 · 契约驱动重构版` 且正文包含 `audio-first` 与 `storyboard.json`。若通过 `@skill` 加载到的仍是含 `12fps 插帧`、`references/storyboard-guide.md` 的旧文本，那是会话启动时缓存的旧版本，**不要照旧文执行**；以磁盘上的 v2 文件为准，并重新读取 `references/` 与 `scripts/`。此缓存只影响当前会话的文本加载，不影响任何脚本与产出。

## 概览

流程：**初始化 → 知识检索 ✋ → 动画设计 ✋ → 配音与样片 ✋ → 批量渲染与合成**。
每个场景是一个纯函数 `render(ctx, t, S)`，`t` 为场景内 0~1 进度；以原生 30fps 逐帧渲染（不做插帧），保证文字锐利、可复现、可单场景返工。

### 五条铁律（不得跳过）

1. **三个卡点必须人工确认**：知识资料、动画设计（含解说词定稿）、关键帧与样片。用户明确说"确认/通过/可以"才进入下一阶段；有修改意见则改完重新提交。解说词在卡点 2 定稿，之后改词意味着重新配音并重排全片帧号，必须回到卡点 2。
2. **Audio-first**：先逐句合成 TTS、用实测采样数得到每句精确起止（`audio/timeline.json`），再由它决定帧数与字幕时间。禁止估算时长、禁止先定帧数再配音。
3. **契约驱动**：`storyboard.json` 是唯一事实源。渲染脚本不得自行发明时间、字幕或数字；屏幕上的每个数字/术语必须能追溯到 `research.md`。任何偏差记录为 `deviation` 并询问用户，不得静默修改。
4. **确定性渲染**：`render(ctx,t,S)` 必须是纯函数——禁用 `Date.now()`、未播种随机、渲染期联网；字体先加载完成再截帧；同一帧重渲结果一致。
5. **必须看画面**：关键帧、样片、成片都要实际查看（contact sheet + 布局检查 + ffprobe）。"旁白说 D=10、画面写 D=8"这类错误只能靠看帧发现。

## 默认配置

| 参数 | 默认 |
|---|---|
| 时长 | 3~5 分钟（用户可指定） |
| 分辨率/帧率 | 1920×1080 / 30fps 原生逐帧（**不插帧**） |
| 语言 | 中文（旁白+字幕） |
| 渲染器 | Canvas 2D + Playwright 无头 Chromium；封面/氛围图可用 AI 生图 |
| TTS | 默认 edge-tts（免费，逐句合成+词级边界）；可选 Azure / ElevenLabs 升档 |
| 音色 | `zh-CN-YunxiNeural`（年轻男声，讲解自然）；卡点 3 提供 2~3 个试听 |
| 字幕 | 烧录在画布内，按句出现、按词高亮（词级边界来自 TTS） |
| 场景转场 | 合成器统一加 350ms 转场；推荐 `--transition mixed`（fade/slideleft/wipeleft 交替），避免全片只有淡入淡出 |
| 画面运动 | 运行时强制叠加持续镜头推拉/微位移/视差点阵/扫描光，字幕层不受影响；QA 会检测相邻帧是否真的在动 |
| 中间产物 | 成片后运行 `cleanup.py` 清理帧序列/渲染缓存/音频分段，保留源码契约、报告、`video.mp4` 与 `keyframes/contact.png` |
| 信息密度 | 每帧最多 1 个新概念；单镜旁白不超过 3 句、不超过 10 秒 |

开始时简短列出默认配置，用户未反对即采用。所有参数可覆盖。

## 目录结构

```
output/<topic>/
├── research.md            卡点1：带 URL 与置信度的资料
├── design.md              卡点2：叙事线 + 视觉风格 + 分镜一句话
├── storyboard.json        卡点2：机器可读契约（时间/字幕/数字/样式）
├── lexicon.json           读音与术语替换（TTS 用）
├── audio/
│   ├── audition/          音色试听（卡点3）
│   ├── segments/          逐句音频 + 词边界缓存
│   ├── timeline.json      精确时间轴（场景/句/词）
│   └── narration_raw.wav  拼接后的原始旁白
├── scenes/scene_NN.js     每镜一个 render(ctx,t,S) 纯函数
├── runtime/               从 skill assets 复制的渲染运行时
├── keyframes/             卡点3关键帧 + contact.png
├── frames/scene_NN/       批量帧序列 + meta.json
├── qa/report.json         布局/越界/控制台检查
├── render/scene_NN.mp4    场景无声视频
├── video.mp4              成品
└── render_manifest.json   ffprobe 校验结果
```

Skill 自带资源：`references/`（契约/视觉/场景配方/音频/质检）、`assets/`（运行时与 HTML 模板）、`scripts/`（可直接执行的 Python 工具）。**不要手写这些工具的替代实现**；先运行 `scripts/doctor.py` 检查依赖。

## 工作流

### Stage 0 · 初始化（无卡点）

```bash
python <skill>/scripts/doctor.py
python <skill>/scripts/init_project.py --topic "主题名" --dir "output/<topic>"
```
依赖缺失时明确告知用户安装命令，不要静默降级（Windows 已验证可用：Python 3.11、ffmpeg、edge-tts、playwright chromium、Pillow、numpy）。

### Stage 1 · 知识检索 → 卡点 1

检索官方文档/源码/权威资料，产出 `research.md`：每个知识点附 URL、置信度（高/中/低）、冲突说法标注；结尾给 3 个候选叙事线。对话内提交摘要，等待确认。

### Stage 2 · 动画设计 → 卡点 2

**先读** `references/storyboard-contract.md` 与 `references/visual-design.md`。产出：

- `storyboard.json`：场景、解说词逐句文本、claims、style_tokens、audio 配置（严格按契约 schema）
- `design.md`：叙事线、每镜一句话意图、视觉风格说明、AI 生图提示词（仅限封面/氛围）

旁白文案遵循 `references/audio-guide.md` 的"口语短句"规则：一句一个信息点，术语首次出现给比喻，避免长定语。提交紧凑摘要（镜头数、预计字数、每镜一句话），等待确认与**解说词定稿**。

### Stage 3 · 配音与样片 → 卡点 3

```bash
# 1) 音色试听（用户选择后写入 storyboard.json 的 audio.voice）
python <skill>/scripts/tts_generate.py --project "output/<topic>" --audition

# 2) 正式配音：得到 timeline.json 与每条精确起止
python <skill>/scripts/tts_generate.py --project "output/<topic>"

# 3) 编写 3~6 个代表性场景脚本（见 references/scene-recipes.md），渲染关键帧
python <skill>/scripts/render_scene.py --project "output/<topic>" --scene 01 --frame 0.5
python <skill>/scripts/qa_scene.py --project "output/<topic>" --scenes 01,03,08 --contact

# 4) 样片：渲染前 1~2 镜的完整帧并合成 20~30 秒预览
python <skill>/scripts/render_scene.py --project "output/<topic>" --scene 01 --batch
python <skill>/scripts/compose_video.py --project "output/<topic>" --preview
```
在对话内展示关键帧、contact sheet 与样片，附"每句台词对应哪帧"的说明，等待确认。用户反馈"人机味重"时按 `references/audio-guide.md` 的顺序处理：换音色 → 调停顿 → 微调 pitch → 最后才考虑文案，**不要靠大幅降速**。

### Stage 4 · 批量渲染与合成

```bash
# 若 storyboard 含 preroll（外部音频前置），先注入并同步时间轴
python <skill>/scripts/inject_preroll.py --project "output/<topic>"

python <skill>/scripts/render_scene.py --project "output/<topic>" --scene 00 --batch
python <skill>/scripts/render_scene.py --project "output/<topic>" --scene 01 --batch
# ... 对每个场景执行；可并行但需保持帧号连续

python <skill>/scripts/qa_scene.py --project "output/<topic>" --contact
python <skill>/scripts/compose_video.py --project "output/<topic>"
python <skill>/scripts/cleanup.py --project "output/<topic>"
```
合成器自动完成：场景视频编码 → 拼接 → 旁白响度标准化（−16 LUFS / −1.5 dBTP）→ 混音 → 烧录字幕已在画布内 → ffprobe 校验 → `render_manifest.json`。报告时长、文件路径、校验结果；**成片确认无误后再运行 `cleanup.py`** 删除帧序列、渲染缓存与音频分段。用户需要复用素材时可用 `--keep-frames --keep-keyframes --keep-audio` 保留；先用 `--dry-run` 预览删除清单。某镜有问题只重渲该镜，不要在清理后发现再全量重跑。

## 脚本速查

| 脚本 | 作用 | 关键参数 |
|---|---|---|
| `doctor.py` | 依赖体检 | `--json` |
| `init_project.py` | 建目录、复制运行时、写 storyboard 骨架 | `--topic --dir --force` |
| `tts_generate.py` | 逐句 TTS + 词边界 + 精确时间轴 | `--project --provider --voice --audition --force` |
| `inject_preroll.py` | 将外部音频（如角色音色）前置到镜 00 并同步时间轴/字幕 | `--project`（需 storyboard 中有 `preroll` 配置） |
| `render_scene.py` | 单帧 / 批量帧渲染 | `--project --scene --frame 0.5 \| --batch [--draft] [--scale 2]` |
| `qa_scene.py` | 越界/重叠/控制台检查 + 帧拼图 | `--project [--scenes 01,02] [--contact]` |
| `compose_video.py` | 合成、MG 转场、响度、校验 | `--project [--preview] [--bgm path] [--transition fade\|slideleft\|wipeleft\|mixed\|none] [--transition-ms 350]` |
| `cleanup.py` | 成片后清理中间产物 | `--project [--dry-run] [--keep-frames] [--keep-keyframes] [--keep-audio]` |

## 配音质量要点（详见 `references/audio-guide.md`）

- 逐句合成，按标点加停顿：句末 `。！？：` 后 350ms，句中 `，；、—` 后 120ms，其余 30ms；场景末尾留白 600ms。全部用 WAV 采样数计算，误差为 0。
- edge-tts 的 `WordBoundary` 事件给出 100ns 为单位的词起止，转成秒后写进 timeline，供逐词字幕高亮；不要在句中切分 bookmark。
- 多音字/英文缩写/数字读法写进 `lexicon.json`（如 `"RAG": "R A G"`），在送 TTS 前替换，**字幕保留原文**。
- 语速护栏 `[-5%, +8%]`；低于 −10% 会拖沓失真。要放慢就加停顿或精简文案。
- 升档：设置 `AZURE_SPEECH_KEY`+`AZURE_REGION` 可用 Azure 神经语音的 `narration-relaxed` 等风格；设置 `ELEVENLABS_API_KEY` 可用 ElevenLabs 多语种 v2（中文情感更强）。两者都输出同一 timeline 格式。

## 视觉质量要点（详见 `references/visual-design.md`；浅色白板风见 `references/style-whiteboard.md`）

- 语义色板：一种颜色只有一个含义（实体蓝、焦点黄、关系灰、正确绿、错误红、假设紫、数量金），全片不复用。
- 字号阶梯：标题 64 / 小标题 44 / 正文 34 / 标签 26 / 字幕 30；正文与字幕不低于 24px。
- 运动：快进慢出，默认 `easeOutCubic`；并列元素 stagger 60~100ms；场景转场 300~500ms。禁止线性位移当主要运动。
- 一镜一论点，渐进揭示；先给比喻再给术语；画面上同时存在的元素不超过 7 个。
- AI 生图只用于封面/氛围，**绝不用于数据结构状态**——状态必须程序绘制。

## 常见误区

- 不要跳过卡点直接批量渲染；解说词定稿前不要写场景代码。
- 不要用 12fps + ffmpeg 插帧：文字和线条会糊，v2 直接 30fps 原生渲染。
- 不要估算音频时长或照字数推算帧数；一切以 `timeline.json` 为准。
- 不要静默改字幕/数字/时序；有偏差写进 manifest 并询问。
- 不要把字幕交给 ffmpeg 烧录：v2 由运行时按 timeline 画进画布，避免字体转义与对位漂移。
- 不要把数千帧中间产物留在项目目录：成片复核后运行 `cleanup.py`；`--dry-run` 可先看清单。
- 用户对某帧不满意时只重跑对应场景；改文案则回到卡点 2 重走配音与对位。
