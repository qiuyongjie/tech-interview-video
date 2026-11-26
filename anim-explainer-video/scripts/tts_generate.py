#!/usr/bin/env python3
"""tts_generate.py — 为每个分镜生成旁白音频并输出时长 JSON。

用法:
    python tts_generate.py manifest.json --out-dir audio/
manifest.json 格式（两种均可）:
    # 简单列表
    [
      {"scene": "scene_01", "text": "旁白文本", "voice": "zh-CN-XiaoxiaoNeural",
       "rate": "+0%", "pitch": "+0Hz", "gap_ms": 320},
      ...
    ]
    # 带全局默认值
    {
      "defaults": {"voice": "zh-CN-XiaoxiaoNeural", "rate": "+0%", "gap_ms": 320},
      "scenes": [ {"scene": "scene_01", "text": "..."}, ... ]
    }

输出:
    audio/scene_01.mp3 ...
    audio/durations.json  -> {"scene_01": 12.34, ...}

合成策略（治"人机味"的关键）:
  1. 逐句合成：按句级标点（。！？；!?;）切分旁白，每句单独送 TTS，
     句与句之间插入 gap_ms 毫秒的自然停顿后拼接——模拟真人讲稿的呼吸节奏，
     避免"整段匀速连念"的机器感。逗号停顿由 TTS 自身处理，不在句级切分。
  2. 语速护栏：rate 限制在 [-5%, +8%]。需要放慢节奏时优先加大 gap_ms
     或延长分镜末尾留白，禁止用大幅负语速（<-10% 会拖沓失真）。

可选音色（zh-CN，实测自然度排序）:
    zh-CN-XiaoxiaoNeural   温和女声（默认，讲解通用）
    zh-CN-YunxiNeural      年轻男声，口语感强（活泼主题）
    zh-CN-YunyangNeural    新闻男声，稳重（正式主题）
    zh-CN-XiaoyiNeural     活泼女声（轻快主题）

方案: 优先 edge-tts (pip install edge-tts)，失败则回退 Windows SAPI (System.Speech)。
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

RATE_MIN, RATE_MAX = -5, 8          # 自然语速区间（百分比）
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_GAP_MS = 320                # 句间停顿
SENT_SPLIT = re.compile(r"(?<=[。！？；!?;])")


def clamp_rate(rate: str) -> str:
    try:
        v = int(float(str(rate).strip("+%")))
    except (ValueError, TypeError):
        return "+0%"
    c = max(RATE_MIN, min(RATE_MAX, v))
    if c != v:
        print(f"  语速 {rate}% 超出自然区间 [{RATE_MIN}, {RATE_MAX}]，已收拢为 {c}%")
    return f"{c:+d}%"


def load_items(manifest_path: Path) -> list[dict]:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        defaults = {k: v for k, v in raw.get("defaults", {}).items()
                    if k not in ("scene", "text")}
        items = []
        for it in raw.get("scenes", []):
            merged = dict(defaults)
            merged.update(it)
            items.append(merged)
        return items
    return raw


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in SENT_SPLIT.split(text)]
    return [p for p in parts if p]


def try_edge_tts(items, out_dir: Path) -> dict | None:
    try:
        import edge_tts  # noqa: F401
        import asyncio
    except ImportError:
        return None

    async def gen_sentence(text, voice, rate, pitch, out):
        last = None
        for attempt in range(3):  # 瞬时网络失败重试
            try:
                await edge_tts.Communicate(text, voice, rate=rate,
                                           pitch=pitch).save(str(out))
                return
            except Exception as e:
                last = e
                out.unlink(missing_ok=True)
                await asyncio.sleep(1.5)
        raise last

    async def run():
        for item in items:
            text = item["text"]
            voice = item.get("voice", DEFAULT_VOICE)
            rate = clamp_rate(item.get("rate", "+0%"))
            pitch = item.get("pitch", "+0Hz")
            gap = max(0, int(item.get("gap_ms", DEFAULT_GAP_MS))) / 1000
            sents = split_sentences(text)
            tmp = out_dir / f".tmp_{item['scene']}"
            tmp.mkdir(exist_ok=True)
            try:
                if len(sents) <= 1:
                    # 单句：直接合成
                    await gen_sentence(text, voice, rate, pitch,
                                       tmp / "s0.mp3")
                    subprocess.run(
                        ["ffmpeg", "-y", "-v", "error", "-i", str(tmp / "s0.mp3"),
                         "-ar", "24000", "-ac", "1", str(out_dir / f"{item['scene']}.mp3")],
                        check=True, capture_output=True)
                else:
                    # 逐句合成 → wav，句间插停顿后 concat
                    wavs = []
                    for i, s in enumerate(sents):
                        mp3 = tmp / f"s{i}.mp3"
                        await gen_sentence(s, voice, rate, pitch, mp3)
                        wav = tmp / f"s{i}.wav"
                        subprocess.run(
                            ["ffmpeg", "-y", "-v", "error", "-i", str(mp3),
                             "-ar", "24000", "-ac", "1", str(wav)],
                            check=True, capture_output=True)
                        wavs.append(wav)
                    # 组装 ffmpeg 命令: 句 wav + 句间 anullsrc 静音
                    cmd = ["ffmpeg", "-y", "-v", "error"]
                    fparts = []
                    for i, wav in enumerate(wavs):
                        cmd += ["-i", str(wav)]
                        fparts.append(f"[{len(fparts)}:a]")
                        if i < len(wavs) - 1:
                            cmd += ["-f", "lavfi", "-t", f"{gap:.3f}",
                                    "-i", "anullsrc=r=24000:cl=mono"]
                            fparts.append(f"[{len(fparts)}:a]")
                    fc = "".join(fparts) + f"concat=n={len(fparts)}:v=0:a=1[out]"
                    cmd += ["-filter_complex", fc, "-map", "[out]",
                            "-c:a", "libmp3lame", "-q:a", "4",
                            str(out_dir / f"{item['scene']}.mp3")]
                    subprocess.run(cmd, check=True, capture_output=True)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

    try:
        asyncio.run(run())
    except Exception as e:
        # 网络受限/服务无响应等，回退本地方案
        print(f"edge-tts 失败({type(e).__name__}: {e})，回退 Windows SAPI")
        return None
    durations = measure_durations(items, out_dir)
    if not durations or any(d <= 0 for d in durations.values()):
        return None
    return durations


def sapi_tts(items, out_dir: Path) -> dict:
    """Windows 回退方案：PowerShell System.Speech，输出 WAV。"""
    for item in items:
        out = out_dir / f"{item['scene']}.wav"
        escaped = item["text"].replace("'", "''")
        ps = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.SetOutputToWaveFile('" + str(out).replace("'", "''") + "'); "
            "$s.Rate = " + str(_rate_to_int(item.get("rate", "+0%"))) + "; "
            "$s.Speak('" + escaped + "')"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    return measure_durations(items, out_dir)


def _rate_to_int(rate: str) -> int:
    try:
        return max(-10, min(10, int(float(rate.strip("+%")))))
    except ValueError:
        return 0


def measure_durations(items, out_dir: Path) -> dict:
    durations = {}
    for item in items:
        for ext in (".mp3", ".wav"):
            f = out_dir / f"{item['scene']}{ext}"
            if f.exists():
                try:
                    d = ffprobe_duration(f)
                except Exception:
                    f.unlink(missing_ok=True)  # 损坏文件，删除后看下一扩展名
                    continue
                durations[item["scene"]] = d
                break
    return durations


def ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    return round(float(r.stdout.strip()), 3)


def main():
    if len(sys.argv) < 3 or "--out-dir" not in sys.argv:
        print(__doc__)
        sys.exit(1)
    manifest_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[sys.argv.index("--out-dir") + 1])
    out_dir.mkdir(parents=True, exist_ok=True)
    items = load_items(manifest_path)

    durations = try_edge_tts(items, out_dir)
    engine = "edge-tts"
    if durations is None:
        if sys.platform != "win32":
            print("edge-tts 不可用且非 Windows，无法回退 SAPI。请: pip install edge-tts")
            sys.exit(2)
        durations = sapi_tts(items, out_dir)
        engine = "windows-sapi"

    (out_dir / "durations.json").write_text(
        json.dumps(durations, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK engine={engine} scenes={len(durations)}")
    print(json.dumps(durations, ensure_ascii=False))


if __name__ == "__main__":
    main()
