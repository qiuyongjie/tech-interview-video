# Canvas 绘制模式库（Stage 3/4 必读）

场景脚本 = 一个自包含 HTML 文件，内含确定性渲染函数。渲染器按 `t`（场景进度 0~1）调用它截图。

## 1. 场景脚本模板（严格遵守）

```html
<!-- scenes/scene_03.html -->
<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { margin: 0; }
  canvas { background: #0F172A; }
</style></head>
<body>
<canvas id="c" width="1920" height="1080"></canvas>
<script>
const W = 1920, H = 1080;
// 设计规范中的全局常量（每个场景复制一份，保证一致性）
const C = {
  bg: "#0F172A", primary: "#38BDF8", accent: "#F59E0B",
  warn: "#EF4444", text: "#E2E8F0", dim: "#64748B",
  nodeFill: "#1E293B", codeBg: "#111827"
};
const FONT = "28px 'Cascadia Code', Consolas, monospace";
const FONT_TEXT = "28px 'Microsoft YaHei', sans-serif";

// 缓动：全片统一用 easeInOutCubic，除非分镜特别说明
function ease(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

// ===== 可复用绘制函数（见第 2 节） =====
// ...粘贴需要的 pattern 函数...

// 唯一入口：render(ctx, t)，t ∈ [0, 1] 为场景进度
// 必须是纯函数：相同 t 输出完全相同的画面（确定性，供截图）
function render(ctx, t) {
  // 按时间轴分段推进动画，示例见第 3 节
}

window.__render = render; // 渲染器通过该钩子调用
</script>
</body></html>
```

要求：
- `render` 必须确定性——不使用 `Math.random()`（如需随机，用带种子的伪随机函数）。
- 所有动画由 `t` 驱动，分段推进：`const p1 = ease(clamp((t - 0.0) / 0.3, 0, 1))`。
- 不加载外部图片/字体（字体缺失时用回退字体，渲染器注入 `--font` 时除外）。

## 2. 可复用绘制函数（按主题选用，直接粘贴）

### 节点（圆角矩形 + 文字）

```js
function node(ctx, x, y, w, h, label, opt = {}) {
  ctx.save();
  if (opt.appear !== undefined) { // appear 动画：透明度 + 轻微上浮
    ctx.globalAlpha = Math.min(1, opt.appear * 1.5);
    if (opt.appear < 1) y += (1 - ease(opt.appear)) * 20;
  }
  ctx.fillStyle = opt.fill || C.nodeFill;
  ctx.strokeStyle = opt.stroke || C.primary;
  ctx.lineWidth = opt.lw || 3;
  roundRect(ctx, x - w/2, y - h/2, w, h, 14);
  ctx.fill(); ctx.stroke();
  ctx.fillStyle = opt.color || C.text;
  ctx.font = opt.font || FONT_TEXT;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(label, x, y);
  ctx.restore();
}
function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
```

### 箭头连线（链表 next 指针 / 树边）

```js
function arrow(ctx, x1, y1, x2, y2, opt = {}) {
  const p = opt.progress ?? 1; // 用于 connect 动画：0→1 画到一半
  const dx = x2 - x1, dy = y2 - y1;
  const len = Math.hypot(dx, dy), ux = dx / len, uy = dy / len;
  const ex = x1 + dx * p, ey = y1 + dy * p;
  ctx.save();
  ctx.strokeStyle = opt.color || C.dim; ctx.lineWidth = opt.lw || 3;
  ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(ex, ey); ctx.stroke();
  if (p >= 1) { // 画满才画箭头头
    const s = 12;
    ctx.beginPath();
    ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - ux * s - uy * s * 0.5, y2 - uy * s + ux * s * 0.5);
    ctx.lineTo(x2 - ux * s + uy * s * 0.5, y2 - uy * s - ux * s * 0.5);
    ctx.closePath();
    ctx.fillStyle = opt.color || C.dim; ctx.fill();
  }
  ctx.restore();
}
```

### 红黑树节点（带色环 + NIL 叶）

```js
function rbNode(ctx, x, y, label, color /* "R"|"B" */, opt = {}) {
  node(ctx, x, y, 90, 90, label, { stroke: color === "R" ? C.warn : C.text, ...opt });
  ctx.save(); // 内圈色环强化红/黑辨识
  ctx.beginPath(); ctx.arc(x, y + 28, 8, 0, 7);
  ctx.fillStyle = color === "R" ? C.warn : C.text;
  ctx.fill(); ctx.restore();
}
```

### 高亮脉冲（强调当前关注对象）

```js
function glow(ctx, x, y, r, color, p /* 0~1 脉冲相位 */) {
  ctx.save();
  ctx.strokeStyle = color; ctx.globalAlpha = 0.4 + 0.4 * Math.sin(p * Math.PI);
  ctx.lineWidth = 6;
  ctx.beginPath(); ctx.arc(x, y, r + 10, 0, 7); ctx.stroke();
  ctx.restore();
}
```

### 代码面板（逐行 trace 显示 + 当前行高亮）

```js
function codePanel(ctx, x, y, w, lines, opt = {}) {
  const lh = 42, shown = Math.ceil((opt.progress ?? 1) * lines.length);
  ctx.save();
  ctx.fillStyle = C.codeBg;
  roundRect(ctx, x, y, w, lines.length * lh + 24, 12); ctx.fill();
  ctx.strokeStyle = C.dim; ctx.lineWidth = 1.5; ctx.stroke();
  lines.slice(0, shown).forEach((ln, i) => {
    if (i === (opt.activeLine ?? -1)) {
      ctx.fillStyle = "rgba(56,189,248,0.18)";
      ctx.fillRect(x + 8, y + 12 + i * lh, w - 16, lh - 4);
    }
    ctx.fillStyle = i === (opt.activeLine ?? -1) ? C.accent : C.text;
    ctx.font = FONT; ctx.textAlign = "left"; ctx.textBaseline = "middle";
    ctx.fillText(ln, x + 24, y + 12 + i * lh + lh / 2 - 2);
  });
  ctx.restore();
}
```

### 标注文字（淡入）

```js
function label(ctx, x, y, text, p /* 0~1 appear */, opt = {}) {
  if (p <= 0) return;
  ctx.save();
  ctx.globalAlpha = Math.min(1, p * 2);
  ctx.fillStyle = opt.color || C.accent;
  ctx.font = opt.font || FONT_TEXT;
  ctx.textAlign = opt.align || "left";
  ctx.fillText(text, x, y);
  ctx.restore();
}
```

## 3. 分段推进动画示例（对应 storyboard-guide 的术语）

```js
function render(ctx, t) {
  ctx.clearRect(0, 0, W, H);
  // 时间轴：0~0.2 appear 全部节点；0.2~0.5 move 指针；0.5~0.8 highlight；0.8~1.0 标注淡入
  const pAppear = ease(clamp(t / 0.2, 0, 1));
  const pMove   = ease(clamp((t - 0.2) / 0.3, 0, 1));
  const pGlow   = clamp((t - 0.5) / 0.3, 0, 1);
  const pLabel  = clamp((t - 0.8) / 0.2, 0, 1);

  const nodes = ["10", "20", "30", "40", "50"];
  const xs = nodes.map((_, i) => 320 + i * 260);
  nodes.forEach((v, i) => {
    // appear：整体透明度驱动；已访问节点（指针之前）变灰
    const visited = pMove * (nodes.length - 1) > i;
    node(ctx, xs[i], 540, 120, 90, v, {
      appear: pAppear,
      stroke: visited ? C.dim : C.primary,
    });
    if (i < nodes.length - 1) arrow(ctx, xs[i] + 60, 540, xs[i+1] - 60, 540);
  });
  // 指针沿链表移动
  const px = 320 + 260 * pMove * 4;
  node(ctx, px, 700, 140, 70, "cur", { stroke: C.accent });
  if (pGlow > 0) glow(ctx, xs[4], 540, 60, C.accent, pGlow);
  if (pLabel > 0) label(ctx, xs[4], 420, "找到目标：O(n) 的代价", pLabel);
}
function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
```

## 4. 渲染器契约（render_scene.py 依赖）

- 渲染器加载 HTML 后，执行 `window.__render(ctx, t)`，`t = frameIndex / totalFrames`，然后 `canvas.toDataURL("image/png")` 存帧。
- 画布固定 1920×1080；不要滚动页面。
- 场景 HTML 必须无控制台错误——渲染前先渲染 3 个抽样帧（t=0/0.5/1）人工查看，有错先修。
