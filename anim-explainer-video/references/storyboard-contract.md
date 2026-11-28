# Storyboard 契约（v2）

`storyboard.json` 是整条管线的唯一事实源。渲染、配音、字幕、质检都只读它；任何脚本都不得自行发明时间、文案或数字。

## 顶层结构

```json
{
  "schema_version": "2.0",
  "topic": "Java 链表转红黑树",
  "language": "zh-CN",
  "resolution": [1920, 1080],
  "fps": 30,
  "style_tokens": {
    "bg": "#0B1020", "surface": "#151D33", "text": "#E8EDF7",
    "muted": "#8A94A8", "entity": "#4CC9F0", "focus": "#FFD166",
    "relation": "#6B7A99", "good": "#06D6A0", "bad": "#EF476F",
    "assumption": "#B388FF", "quantity": "#F6C85F",
    "font_sans": "Microsoft YaHei", "font_mono": "Consolas",
    "title_px": 64, "heading_px": 44, "body_px": 34,
    "label_px": 26, "caption_px": 30,
    "margin": 96, "safe_top": 120, "safe_bottom": 180
  },
  "audio": {
    "provider": "edge",
    "voice": "zh-CN-YunxiNeural",
    "rate": "+0%",
    "pitch": "+0Hz",
    "scene_tail_ms": 600
  },
  "scenes": [
    {
      "id": "01",
      "title": "开场钩子",
      "intent": "用一个生活比喻说明为什么要转换",
      "visual": "链表节点逐个排开，查找路径高亮",
      "motion": "节点 stagger 入场，箭头沿查找路径依次画出",
      "claims": ["链表查找是 O(n)"],
      "narration": [
        { "id": "s1", "text": "先看一个链表。" },
        { "id": "s2", "text": "要找到最后一个节点，只能从头一步一步走。" }
      ],
      "duration_hint": 10
    }
  ]
}
```

## 字段规则

| 字段 | 规则 |
|---|---|
| `scenes[].id` | 两位数字字符串，`00` 保留给可选封面镜；必须连续 |
| `scenes[].intent` | 一句话说明这一镜"证明什么"，不是画面描述的堆砌 |
| `scenes[].claims` | 该镜呈现的事实断言；每个 claim 必须有对应画面证据，质检时逐条抽帧核对 |
| `scenes[].narration[].text` | 口语短句，一句一个信息点；卡点 2 定稿后不可改 |
| `scenes[].narration[].id` | 场景内唯一；生成 timeline 后与 cue id 一一对应 |
| `duration_hint` | 仅供设计时参考，**不参与渲染**；实际时长由 TTS 决定 |
| `scene_tail_ms`（场景级可选） | 覆盖全局 `audio.scene_tail_ms`（毫秒），用于单独调整某镜结尾留白 |
| `style_tokens` | 颜色必须语义化；同一含义全片同色，不同含义不复用同色 |
| `audio.rate/pitch` | rate 限 `[-5%, +8%]`，pitch 限 `[-2Hz, +2Hz]` |
| `audio.provider` | `edge`（默认）/ `azure` / `elevenlabs`；均可输出相同 timeline 格式 |

## 时间轴契约（tts_generate.py 产出）

`audio/timeline.json` 由实测采样数生成，禁止手写或手改：

```json
{
  "schema_version": "2.0",
  "provider": "edge", "voice": "zh-CN-YunxiNeural",
  "total_duration": 183.42,
  "scenes": [
    {
      "id": "01", "start": 0.0, "duration": 9.86, "frames": 296,
      "cues": [
        {
          "id": "s1", "text": "先看一个链表。",
          "start": 0.0, "end": 2.13, "duration": 2.13,
          "words": [
            { "text": "先看", "start": 0.10, "end": 0.62 },
            { "text": "一个", "start": 0.62, "end": 1.05 }
          ]
        }
      ]
    }
  ]
}
```

- `start/end` 单位为秒，场景内时间从 0 起；全片时间 = 场景 `start` + 场景内时间。
- `duration` 由 WAV 样本数 / 采样率得出，误差为 0；`frames = ceil(duration × fps)`。
- `words` 来自 edge-tts `WordBoundary`（100ns ticks ÷ 1e7）；其他 provider 可为空数组，此时字幕按整句显示。
- 字幕起点 = cue 的真实音频起点；不得用估算值。

## 偏差处理

渲染器如发现 `storyboard.json` 与画面不一致（例如某数字在契约里是 8、旁白却写 10），必须：

1. 不修改任何内容；
2. 在 `render_manifest.json` 的 `deviations` 中记录 `{scene, field, expected, found}`；
3. 停下来询问用户，得到明确指示后再改 `storyboard.json` 并重新走卡点 2。

## 自检清单（进入卡点 2 前）

- [ ] 每个 claim 都能在 `visual` 中找到对应画面
- [ ] 每镜旁白 ≤ 3 句、≤ 10 秒，无书面长定语
- [ ] 数字、年份、术语均来自 `research.md` 且带来源
- [ ] 颜色语义与 `visual-design.md` 一致
- [ ] `audio.provider/voice` 已确定，等待卡点 3 试听确认
