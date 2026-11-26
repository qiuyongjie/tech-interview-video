#!/usr/bin/env python3
"""compose_video.py — 合成最终视频：插帧、拼场景、混音、烧字幕。

用法:
    python compose_video.py plan.json --out video.mp4
plan.json 格式:
    {
      "fps_out": 30,
      "cover": "assets/cover.png",            // 可选, 展示 2s
      "scenes": [
        {"name": "scene_01", "frames_dir": "frames/scene_01",
         "fps_in": 12, "audio": "audio/scene_01.wav",
         "subtitle": "旁白文本..."}
      ]
    }

流程: 每场景 帧12fps->30fps (minterpolate) + 音频对齐 -> 烧字幕 -> concat -> 封面。
依赖: ffmpeg / ffprobe。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

COVER_SEC = 2.0


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        sys.exit(f"命令失败: {' '.join(map(str, cmd))}")


def audio_dur(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def build_scene_clip(scene, work: Path, fps_out: int) -> Path:
    """单场景: 帧序列 -> 插帧 30fps -> 按音频时长定长 -> 烧字幕 -> mp4 (无声段先出, 混音在 concat 后统一做)。"""
    frames = sorted(Path(scene["frames_dir"]).glob("frame_*.png"))
    if not frames:
        sys.exit(f"{scene['frames_dir']} 中无 frame_*.png")
    fps_in = scene.get("fps_in", 12)
    clip = work / f"{scene['name']}_clip.mp4"

    cmd = ["ffmpeg", "-y", "-framerate", str(fps_in),
           "-i", str(Path(scene["frames_dir"]) / "frame_%05d.png")]
    if scene.get("audio"):
        cmd += ["-i", str(scene["audio"])]  # 所有输入先声明，再写输出选项
    # 12→30fps 帧复制；末尾克隆最后一帧留白，apad 同步补静音
    vf = f"fps={fps_out},tpad=stop_mode=clone:stop_duration=2"
    if scene.get("subtitle"):
        sub_srt = work / f"{scene['name']}.srt"
        dur = audio_dur(Path(scene["audio"])) if scene.get("audio") else 5.0
        sub_srt.write_text(
            f"1\n00:00:00,000 --> {fmt_ts(dur)}\n{scene['subtitle']}\n",
            encoding="utf-8")
        # Windows 盘符冒号必须转义，否则 ffmpeg 过滤器解析失败
        sub_path = sub_srt.as_posix().replace(":", r"\:")
        style = ("FontName=Microsoft YaHei,FontSize=12,PrimaryColour=&H00363A3B,"
                 "BackColour=&H80FDF6E3,BorderStyle=3,Outline=0,Shadow=0,"
                 "Alignment=2,MarginV=18")
        vf += f",subtitles='{sub_path}':force_style='{style}'"
    cmd += ["-vf", vf]
    if scene.get("audio"):
        cmd += ["-af", "apad", "-shortest",
                "-c:a", "aac", "-ar", "44100", "-ac", "1"]
    else:
        cmd += ["-an"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", str(clip)]
    run(cmd)
    return clip


def fmt_ts(sec: float) -> str:
    ms = int(sec * 1000)
    return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"


def main():
    if len(sys.argv) < 4 or "--out" not in sys.argv:
        print(__doc__)
        sys.exit(1)
    plan_path = Path(sys.argv[1])
    out = Path(sys.argv[sys.argv.index("--out") + 1])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    fps_out = plan.get("fps_out", 30)

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        clips = []
        if plan.get("cover"):
            cover_clip = work / "cover.mp4"
            run(["ffmpeg", "-y", "-loop", "1", "-i", str(plan["cover"]),
                 "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                 "-t", str(COVER_SEC), "-vf", "scale=1920:1080",
                 "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                 "-r", str(fps_out),  # 与场景帧率一致，避免 concat 时间基错配
                 "-c:a", "aac", "-ar", "44100", "-ac", "1",
                 "-shortest", str(cover_clip)])
            clips.append(cover_clip)

        for scene in plan["scenes"]:
            clips.append(build_scene_clip(scene, work, fps_out))

        concat_list = work / "list.txt"
        concat_list.write_text(
            "".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
        merged = work / "merged.mp4"
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
             "-c", "copy", str(merged)])

        # 统一响度归一, 保证各场景音量一致
        run(["ffmpeg", "-y", "-i", str(merged), "-af", "loudnorm=I=-16:TP=-1.5",
             "-c:v", "copy", str(out)])

    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        capture_output=True, text=True, check=True)
    print(f"OK -> {out}  duration={float(r.stdout):.1f}s")


if __name__ == "__main__":
    main()
