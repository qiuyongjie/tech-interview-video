#!/usr/bin/env python3
"""render_scene.py — 用 Playwright 无头浏览器确定性渲染场景帧。

用法:
    渲染单帧(关键帧预览):  python render_scene.py scenes/scene_03.html --frame 0.5 --out keyframes/
    渲染整段帧序列:       python render_scene.py scenes/scene_03.html --frames 180 --out frames/scene_03/

场景 HTML 契约 (见 references/canvas-patterns.md 第 4 节):
    - 画布 1920x1080
    - window.__render(ctx, t) 纯函数, t ∈ [0,1]

依赖: pip install playwright && playwright install chromium
"""
import argparse
import base64
import sys
from pathlib import Path

CANVAS_W, CANVAS_H = 1920, 1080


def render_batch(html_path: Path, out_dir: Path, total: int, samples=None):
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    ts = samples if samples is not None else [i / total for i in range(total)]
    prefix = "sample" if samples is not None else "frame"

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-device-scale-factor=1"])
        page = browser.new_page(viewport={"width": CANVAS_W, "height": CANVAS_H})
        page.goto(html_path.resolve().as_uri())
        page.wait_for_function("() => typeof window.__render === 'function'")

        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        for n, t in enumerate(ts):
            png = page.evaluate(
                """(t) => {
                    const c = document.getElementById('c');
                    window.__render(c.getContext('2d'), t);
                    return c.toDataURL('image/png').split(',')[1];
                }""", t)
            f = out_dir / f"{prefix}_{n:05d}.png"
            f.write_bytes(base64.b64decode(png))
        browser.close()

    if errors:
        print("页面 JS 错误:", *errors, sep="\n  ")
        sys.exit(3)
    print(f"OK rendered {len(ts)} frame(s) -> {out_dir}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scene_html", type=Path)
    ap.add_argument("--frame", type=float, default=None,
                    help="渲染单个 t∈[0,1] 帧 (关键帧预览)")
    ap.add_argument("--frames", type=int, default=None,
                    help="批量渲染帧数 (整段场景)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    if (args.frame is None) == (args.frames is None):
        ap.error("必须且只能指定 --frame 或 --frames 之一")

    if args.frame is not None:
        render_batch(args.scene_html, args.out, 0, samples=[args.frame])
    else:
        render_batch(args.scene_html, args.out, args.frames)


if __name__ == "__main__":
    main()
