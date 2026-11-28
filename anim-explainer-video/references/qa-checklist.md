# 质检与验收

## 1. 三道自动检查

```bash
python <skill>/scripts/doctor.py                       # 依赖与字体
python <skill>/scripts/qa_scene.py --project ... --contact   # 画面
python <skill>/scripts/compose_video.py --project ...       # 内嵌 ffprobe 校验
```

`qa_scene.py` 在每个 cue 起点、场景中点、场景末点冻结帧，检查：

| 检查项 | 含义 | 级别 |
|---|---|---|
| `off-frame` | 文字/元素超出画布 | 必须修 |
| `margin` | 文字进入左右 96px / 上 120px / 下 180px 安全区外 | 必须修 |
| `overlap` | 两块文字包围盒重叠 | 必须修 |
| `font-too-small` | 正文字号 <24px | 必须修 |
| `console-error` | 场景脚本抛异常或控制台报错 | 必须修 |
| `long-shot` | 单镜旁白 >10 秒 | 回到卡点 2 拆镜 |
| `claim-value-mismatch` | 屏幕数字与旁白/契约不一致（实例：画面写"第 8 次"、旁白说"最坏 7 次"） | 必须修；自动检查看不出，需逐帧人工核对 |
| `missing-content` | 容器/卡片只画出边框，文字没画出来（实例：`cards` 传了字符串数组但组件期待对象） | 必须修；`qa_scene.py` 按 storyboard 的卡片数校验文字框下限 |
| `static-frame` | 相邻帧像素变化 <0.2%，画面实际静止 | 必须修；说明持续运动层失效，检查 runtime 是否被旧运行时覆盖 |

输出 `qa/report.json` 与 `keyframes/contact.png`（每镜抽帧拼图）。`compose_video.py` 输出 `render_manifest.json`，含 ffprobe 的编码/时长/分辨率/帧率校验和 deviations 列表。

## 2. 人工看帧（不可省略）

自动检查看不见"说错了但画对了"的语义错误。按下面顺序看：

1. **逐 claim 抽帧**：`storyboard.json` 里每个 claim 找一帧，确认画面显示的就是旁白说的值。经典事故：旁白说 "D is ten"、画面写 D=8。
2. **逐句对应**：读 contact sheet，每行台词下方应有对应画面证据；高亮对象应与当前句子一致。
3. **节奏**：至少有一个静止消化点；全程都在动说明动画在抢注意力。
4. **字幕**：起止与音频对齐；逐词高亮不领先/滞后；无遮挡。
5. **一致性**：同一实体全片同色同形；节点位置跨镜连续；数字单位齐全。

发现问题：只重渲对应场景（`render_scene.py --scene NN --batch`），然后重新 qa + compose。不要全量重渲。

## 3. 成片验收清单

- [ ] `render_manifest.json` 的 ffprobe 检查为 `pass`，编码 h264+aac，分辨率与 fps 符合配置
- [ ] 实际时长与**帧时长**（各场景 `meta.json` 的帧数 ÷ fps 之和）误差 < 0.2 秒；旁白时长可略短，差值为逐镜向上取整的留白，由 `audio-fit` 检查（0~1 秒）覆盖，不再拿旁白总时长当视频时长判据
- [ ] 音量无爆音（−1.5 dBTP 以下），无底噪（highpass 已启用）
- [ ] 每个 claim 有画面证据，字幕与旁白逐句对齐
- [ ] 无越界/重叠/过小字/控制台错误
- [ ] 关键帧与卡点 3 确认的风格一致
- [ ] 成片复核后已运行 `cleanup.py` 清除帧序列/渲染缓存/分段音频（保留 `video.mp4`、`render_manifest.json`、`timeline.json` 与 `contact.png`）
- [ ] 场景切换为 350ms 交叉溶解（`render_manifest.json.transition`），无黑帧、无硬切、无双重淡化；转场期间字幕未被遮挡或漂移
- [ ] 若 storyboard 含 `preroll`：开场音频来自指定文件，`inject_preroll.py` 已同步 timeline 位移，字幕在外部音频结束后才出现
- [ ] 动效未穿越文字、未进入字幕安全区；无可见矩形扫光块或穿过标题的装饰线条（目视检查，自动检查暂不能覆盖）

## 4. 偏差与升级

渲染器或合成器发现契约与画面冲突时，不得自行纠错：记录到 `render_manifest.json.deviations`，停下来询问用户。若用户要求改文案，回到卡点 2 重走配音与时间轴；若只改视觉，改对应场景脚本后单镜重渲。
