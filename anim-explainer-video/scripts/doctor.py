#!/usr/bin/env python3
"""Check dependencies required by the anim-explainer-video pipeline."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

CRITICAL = {"ffmpeg", "ffprobe", "playwright-chromium", "tts-provider"}


def module_ok(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def tool_version(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if out.returncode != 0:
            return None
        return (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr).strip() else "ok"
    except (OSError, subprocess.SubprocessError):
        return None


def chromium_path() -> Path | None:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            exe = p.chromium.executable_path
            return Path(exe) if Path(exe).exists() else None
    except Exception:
        return None


def tts_status() -> tuple[bool, str]:
    if module_ok("edge_tts"):
        return True, "edge-tts ready (default)"
    if __import__("os").environ.get("AZURE_SPEECH_KEY") and __import__("os").environ.get("AZURE_REGION"):
        return True, "azure credentials ready"
    if __import__("os").environ.get("ELEVENLABS_API_KEY"):
        return True, "elevenlabs credentials ready"
    return False, "no TTS provider"


def run() -> dict:
    results: dict[str, dict] = {}

    def add(name: str, ok: bool, detail: str, hint: str = "") -> None:
        results[name] = {"ok": ok, "detail": detail, "hint": hint}

    v = tool_version(["ffmpeg", "-version"])
    add("ffmpeg", bool(v), v or "missing", "Windows: winget install ffmpeg")
    v = tool_version(["ffprobe", "-version"])
    add("ffprobe", bool(v), v or "missing", "usually installed with ffmpeg")
    add("python", sys.version_info >= (3, 9), sys.version.split()[0], "Python 3.9+ required")

    for mod in ("edge_tts", "playwright", "PIL", "numpy", "requests"):
        add("module:" + mod, module_ok(mod), "installed" if module_ok(mod) else "missing",
            "pip install " + {"edge_tts": "edge-tts", "PIL": "pillow"}.get(mod, mod))

    cp = chromium_path()
    add("playwright-chromium", bool(cp), str(cp) if cp else "browser not installed",
        "python -m playwright install chromium")

    ok, detail = tts_status()
    add("tts-provider", ok, detail, "pip install edge-tts  (or set Azure/ElevenLabs credentials)")

    fonts = [f for f in ("msyh.ttc", "simhei.ttf") if (Path("C:/Windows/Fonts") / f).exists()]
    add("cjk-font", bool(fonts) or sys.platform != "win32",
        ", ".join(fonts) if fonts else "no Windows CJK font found (check font config)", "")

    missing = [k for k, val in results.items() if not val["ok"]]
    blocked = [k for k in missing if k in CRITICAL]
    return {"results": results, "missing": missing, "blocked": blocked, "ready": not blocked}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = ap.parse_args()
    report = run()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        width = max(len(k) for k in report["results"])
        for key, val in report["results"].items():
            flag = "OK  " if val["ok"] else "MISS"
            print(f"{flag} {key:<{width}}  {val['detail']}")
            if not val["ok"] and val["hint"]:
                print(f"      -> {val['hint']}")
        print("\nREADY" if report["ready"] else "\nNOT READY: resolve the MISS items above")
    sys.exit(0 if report["ready"] else 1)


if __name__ == "__main__":
    main()
