#!/usr/bin/env python3
"""Prepend an external audio clip (e.g. a synthetic character voice) to scene 00.

Run after tts_generate.py and before render_scene.py. Updates audio/scene_00.wav,
audio/narration_raw.wav and audio/timeline.json so the whole pipeline stays audio-first.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import wave
from pathlib import Path


def ffmpeg(*args: object) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *[str(a) for a in args]], check=True)


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def concat_wavs(parts: list[Path], out: Path, work: Path) -> None:
    list_file = work / f"concat_{out.stem}.txt"
    list_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    ffmpeg("-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", out)
    list_file.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    args = ap.parse_args()

    project = Path(args.project).resolve()
    sb = json.loads((project / "storyboard.json").read_text(encoding="utf-8"))
    cfg = sb.get("preroll")
    if not cfg:
        raise SystemExit("storyboard.json has no preroll config")
    audio_dir = project / "audio"
    timeline_path = audio_dir / "timeline.json"
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    fps = int(sb.get("fps", 30))

    source = Path(cfg["file"])
    if not source.is_absolute():
        source = (project / source).resolve()
    if not source.exists():
        raise SystemExit(f"preroll source missing: {source}")

    trim = float(cfg.get("trim", 4.5))
    fade_in = float(cfg.get("fade_in", 0.2))
    fade_out_start = trim - float(cfg.get("fade_out", 0.5))
    gap = float(cfg.get("gap_after", 0.3))
    work = audio_dir / "segments"
    work.mkdir(parents=True, exist_ok=True)

    preroll = work / "preroll.wav"
    ffmpeg("-i", source, "-t", f"{trim:.3f}",
           "-af", f"highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11,"
                  f"afade=t=in:st=0:d={fade_in:.3f},"
                  f"afade=t=out:st={fade_out_start:.3f}:d={trim - fade_out_start:.3f}",
           "-ar", "48000", "-ac", "1", preroll)
    silence = work / f"gap_{int(gap * 1000):05d}ms.wav"
    if not silence.exists():
        ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
               "-t", f"{gap:.3f}", "-ar", "48000", "-ac", "1", silence)

    host = audio_dir / "scene_00.wav"
    if not host.exists():
        raise SystemExit("audio/scene_00.wav missing: run tts_generate.py first")
    host_backup = work / "scene_00_host.wav"
    if not host_backup.exists():
        host.replace(host_backup)
    else:
        host.unlink()

    concat_wavs([preroll, silence, host_backup], host, work)
    narration = audio_dir / "narration_raw.wav"
    concat_wavs([preroll, silence, narration], work / "narration_with_preroll.wav", work)
    (work / "narration_with_preroll.wav").replace(narration)

    delta = trim + gap
    scene0 = next((s for s in timeline["scenes"] if str(s["id"]) == "00"), None)
    if scene0 is None:
        raise SystemExit("timeline has no scene 00")
    old_duration = float(scene0["duration"])
    scene0["duration"] = round(old_duration + delta, 4)
    scene0["frames"] = math.ceil(scene0["duration"] * fps)
    for cue in scene0.get("cues", []):
        cue["start"] = round(cue["start"] + delta, 4)
        cue["end"] = round(cue["end"] + delta, 4)
        cue["duration"] = round(cue["duration"], 4)
        for word in cue.get("words", []):
            word["start"] = round(word["start"] + delta, 4)
            word["end"] = round(word["end"] + delta, 4)
    for scene in timeline["scenes"]:
        if str(scene["id"]) != "00":
            scene["start"] = round(float(scene["start"]) + delta, 4)
    timeline["preroll"] = {"file": str(source), "trim": trim, "gap_after": gap,
                           "duration": round(delta, 4)}
    timeline["total_duration"] = round(float(timeline["total_duration"]) + delta, 4)
    timeline_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"scene_00_duration": scene0["duration"], "shift_seconds": delta,
                      "total_duration": timeline["total_duration"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
