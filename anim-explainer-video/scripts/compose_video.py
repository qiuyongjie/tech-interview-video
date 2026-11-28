#!/usr/bin/env python3
"""Compose scene frames + narration into the final MP4, with loudness and ffprobe checks."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def ffmpeg(*args: object) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *[str(a) for a in args]], check=True)


def ffprobe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=index,codec_name,codec_type,width,height,r_frame_rate",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def make_list(lines: list[Path], target: Path) -> None:
    target.write_text("".join(f"file '{p.as_posix()}'\n" for p in lines), encoding="utf-8")


def concat_with_transition(scene_videos: list[Path], lengths: list[float], out: Path,
                           list_file: Path, kind: str, seconds: float, fps: int) -> None:
    """Join scenes with an MG transition while preserving the original timeline length."""
    if len(scene_videos) == 1 or kind == "none" or seconds <= 0:
        make_list(scene_videos, list_file)
        ffmpeg("-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", out)
        return

    inputs: list[str] = []
    for video in scene_videos:
        inputs.extend(["-i", str(video)])
    filters = [
        f"[{i}:v]tpad=stop_mode=clone:stop_duration={seconds:.3f},format=yuv420p,setsar=1[v{i}]"
        for i in range(len(scene_videos))
    ]
    previous = "v0"
    offset = 0.0
    kinds = ["fade", "slideleft", "wipeleft"] if kind == "mixed" else [kind]
    for i in range(1, len(scene_videos)):
        offset += lengths[i - 1]
        label = f"x{i}"
        xfade_kind = kinds[(i - 1) % len(kinds)]
        filters.append(
            f"[{previous}][v{i}]xfade=transition={xfade_kind}:duration={seconds:.3f}:"
            f"offset={offset:.3f}[{label}]"
        )
        previous = label
    total = sum(lengths)
    filters.append(f"[{previous}]trim=duration={total:.3f},setpts=PTS-STARTPTS[outv]")
    ffmpeg(*inputs, "-filter_complex", ";".join(filters), "-map", "[outv]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", "-r", str(fps), out)


def loudnorm_filter(narration: Path) -> str:
    """Two-pass loudnorm: measure once, then apply exact gain (target -16 LUFS)."""
    base = "loudnorm=I=-16:TP=-1.5:LRA=11"
    try:
        probe = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(narration),
             "-af", base + ":print_format=json", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
        match = re.search(r"\{\s*\"input_i\".*?\}", probe.stderr, re.DOTALL)
        if not match:
            raise ValueError("no loudnorm measurement in ffmpeg output")
        m = json.loads(match.group(0))
        precise = (
            f"{base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
            f"offset={m['target_offset']}:linear=true"
        )
        return f"highpass=f=80,{precise},alimiter=limit=0.97"
    except (ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"[warn] two-pass loudnorm unavailable ({exc}); using single pass")
        return f"highpass=f=80,{base},alimiter=limit=0.97"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--preview", action="store_true", help="assemble a ~25s preview from first scenes")
    ap.add_argument("--bgm", help="optional background music file")
    ap.add_argument("--bgm-gain", default="-24dB", help="gain applied to bgm before mixing")
    ap.add_argument("--transition", choices=["none", "fade", "slideleft", "wipeleft", "mixed"],
                    default="fade", help="MG transition between scenes; mixed cycles fade/slideleft/wipeleft")
    ap.add_argument("--transition-ms", type=int, default=350,
                    help="transition duration in milliseconds (default: 350)")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    storyboard = json.loads((project / "storyboard.json").read_text(encoding="utf-8"))
    timeline = json.loads((project / "audio" / "timeline.json").read_text(encoding="utf-8"))
    fps = int(storyboard.get("fps", 30))
    width, height = storyboard.get("resolution", [1920, 1080])

    selected = timeline["scenes"]
    preview_duration = 0.0
    if args.preview:
        selected = []
        for scene in timeline["scenes"]:
            selected.append(scene)
            preview_duration += scene["duration"]
            if preview_duration >= 25:
                break

    render_dir = project / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    scene_videos: list[Path] = []
    scene_lengths: list[float] = []
    expected_video_duration = 0.0
    for scene in selected:
        sid = str(scene["id"]).zfill(2)
        frames_dir = project / "frames" / f"scene_{sid}"
        meta_path = frames_dir / "meta.json"
        if not meta_path.exists():
            raise SystemExit(f"missing frames for scene {sid}: run render_scene.py --batch first")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not scene_videos:
            width, height = int(meta["width"]), int(meta["height"])
        scene_length = int(meta["frames"]) / fps
        scene_lengths.append(scene_length)
        expected_video_duration += scene_length
        pngs = sorted(frames_dir.glob("*.png"))
        if len(pngs) != int(meta["frames"]):
            raise SystemExit(f"scene {sid}: expected {meta['frames']} frames, found {len(pngs)}")
        target = render_dir / f"scene_{sid}.mp4"
        ffmpeg("-framerate", fps, "-i", frames_dir / "%05d.png",
               "-c:v", "libx264", "-preset", "medium", "-crf", "18",
               "-pix_fmt", "yuv420p", "-r", fps, target)
        scene_videos.append(target)

    silent = render_dir / "silent_preview.mp4" if args.preview else render_dir / "silent.mp4"
    list_file = render_dir / ("concat_preview.txt" if args.preview else "concat.txt")
    concat_with_transition(scene_videos, scene_lengths, silent, list_file,
                           args.transition, args.transition_ms / 1000.0, fps)

    audio_dir = project / "audio"
    narration = audio_dir / "narration_raw.wav"
    if not narration.exists():
        raise SystemExit("audio/narration_raw.wav missing: run tts_generate.py first")
    final_audio = audio_dir / "final_audio.m4a"
    norm = loudnorm_filter(narration)
    if args.bgm:
        ffmpeg("-i", narration, "-stream_loop", "-1", "-i", args.bgm,
               "-filter_complex",
               f"[0:a]{norm}[n];[1:a]volume={args.bgm_gain}[b];"
               "[n][b]amix=inputs=2:duration=first:dropout_transition=0[a]",
               "-map", "[a]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", final_audio)
    else:
        ffmpeg("-i", narration, "-af", norm, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", final_audio)

    if args.preview:
        preview_duration = expected_video_duration
        preview_audio = audio_dir / "preview_audio.m4a"
        ffmpeg("-i", final_audio, "-t", f"{preview_duration:.3f}", "-c", "copy", preview_audio)
        final_audio = preview_audio

    output = project / ("video_preview.mp4" if args.preview else "video.mp4")
    ffmpeg("-i", silent, "-i", final_audio,
           "-c:v", "copy", "-c:a", "copy",
           "-movflags", "+faststart", output)

    probe = ffprobe(output)
    streams = probe.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), {})
    duration = float(probe.get("format", {}).get("duration", 0))
    expected = expected_video_duration
    narration_duration = sum(float(s["duration"]) for s in selected)
    checks = [
        {"name": "ffprobe", "status": "pass" if v.get("codec_name") == "h264" and a.get("codec_name") == "aac" else "fail",
         "evidence": f"video={v.get('codec_name')}, audio={a.get('codec_name')}"},
        {"name": "resolution",
         "status": "pass" if (v.get("width") == width and v.get("height") == height) else "fail",
         "evidence": f"{v.get('width')}x{v.get('height')} expected {width}x{height}"},
        {"name": "fps", "status": "pass" if abs(float(v.get("r_frame_rate", "0/1").split("/")[0]) /
         max(1, int(v.get("r_frame_rate", "1/1").split("/")[1])) - fps) < 0.1 else "fail",
         "evidence": str(v.get("r_frame_rate"))},
        {"name": "duration", "status": "pass" if abs(duration - expected) < 0.2 else "fail",
         "evidence": f"{duration:.3f}s vs frame duration {expected:.3f}s"},
        {"name": "audio-fit",
         "status": "pass" if -0.05 <= duration - narration_duration <= 1.0 else "fail",
         "evidence": f"video {duration:.3f}s, narration {narration_duration:.3f}s (frame rounding is expected)"},
    ]
    manifest = {
        "schema_version": "2.0",
        "project": str(project),
        "output": str(output),
        "duration": duration,
        "audio_duration": narration_duration,
        "transition": {"type": args.transition,
                       "duration_ms": args.transition_ms if args.transition != "none" else 0},
        "width": width, "height": height, "fps": fps,
        "files": [str(output), str(final_audio)],
        "checks": checks,
        "deviations": [],
        "passed": all(c["status"] == "pass" for c in checks),
    }
    manifest_path = project / ("render_manifest_preview.json" if args.preview else "render_manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "duration": duration, "passed": manifest["passed"],
                      "manifest": str(manifest_path)}, ensure_ascii=False))
    for c in checks:
        if c["status"] != "pass":
            print("  FAIL", c["name"], c["evidence"])


if __name__ == "__main__":
    main()
