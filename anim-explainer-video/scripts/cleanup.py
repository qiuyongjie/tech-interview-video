#!/usr/bin/env python3
"""Remove bulky intermediate artifacts after a video is composed and verified.
Keeps source contracts, reports, the final MP4 and keyframes/contact.png by default.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def collect(project: Path, keep_frames: bool, keep_keyframes: bool, keep_audio: bool) -> list[Path]:
    targets: list[Path] = []
    if not keep_frames:
        targets.append(project / "frames")
        targets.append(project / "render")
        targets.append(project / "video_preview.mp4")
        targets.append(project / "render_manifest_preview.json")
    if not keep_audio:
        targets.append(project / "audio" / "segments")
        for pattern in ("scene_*.wav", "narration_raw.wav", "final_audio.m4a",
                        "preview_audio.m4a", "audition/*.mp3"):
            targets.extend((project / "audio").glob(pattern))
    if not keep_keyframes:
        for png in (project / "keyframes").glob("*.png"):
            if png.name != "contact.png":
                targets.append(png)
    targets.extend((project / "runtime").glob("_harness_*.html"))
    return [p for p in targets if p.exists()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--keep-frames", action="store_true")
    ap.add_argument("--keep-keyframes", action="store_true")
    ap.add_argument("--keep-audio", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    if not (project / "storyboard.json").exists() or not (project / "audio" / "timeline.json").exists():
        raise SystemExit("not a valid video project: storyboard.json / timeline.json missing")
    if not (project / "video.mp4").exists():
        raise SystemExit("video.mp4 not found; compose before cleanup")

    targets = collect(project, args.keep_frames, args.keep_keyframes, args.keep_audio)
    removed, freed = 0, 0
    for path in targets:
        if project not in path.parents:
            raise SystemExit(f"refusing to delete outside project: {path}")
        size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else path.stat().st_size
        if args.dry_run:
            print("would remove", path.relative_to(project))
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed += 1
        freed += size

    if not args.dry_run:
        manifest = project / "render_manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["files"] = [f for f in data.get("files", []) if Path(f).exists()]
            data["cleaned_intermediates"] = True
            manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"removed_items": removed, "freed_MB": round(freed / 1024 / 1024, 2),
                      "dry_run": args.dry_run}, ensure_ascii=False))


if __name__ == "__main__":
    main()
