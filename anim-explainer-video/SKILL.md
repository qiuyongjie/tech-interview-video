---
name: anim-explainer-video
description: 根据任意技术主题自动生成讲解型动画视频（如"Java 链表转红黑树的过程"）。全流程含知识检索、人工审核、动画设计、关键帧预览、批量生成与配音合成四个阶段和三个审核卡点。技术路线为混合式：结构动画用 Canvas/SVG 程序化渲染保证精确性，封面/氛围图用 AI 生图；配音用本地免费 TTS；输出 1080p、默认 3~5 分钟。当用户要求"做一个讲解动画视频""把某主题做成动画""生成教学视频"时使用本 Skill。
---

# Anim Explainer Video

## Overview

将一个技术主题转化为讲解型动画视频。核心流程：**知识检索 → 人工审核 → 动画设计 → 人工审核 → 关键帧预览 → 人工审核 → 批量生成与合成**。

三条铁律（任何情况下不得跳过）：

1. **三个卡点必须人工确认**：知识资料、动画设计、关键帧，未经用户明确确认（如"确认""通过""可以"）不得进入下一阶段。用户提出修改意见时，修改后重新提交确认。
2. **Audio-first 时序**：先为每段旁白生成 TTS 音频并测得实际时长，由音频时长反推每个分镜的帧数，禁止先定帧数再配音。
3. **场景脚本化渲染**：每个分镜写成一个确定性渲染脚本 `render(ctx, t)`（t 为 0~1 的场景进度），以 12fps 渲染，再用 ffmpeg 插帧平滑到 30fps。任何一帧出错只需重跑对应场景。

## 默认配置

| 参数 | 默认值 |
|---|---|
| 总时长 | 3~5 分钟（用户可指定） |
| 分辨率/帧率 | 1920×1080 / 输出 30fps（渲染 12fps 后插帧） |
| 语言 | 中文（旁白+字幕） |
| TTS | 本地免费方案：优先 edge-tts（逐句合成+句间停顿），不可用则回退 Windows SAPI |
| 审核形式 | 对话内图片预览 + 文字摘要 |
| 中间产物 | 保留在 `output/<topic>/` 下（frames/audio/scenes） |
| 信息密度 | 每帧最多引入 1 个新概念；单段旁白不超过 3 句 |

所有参数均可被用户覆盖。开始阶段 1 前，向用户确认一遍默认配置（简短列出即可，用户未反对即采用）。

## Stage 1：知识检索

1. 用 web_search / web_fetch 检索主题，优先来源：官方文档、JDK/JVM 源码、权威教材、高赞技术博客。
2. 产出 `output/<topic>/research.md`：
   - 每个知识点单独列出，附来源 URL 与置信度（高/中/低）
   - 冲突说法显式标注（如不同 JDK 版本阈值差异）
   - 结尾附"讲解切入角度建议"（3 个候选叙事线）
3. **卡点 ✋**：在对话内以摘要形式提交审核，等待用户确认或修正。用户补充资料时合并进 research.md 后再次确认。

## Stage 2：动画设计

输入为已确认的 research.md。先阅读 `references/storyboard-guide.md` 获取分镜设计规范，再产出 `output/<topic>/design.md`，必须包含：

- **分镜脚本**：每个分镜一段，含 场景编号、画面内容描述、旁白文本、预计时长、动画要点（哪些元素出现/移动/高亮）、转场方式
- **视觉风格**：色板（背景/主色/强调色/代码色，给具体 hex 值）、字体（正文 + 等宽代码字体）、2D 线稿/Canvas 图形风格的具体描述
- **帧生成方式**：哪些场景用 Canvas 程序化绘制（默认全部结构场景），封面/氛围图用 AI 生图（列出需要的图及提示词）
- **音频规范**：TTS 音色、语速、是否加背景音乐
- **字幕方案**：字幕文本与分镜一一对应，说明位置与样式
- **封面设计**：AI 生图提示词 + 标题文案

设计完成后**卡点 ✋**：在对话内以紧凑摘要（分镜数、总时长、每镜一句话）提交，等待确认。

## Stage 3：关键帧预览

1. 选取 3~6 个代表性分镜（首帧、核心转折帧、结尾帧），编写其 `render(ctx, t)` 场景脚本（见 `references/canvas-patterns.md`）。
2. 用 `scripts/render_scene.py --scene <file> --frame t` 渲染单帧 PNG。
3. 封面用 AI 生图生成（可用 image_gen 工具）。
4. **卡点 ✋**：在对话内展示图片（附每张的说明），等待用户确认风格与质量。修改意见落实后重渲染受影响的帧再次提交。

## Stage 4：批量生成与合成

1. **配音先行**：对每个分镜的旁白运行 `scripts/tts_generate.py`，得到 `audio/scene_NN.mp3` 与时长 JSON。
2. **反推帧数**：`帧数 = round(音频时长 × 12fps)`，写回分镜表。
3. **批量渲染**：对每个分镜运行 `scripts/render_scene.py --scene <file> --batch`，输出 `frames/scene_NN/`。
4. **合成**：运行 `scripts/compose_video.py`，完成：插帧到 30fps → 烧录字幕 → 每场景配音频 → 拼接 → 封面帧（约 2 秒）→ 输出 `output/<topic>/video.mp4`。
5. 依赖 ffmpeg；若未安装，提示用户安装（Windows: `winget install ffmpeg`）。
6. 成片后在对话内报告时长与文件路径，询问是否需要复核；节奏问题时只重做对应分镜。

### 配音质量规范（治"人机味"）

- **逐句合成**：脚本自动按句级标点切分旁白，逐句送 TTS 后以 `gap_ms`（默认 320ms）拼接句间停顿，模拟真人讲稿的呼吸节奏。逗号微停顿由 TTS 自身处理。
- **语速护栏**：`rate` 被限制在 `[-5%, +8%]`。需要放慢节奏时，**加大 `gap_ms` 或延长分镜末尾留白**，不要大幅降低语速——低于 -10% 会拖沓失真、机器感更强。
- **音色选择**（zh-CN 实测自然度）：
  | 音色 | 特点 | 适用 |
  |---|---|---|
  | `zh-CN-XiaoxiaoNeural` | 温和女声 | 通用讲解（默认） |
  | `zh-CN-YunxiNeural` | 年轻男声、口语感 | 活泼/面试闲聊风 |
  | `zh-CN-YunyangNeural` | 新闻男声、稳重 | 正式主题 |
  | `zh-CN-XiaoyiNeural` | 活泼女声 | 轻快主题 |
  用户反馈"人机味重"时，优先级：换音色（Xiaoxiao→Yunxi）→ 加大 `gap_ms` → 微调 `pitch`（±2Hz 内），而不是动语速。
- **旁白文案配合**（Stage 2 写旁白时就注意）：口语短句、每句一个信息点、避免书面长定语；长句在 TTS 里无论如何调参都念不出节奏。

## 目录约定

```
output/<topic>/
├── research.md          # 阶段1产出
├── design.md            # 阶段2产出
├── scenes/scene_NN.js   # 每个分镜的 render(ctx, t) 渲染脚本
├── keyframes/           # 阶段3关键帧
├── audio/               # TTS 音频 + durations.json
├── frames/scene_NN/     # 批量渲染的帧序列
└── video.mp4            # 成品
```

## Scripts

- `scripts/tts_generate.py` — 生成旁白音频并输出时长 JSON。逐句合成+句间停顿拼接（`gap_ms` 可配），语速护栏 `[-5%, +8%]`。优先 edge-tts（`pip install edge-tts`），失败回退 Windows PowerShell System.Speech。
- `scripts/render_scene.py` — 通过 Playwright 无头浏览器加载场景 HTML，渲染单帧（`--frame 0.5`）或整段帧序列（`--batch`）。依赖：`pip install playwright` 且 `playwright install chromium`。
- `scripts/compose_video.py` — 读取 durations.json，插帧、拼场景、混音、烧字幕，合成最终 mp4。依赖 ffmpeg。

运行前先检查依赖是否可用，缺失时明确告知用户并给出安装命令，不要静默降级。

## References

- `references/storyboard-guide.md` — 分镜设计规范：叙事结构、信息密度、旁白写法、转场选择、讲解型动画的常见误区。**Stage 2 开始前必读。**
- `references/canvas-patterns.md` — Canvas 绘制模式库：节点/链表/树/箭头/高亮/代码面板等可复用绘制函数与 render(ctx, t) 场景脚本模板。**Stage 3/4 编写场景脚本时必读。**

## 常见误区

- 不要在知识检索阶段就开始写场景代码——资料未确认，返工成本极高。
- 不要用 AI 生图渲染数据结构状态——状态必须精确，只能程序绘制；AI 生图仅限封面/氛围。
- 不要假设音频时长等于旁白字数估算值——必须以 TTS 实测时长为准。
- 不要用大幅负语速（<-10%）换时长或"压节奏"——正确做法是调 `gap_ms`、分镜留白，或回到 Stage 2 精简旁白文案。
- 用户对某一帧不满意时，只重跑对应场景，不要全量重渲染。
