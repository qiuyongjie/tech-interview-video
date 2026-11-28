#!/usr/bin/env python3
"""Visual QA: frozen cue frames, layout checks, console errors, contact sheet."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from render_scene import build_harness


def check_boxes(boxes: list[dict], width: int, height: int, style: dict, scale: float = 1.0) -> list[dict]:
    issues: list[dict] = []
    margin = int(style.get("margin", 96)) * scale
    top = int(style.get("safe_top", 120)) * scale
    bottom = int(style.get("safe_bottom", 180)) * scale
    for b in boxes:
        label = b.get("label", "")
        if b["x"] < 0 or b["y"] < 0 or b["x"] + b["w"] > width or b["y"] + b["h"] > height:
            issues.append({"type": "off-frame", "text": label, "box": b})
        elif (b["x"] < margin or b["x"] + b["w"] > width - margin
              or b["y"] < top or b["y"] + b["h"] > height - bottom):
            issues.append({"type": "margin", "text": label, "box": b})
        if b.get("size", 99) < 24 * scale:
            issues.append({"type": "font-too-small", "text": label, "size": b["size"]})
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            ox = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
            oy = max(0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
            overlap = ox * oy
            smaller = min(a["w"] * a["h"], b["w"] * b["h"])
            if smaller > 0 and overlap / smaller > 0.25:
                issues.append({"type": "overlap", "text": a.get("label", ""),
                               "other": b.get("label", "")})
    return issues


def make_contact(images: list[tuple[Image.Image, str]], out: Path) -> None:
    if not images:
        return
    thumb_w, thumb_h, label_h, cols = 480, 270, 30, 3
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + label_h)), "#101522")
    draw = ImageDraw.Draw(sheet)
    for idx, (im, label) in enumerate(images):
        x = (idx % cols) * thumb_w
        y = (idx // cols) * (thumb_h + label_h)
        sheet.paste(im.convert("RGB").resize((thumb_w, thumb_h), Image.LANCZOS), (x, y))
        draw.text((x + 8, y + thumb_h + 6), label, fill="#E8EDF7")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--scenes", help="comma-separated scene ids; default all")
    ap.add_argument("--contact", action="store_true", help="write keyframes/contact.png")
    ap.add_argument("--draft", action="store_true")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    storyboard = json.loads((project / "storyboard.json").read_text(encoding="utf-8"))
    sb_scenes = {str(s["id"]).zfill(2): s for s in storyboard.get("scenes", [])}
    timeline = json.loads((project / "audio" / "timeline.json").read_text(encoding="utf-8"))
    style = storyboard.get("style_tokens", {})
    base_w, base_h = storyboard.get("resolution", [1920, 1080])
    width = 640 if args.draft else int(base_w)
    height = round(640 * base_h / base_w) if args.draft else int(base_h)
    scenes = timeline["scenes"]
    if args.scenes:
        wanted = {s.strip().zfill(2) for s in args.scenes.split(",")}
        scenes = [s for s in scenes if str(s["id"]).zfill(2) in wanted]

    from playwright.sync_api import sync_playwright

    report: dict = {"schema_version": "2.0", "scenes": {}, "issues": [], "contact": None}
    contact_images: list[tuple[Image.Image, str]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for scene in scenes:
            sid = str(scene["id"]).zfill(2)
            duration = float(scene["duration"])
            harness = build_harness(project, sid, width, height)
            page = browser.new_page(viewport={"width": width, "height": height})
            errors: list[str] = []
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.goto(harness.as_uri(), wait_until="load")
            page.wait_for_function("window.__READY === true", timeout=20000)

            samples: list[tuple[float, str]] = []
            for cue in scene.get("cues", []):
                samples.append((min(cue["start"] + 0.05, duration - 0.01) / duration,
                                f"{sid}/{cue['id']} @ {cue['start']:.2f}s"))
            samples.append((0.5, f"{sid}/mid"))
            samples.append((0.995, f"{sid}/end"))

            scene_issues: list[dict] = []
            max_boxes = 0
            best_t = 0.0
            best_shot: bytes | None = None
            if duration > 10:
                scene_issues.append({"type": "long-shot", "scene": sid,
                                     "detail": f"{duration:.2f}s > 10s"})
            for idx, (t, label) in enumerate(samples):
                result = page.evaluate("(p) => window.__renderFrame(p)", t)
                if result.get("error"):
                    scene_issues.append({"type": "console-error", "scene": sid,
                                         "detail": result["error"][:300]})
                    continue
                scene_issues.extend({"scene": sid, "frame": label, **issue}
                                    for issue in check_boxes(result["boxes"], width, height, style,
                                                             width / float(base_w)))
                import io
                shot = page.locator("#stage").screenshot()
                if len(result["boxes"]) > max_boxes:
                    max_boxes = len(result["boxes"])
                    best_t = t
                    best_shot = shot
                if args.contact:
                    contact_images.append((Image.open(io.BytesIO(shot)), f"{label}"))
            if best_shot:
                page.evaluate("(p) => window.__renderFrame(p)", min(best_t + 0.012, 0.999))
                shot2 = page.locator("#stage").screenshot()
                import numpy as np
                a = np.asarray(Image.open(io.BytesIO(best_shot)).convert("L"), dtype=np.int16)
                b = np.asarray(Image.open(io.BytesIO(shot2)).convert("L"), dtype=np.int16)
                ratio = float((np.abs(a - b) > 8).mean())
                if ratio < 0.002:
                    scene_issues.append({"type": "static-frame", "scene": sid,
                                         "detail": f"only {ratio:.4%} pixels changed between adjacent frames"})
            sc = sb_scenes.get(sid, {})
            expected_cards = (sc.get("kit_params") or {}).get("cards") or []
            if sc.get("render_kit") in ("three_cards", "summary", "requirements") and expected_cards:
                needed = len(expected_cards) + 1
                if max_boxes < needed:
                    scene_issues.append({"type": "missing-content", "scene": sid,
                                         "detail": f"expected >= {needed} text boxes (title + cards), got {max_boxes}"})
            for err in errors:
                scene_issues.append({"type": "console-error", "scene": sid, "detail": err[:300]})
            report["scenes"][sid] = {"duration": duration, "frames_checked": len(samples)}
            report["issues"].extend(scene_issues)
            page.close()
        browser.close()

    if args.contact and contact_images:
        target = project / "keyframes" / "contact.png"
        make_contact(contact_images, target)
        report["contact"] = str(target)
    report["passed"] = not report["issues"]
    out = project / "qa" / "report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(out), "issues": len(report["issues"]),
                      "passed": report["passed"], "contact": report["contact"]}, ensure_ascii=False))
    if report["issues"]:
        for issue in report["issues"][:12]:
            print("  -", issue["type"], issue.get("scene", ""), issue.get("text", issue.get("detail", "")))


if __name__ == "__main__":
    main()
