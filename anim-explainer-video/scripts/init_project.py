#!/usr/bin/env python3
"""Create an output project skeleton with runtime assets and storyboard contract."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent

SKELETON = {
    "schema_version": "2.0",
    "topic": "",
    "language": "zh-CN",
    "resolution": [1920, 1080],
    "fps": 30,
    "style_tokens": {
        "bg": "#0B1020",
        "surface": "#151D33",
        "text": "#E8EDF7",
        "muted": "#8A94A8",
        "entity": "#4CC9F0",
        "focus": "#FFD166",
        "relation": "#6B7A99",
        "good": "#06D6A0",
        "bad": "#EF476F",
        "assumption": "#B388FF",
        "quantity": "#F6C85F",
        "font_sans": "Microsoft YaHei",
        "font_mono": "Consolas",
        "title_px": 64,
        "heading_px": 44,
        "body_px": 34,
        "label_px": 26,
        "caption_px": 30,
        "margin": 96,
        "safe_top": 120,
        "safe_bottom": 180
    },
    "audio": {
        "provider": "edge",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "scene_tail_ms": 600
    },
    "scenes": [
        {
            "id": "01",
            "title": "开场",
            "intent": "一句话说清本片要解决的问题",
            "visual": "用生活比喻引入核心概念",
            "motion": "元素 stagger 入场，逐步揭示",
            "claims": [],
            "narration": [
                {"id": "s1", "text": "这里写第一句口语化旁白。"}
            ],
            "duration_hint": 8
        }
    ]
}

LEXICON = {
    "RAG": "R A G",
    "HashMap": "Hash Map",
    "JVM": "J V M",
    "O(n)": "O n",
    "API": "A P I"
}


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--topic", required=True, help="video topic / project title")
    ap.add_argument("--dir", required=True, help="output directory, e.g. output/my-topic")
    ap.add_argument("--force", action="store_true", help="overwrite existing storyboard.json")
    args = ap.parse_args()

    project = Path(args.dir).resolve()
    for sub in ("audio/segments", "audio/audition", "scenes", "runtime", "keyframes",
                "frames", "qa", "render"):
        (project / sub).mkdir(parents=True, exist_ok=True)

    runtime_src = SKILL_DIR / "assets"
    for name in ("scene-runtime.js", "scene-template.html"):
        shutil.copy2(runtime_src / name, project / "runtime" / name)

    sb_path = project / "storyboard.json"
    if sb_path.exists() and not args.force:
        raise SystemExit(f"Refusing to overwrite {sb_path}; use --force if intentional")
    skeleton = json.loads(json.dumps(SKELETON))
    skeleton["topic"] = args.topic
    write_json(sb_path, skeleton)
    write_json(project / "lexicon.json", LEXICON)

    print(f"Project ready: {project}")
    print("Next: fill storyboard.json, then run tts_generate.py --audition")


if __name__ == "__main__":
    main()
