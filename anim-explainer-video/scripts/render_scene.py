#!/usr/bin/env python3
"""Deterministic Canvas frame renderer: single frozen frame or full 30fps batch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def build_harness(project: Path, scene_id: str, width: int, height: int) -> Path:
    storyboard = json.loads((project / "storyboard.json").read_text(encoding="utf-8"))
    tl_path = project / "audio" / "timeline.json"
    timeline = json.loads(tl_path.read_text(encoding="utf-8")) if tl_path.exists() else {"scenes": []}
    template = (project / "runtime" / "scene-template.html").read_text(encoding="utf-8")
    scene_file = project / "scenes" / f"scene_{scene_id}.js"
    if not scene_file.exists():
        raise SystemExit(f"missing scene script: {scene_file}")

    replacements = {
        "__STYLE_JSON__": json.dumps(storyboard.get("style_tokens", {}), ensure_ascii=False),
        "__TIMELINE_JSON__": json.dumps(timeline, ensure_ascii=False),
        "__SCENE_ID_JSON__": json.dumps(scene_id),
        "__CONFIG_JSON__": json.dumps({"width": width, "height": height}),
        "__RUNTIME_SRC__": (project / "runtime" / "scene-runtime.js").as_uri(),
        "__SCENE_SRC__": scene_file.as_uri(),
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    out = project / "runtime" / f"_harness_{scene_id}.html"
    out.write_text(template, encoding="utf-8")
    return out


def downsample(path: Path, width: int, height: int) -> None:
    with Image.open(path) as im:
        if im.size != (width, height):
            im.convert("RGB").resize((width, height), Image.LANCZOS).save(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--scene", required=True, help="scene id, e.g. 01")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--frame", type=float, help="normalized time 0..1 for one PNG")
    group.add_argument("--batch", action="store_true", help="render the whole scene")
    ap.add_argument("--out", help="output path for --frame")
    ap.add_argument("--draft", action="store_true", help="render at 640x360")
    ap.add_argument("--scale", type=int, default=1, choices=[1, 2], help="supersample factor")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    storyboard = json.loads((project / "storyboard.json").read_text(encoding="utf-8"))
    tl_path = project / "audio" / "timeline.json"
    if not tl_path.exists():
        raise SystemExit("run tts_generate.py first: audio/timeline.json is missing")
    timeline = json.loads(tl_path.read_text(encoding="utf-8"))
    scene_data = next((s for s in timeline["scenes"] if str(s["id"]) == args.scene.zfill(2)), None)
    if scene_data is None:
        raise SystemExit(f"scene {args.scene} not found in timeline.json")

    base_w, base_h = storyboard.get("resolution", [1920, 1080])
    if args.draft:
        width, height = 640, round(640 * base_h / base_w)
    else:
        width, height = int(base_w), int(base_h)
    harness = build_harness(project, args.scene.zfill(2), width, height)
    duration = float(scene_data["duration"])
    frames = int(scene_data["frames"])

    from playwright.sync_api import sync_playwright

    console_errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height},
                                device_scale_factor=args.scale)
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.goto(harness.as_uri(), wait_until="load")
        page.wait_for_function("window.__READY === true", timeout=20000)
        canvas = page.locator("#stage")

        if args.frame is not None:
            if not 0 <= args.frame <= 1:
                raise SystemExit("--frame must be between 0 and 1")
            result = page.evaluate("(t) => window.__renderFrame(t)", args.frame)
            if result.get("error"):
                raise SystemExit("scene error:\n" + result["error"])
            out = Path(args.out) if args.out else project / "keyframes" / f"scene_{args.scene.zfill(2)}_t{args.frame:.2f}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            canvas.screenshot(path=str(out))
            if args.scale > 1:
                downsample(out, width, height)
            print(json.dumps({"scene": args.scene, "frame": args.frame, "time": result["time"],
                              "output": str(out), "boxes": len(result["boxes"]),
                              "console_errors": console_errors}, ensure_ascii=False))
        else:
            out_dir = project / "frames" / f"scene_{args.scene.zfill(2)}"
            out_dir.mkdir(parents=True, exist_ok=True)
            for old in out_dir.glob("*.png"):
                old.unlink()
            for i in range(frames):
                t = (i + 0.5) / frames
                result = page.evaluate("(t) => window.__renderFrame(t)", t)
                if result.get("error"):
                    raise SystemExit(f"scene error at frame {i}:\n{result['error']}")
                target = out_dir / f"{i:05d}.png"
                canvas.screenshot(path=str(target))
                if args.scale > 1:
                    downsample(target, width, height)
            meta = {"scene": args.scene.zfill(2), "fps": storyboard.get("fps", 30),
                    "frames": frames, "duration": duration, "width": width, "height": height}
            (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({**meta, "output": str(out_dir), "console_errors": console_errors},
                             ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    main()
