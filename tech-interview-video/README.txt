========================================================
tech-interview-video
技术面试题可爱风格讲解视频生成 Skill（个人级 / 项目级通用）
========================================================

[状态]
- 已在 CodeBuddy 环境中验证通过（2026-11-23）。
- 完整流程实测产出：outline.md（5 页）、slides.pptx（可爱风格）、
  video.mp4（1920x1080 / H.264 / AAC，约 105 秒，含中文 TTS 配音）。
- 可提交至 GitHub 公开分享。

[功能简介]
将任意技术主题（编程语言、框架、工具、数据库、云服务等）的面试题，
自动转化为三件交付物：
  1. outline.md   —— 3–5 页大纲，联网搜索最新解释，版本相关内容标注来源
  2. slides.pptx  —— 可爱风格 PPT（马卡龙配色 / 圆角卡片 / 圆体字 /
                     贴纸 emoji / 代码高亮 / 每页不超过 3 个要点）
  3. video.mp4    —— 1080p 讲解视频，每页备注 60–100 字口语化文案并配音；
                     TTS 不可用时自动降级为"无配音 + 内嵌字幕"版本

[核心机制]
- 强制人工审核点：PPT 大纲必须经用户明确回复"确认"后才进入 PPT 与视频
  合成阶段，AI 严禁跳过或自行推断同意。
- 三阶段顺序执行，严禁跳过任何阶段；"必须 / 严禁"级硬性规则措辞。

[触发方式]
- 斜杠指令：/tech-interview-video（兼容旧指令 /java-interview-video）
- 自然语言："帮我把这些 XX 面试题做成可爱风格讲解视频"、"生成 XX 技术
  面试讲解 PPT"等。

[文件清单]
  SKILL.md   —— Skill 主体（YAML 元数据 + 操作指令），必需文件
  README.txt —— 本说明文件

[安装位置（二选一，放置后 AI 可自动调用）]
  个人级：C:\Users\<用户名>\.codebuddy\skills\tech-interview-video\
  项目级：<项目根>\.codebuddy\skills\tech-interview-video\

[依赖环境（在已验证的 Windows 11 + CodeBuddy 环境实测）]
  Python 3.9+（实测 3.11.8）
  python-pptx 1.0+   pip install python-pptx
  Pillow             pip install Pillow        （字幕降级方案使用）
  edge-tts           pip install edge-tts      （中文配音，需联网）
  ffmpeg 9.x         下载构建包并加入 PATH，ffmpeg -version 验证
  幻灯片导出图片：优先 LibreOffice；Windows 无 LibreOffice 时用
  PowerPoint/WPS COM（Export 1920x1080 PNG，导出后需关闭占用进程
  再重写 pptx，详见 SKILL.md 阶段三）


[常见问题]
- Q：AI 跳过了"确认"环节直接生成 PPT？
  A：在 SKILL.md 的硬性规则区追加更强化措辞（"必须""严禁""绝对禁止"），
     并在审核点处重复声明；本 SKILL.md 已内置三层防护。
- Q：视频没有声音？
  A：检查 edge-tts 是否可用及网络连通；不可用时 Skill 会自动生成
     无配音 + 字幕版本并在交付时说明。
