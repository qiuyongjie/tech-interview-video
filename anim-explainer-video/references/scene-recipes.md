# 场景脚本配方（Canvas 2D）

每个 `scenes/scene_NN.js` 定义一个纯函数，运行时注入绘制工具 `S`：

```js
// scenes/scene_03.js
function render(ctx, t, S) {
  // t: 场景内 0~1 进度；S.time: 场景内秒数；S.duration: 场景时长（来自 TTS）
  // S.cue(id) / S.n(id): 该句的时间信息与句内 0~1 进度
}
```

## 1. 可用 API

### 时间与缓动
| API | 说明 |
|---|---|
| `S.W`, `S.H`, `S.C`, `S.style` | 画布尺寸、语义色对象、完整 style_tokens |
| `S.t`, `S.time`, `S.duration` | 归一化进度、场景内秒数、场景时长 |
| `S.cues`, `S.cue(id)`, `S.n(id)` | 句级时间轴；`S.n(id)` 返回该句内 0~1 进度 |
| `S.seg(p, a, b)` | 把全局进度 p 映射到 [a,b] 区间的 0~1 |
| `S.clip(v)`, `S.lerp(a,b,p)` | 截断、插值 |
| `S.ease.outCubic(p)` 等 | `linear/outCubic/inCubic/inOutCubic/outBack/outExpo` |
| `S.rng(seed)` | 带种子的确定性随机数函数（禁用 Math.random） |

### 绘制原语
| API | 参数要点 |
|---|---|
| `S.text(str,x,y,{size,color,align,weight,mono,maxWidth,alpha})` | 自动登记文字包围盒供 QA 检查 |
| `S.rect(x,y,w,h,{fill,stroke,lineWidth,radius,alpha})` | 圆角矩形/卡片 |
| `S.line(x1,y1,x2,y2,{color,width,dash,progress})` | `progress` 可画部分线段 |
| `S.arrow(x1,y1,x2,y2,{color,width,head,progress})` | 带箭头，可随解说逐步画出 |
| `S.node(x,y,r,label,{color,labelColor,size,progress})` | 节点：圆 + 标签 |
| `S.panel(x,y,w,h,title,{color,bodyLines,bodySize,progress})` | 卡片面板 |
| `S.code(lines,x,y,w,h,{size,highlight,title})` | 代码面板，`highlight` 为行号数组 |
| `S.chip(text,x,y,{color,size})` | 小标签胶囊 |
| `S.progressBar(x,y,w,h,p,{color})` | 进度条 |
| `S.stars(seed,count,alpha)` | 确定性背景点阵 |

字幕由运行时按 `timeline.json` **自动绘制**，场景脚本不要自己画字幕。

## 2. 标准模板

```js
function render(ctx, t, S) {
  const { C, W, H } = S;
  const e = S.ease;

  // 背景：静态，确定性
  S.stars(7, 90, 0.12);

  // 阶段一（第一句）：节点依次入场
  const p1 = S.n('s1');
  const nodes = [320, 760, 1200, 1640];
  nodes.forEach((x, i) => {
    const local = e.outCubic(S.clip((p1 - i * 0.12) / 0.4));
    S.node(x, 440, 46 * local, String(i + 1), {
      color: C.entity,
      size: 30,
      progress: local
    });
  });

  // 阶段二（第二句）：查找路径逐段高亮，上一阶段对象保持存在
  const p2 = S.n('s2');
  for (let i = 0; i < nodes.length - 1; i++) {
    const q = e.outCubic(S.clip((p2 - i * 0.22) / 0.35));
    if (q > 0) {
      S.arrow(nodes[i] + 50, 440, nodes[i + 1] - 50, 440, {
        color: C.focus, width: 5, progress: q
      });
    }
  }

  // 结论：第二句末尾才出现，配 focus 色与短暂停留
  const reveal = e.outExpo(S.clip((p2 - 0.75) / 0.25));
  S.text('线性查找：O(n)', W / 2, 700, {
    size: S.style.heading_px, color: C.focus, align: 'center', alpha: reveal
  });
}
```

## 3. 常用配方

### 渐进揭示（默认）
用 `S.n(cueId)` 把每个动画段绑定到对应旁白句；**对象保持存在**，只改变状态/颜色/位置，不要整屏替换。这样"声音说到哪，画面就证明到哪"。

### 高亮切换
上一焦点转 `C.muted`，当前焦点转 `C.focus`，用 300ms `inOutCubic` 插值颜色：
```js
const c = mixColor(C.muted, C.focus, e.inOutCubic(p));
```
（实现时用 `S.lerp` 对 RGB 分量插值，或直接按阈值切换并配 150ms 透明度渐变。）

### 流程箭头
给每个箭头分配顺序 `i`，用 `S.clip((p - i*0.15)/0.3)` 做 stagger；箭头起点终点与节点坐标共享同一组常量，避免错位。

### 数据变化
用 `S.lerp(oldValue, newValue, e.outCubic(p))` 驱动数字和图形（同一个 tracker 同时驱动条形高度、数值标签和坐标轴），不要各动各的。

### 转场
**场景之间的转场由 `compose_video.py` 统一处理**（默认 350ms 交叉溶解，ffmpeg `xfade`），场景脚本不要再对整屏做淡入淡出，否则会与合成器转场叠加、出现双重淡化或黑帧。场景脚本只负责：元素级 stagger 入场、跨镜连续对象保持相同坐标与颜色。仅在用户明确要求 `--transition none` 时，才在场景首帧用 `e.outCubic(S.t / 0.08)` 做轻微位移+淡入、末帧用 `1 - e.inCubic((S.t - 0.92)/0.08)` 淡出。

### 背景氛围
`S.stars(seed, count, alpha)` 只做低对比点缀；需要更强氛围时由 `design.md` 指定 AI 生成的背景图，透明度 ≤15%，绝不用它承载数据。

## 4. 硬性禁令

- 容器类组件（卡片、面板、列表）必须实际绘制文字内容。若组件参数既接受字符串也接受 `{title, body}` 对象，先归一化再取字段；只画边框不画文字是常见事故，`qa_scene.py` 会按 `kit_params.cards` 数量检查文字框下限。
- 禁用 `Math.random()`、`Date.now()`、`performance.now()`、网络请求、DOM 测量；每帧必须是 `t` 的纯函数。
- 禁止在场景脚本里画字幕（运行时统一处理）。
- 禁止写死时长数字与音频对齐；一律用 `S.n(cueId)` / `S.cue(id)`。
- 禁止把文字贴到安全边距之外；`qa_scene.py` 会报 `off-frame` / `margin`。
- 单个场景脚本建议 ≤150 行；超长说明这一镜承载了太多概念，应拆镜。
