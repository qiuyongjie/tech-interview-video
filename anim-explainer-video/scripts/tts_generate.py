#!/usr/bin/env python3
"""Audio-first TTS: per-sentence synthesis, exact sample timing, word boundaries, timeline.json."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import subprocess
import wave
import xml.sax.saxutils as xmlutil
from pathlib import Path

SAMPLE_RATE = 48000
SENTENCE_END = "。！？：!?:"
CLAUSE_END = "，、,；;—-"
DEFAULT_AUDITION = "zh-CN-YunxiNeural,zh-CN-XiaoxiaoNeural,zh-CN-YunyangNeural"


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *[str(a) for a in args]], check=True)


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def parse_rate(value: str) -> int:
    m = re.fullmatch(r"([+-]?\d+)%", value or "+0%")
    return int(m.group(1)) if m else 0


def parse_pitch(value: str) -> int:
    m = re.fullmatch(r"([+-]?\d+)Hz", value or "+0Hz")
    return int(m.group(1)) if m else 0


def guardrails(rate: str, pitch: str) -> tuple[str, str]:
    r = max(-5, min(8, parse_rate(rate)))
    p = max(-2, min(2, parse_pitch(pitch)))
    if r != parse_rate(rate):
        print(f"[warn] rate clamped to {r:+d}% (allowed -5%..+8%)")
    if p != parse_pitch(pitch):
        print(f"[warn] pitch clamped to {p:+d}Hz (allowed -2..+2Hz)")
    return f"{r:+d}%", f"{p:+d}Hz"


def prepare_text(text: str, lexicon: dict) -> str:
    result = text
    for key in sorted(lexicon, key=len, reverse=True):
        result = result.replace(key, str(lexicon[key]))
    return result


def pause_after(text: str) -> float:
    stripped = (text or "").strip()
    if not stripped:
        return 0.03
    if stripped[-1] in SENTENCE_END:
        return 0.35
    if stripped[-1] in CLAUSE_END:
        return 0.12
    return 0.03


async def synth_edge(text: str, voice: str, rate: str, pitch: str, out_mp3: Path) -> list[dict]:
    import edge_tts

    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    words: list[dict] = []
    with out_mp3.open("wb") as fh:
        async for event in comm.stream():
            kind = event.get("type")
            if kind == "audio":
                fh.write(event["data"])
            elif kind == "WordBoundary":
                start = event["offset"] / 1e7
                words.append({
                    "text": event["text"],
                    "start": round(start, 4),
                    "end": round((event["offset"] + event["duration"]) / 1e7, 4)
                })
    return words


def synth_azure(text: str, voice: str, rate: str, pitch: str) -> bytes:
    import requests

    key = os.environ["AZURE_SPEECH_KEY"]
    region = os.environ["AZURE_REGION"]
    ssml = (
        '<speak xmlns="http://www.w3.org/2001/10/Synthesis" '
        'xmlns:mstts="https://www.w3.org/2001/mstts" version="1.0" xml:lang="zh-CN">'
        f'<voice name="{xmlutil.escape(voice)}">'
        '<mstts:express-as style="narration-relaxed" styledegree="1.0">'
        f'<prosody rate="{xmlutil.escape(rate)}" pitch="{xmlutil.escape(pitch)}">'
        f"{xmlutil.escape(text)}</prosody></mstts:express-as></voice></speak>"
    )
    resp = requests.post(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
        },
        data=ssml.encode("utf-8"),
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content


def synth_elevenlabs(text: str, voice: str) -> bytes:
    import requests

    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Accept": "audio/mpeg"},
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.45, "similarity_boost": 0.75,
                "style": 0.15, "use_speaker_boost": True,
            },
        },
        timeout=90,
    )
    resp.raise_for_status()
    return resp.content


def segment_audio(text: str, cfg: dict, seg_dir: Path, force: bool) -> tuple[Path, list[dict], float]:
    provider = cfg["provider"]
    voice = cfg["voice"]
    rate, pitch = cfg["rate"], cfg["pitch"]
    key = hashlib.sha1(f"{provider}|{voice}|{rate}|{pitch}|{text}".encode("utf-8")).hexdigest()[:18]
    wav_path = seg_dir / f"{key}.wav"
    meta_path = seg_dir / f"{key}.json"
    if wav_path.exists() and meta_path.exists() and not force:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return wav_path, meta.get("words", []), wav_duration(wav_path)

    if provider == "edge":
        tmp = seg_dir / f"{key}.mp3"
        words = asyncio.run(synth_edge(text, voice, rate, pitch, tmp))
        ffmpeg("-i", tmp, "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", wav_path)
        tmp.unlink(missing_ok=True)
    else:
        if provider == "azure":
            payload = synth_azure(text, voice, rate, pitch)
        elif provider == "elevenlabs":
            payload = synth_elevenlabs(text, voice)
        else:
            raise ValueError(f"unknown provider: {provider}")
        raw = seg_dir / f"{key}.raw"
        raw.write_bytes(payload)
        ffmpeg("-i", raw, "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", wav_path)
        raw.unlink(missing_ok=True)
        words = []

    meta = {"text": text, "voice": voice, "provider": provider, "words": words,
            "duration": round(wav_duration(wav_path), 6)}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return wav_path, words, meta["duration"]


def silence_wav(seconds: float, seg_dir: Path) -> Path:
    ms = int(round(seconds * 1000))
    path = seg_dir / f"silence_{ms:05d}ms.wav"
    if not path.exists():
        ffmpeg("-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono",
               "-t", f"{seconds:.6f}", "-ar", str(SAMPLE_RATE), "-ac", "1",
               "-c:a", "pcm_s16le", path)
    return path


def concat_wavs(parts: list[Path], out: Path, seg_dir: Path) -> None:
    list_file = seg_dir / f"concat_{out.stem}.txt"
    list_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    ffmpeg("-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", out)
    list_file.unlink(missing_ok=True)


def audition(cfg: dict, audio_dir: Path, sample: str, voices: list[str]) -> None:
    out_dir = audio_dir / "audition"
    out_dir.mkdir(parents=True, exist_ok=True)
    for voice in voices:
        local = dict(cfg)
        local["voice"] = voice
        target = out_dir / f"{voice}.mp3"
        print(f"audition: {voice} -> {target}")
        tmp = out_dir / f"_{voice}.tmp.mp3"
        asyncio.run(synth_edge(sample, voice, "+0%", "+0Hz", tmp))
        tmp.replace(target)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--provider", choices=["edge", "azure", "elevenlabs"])
    ap.add_argument("--voice")
    ap.add_argument("--rate")
    ap.add_argument("--pitch")
    ap.add_argument("--audition", action="store_true")
    ap.add_argument("--audition-voices", default=DEFAULT_AUDITION)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    storyboard = json.loads((project / "storyboard.json").read_text(encoding="utf-8"))
    lexicon = json.loads((project / "lexicon.json").read_text(encoding="utf-8")) if (project / "lexicon.json").exists() else {}
    audio_dir = project / "audio"
    seg_dir = audio_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    cfg = dict(storyboard.get("audio", {}))
    cfg["provider"] = args.provider or cfg.get("provider", "edge")
    cfg["voice"] = args.voice or cfg.get("voice", "zh-CN-YunxiNeural")
    cfg["rate"], cfg["pitch"] = guardrails(args.rate or cfg.get("rate", "+0%"),
                                           args.pitch or cfg.get("pitch", "+0Hz"))

    if args.audition:
        sample = " ".join(c["text"] for s in storyboard["scenes"][:1] for c in s.get("narration", []))[:90]
        sample = sample or "我们先看一个例子，理解它是怎么一步步工作的。"
        audition(cfg, audio_dir, prepare_text(sample, lexicon),
                 [v.strip() for v in args.audition_voices.split(",") if v.strip()])
        return

    fps = int(storyboard.get("fps", 30))
    default_tail_ms = float(cfg.get("scene_tail_ms", 600))
    timeline = {
        "schema_version": "2.0",
        "provider": cfg["provider"],
        "voice": cfg["voice"],
        "rate": cfg["rate"],
        "pitch": cfg["pitch"],
        "total_duration": 0.0,
        "scenes": [],
    }
    full_parts: list[Path] = []
    abs_start = 0.0

    for scene in storyboard["scenes"]:
        parts: list[Path] = []
        cues: list[dict] = []
        local_time = 0.0
        for item in scene.get("narration", []):
            original = item["text"]
            spoken = prepare_text(original, lexicon)
            wav_path, words, duration = segment_audio(spoken, cfg, seg_dir, args.force)
            parts.append(wav_path)
            words_scene = [{"text": w["text"],
                            "start": round(local_time + w["start"], 4),
                            "end": round(local_time + w["end"], 4)} for w in words]
            cues.append({
                "id": item["id"],
                "text": original,
                "start": round(local_time, 4),
                "end": round(local_time + duration, 4),
                "duration": round(duration, 4),
                "words": words_scene,
            })
            local_time += duration
            gap = pause_after(original)
            if gap > 0:
                parts.append(silence_wav(gap, seg_dir))
                local_time += gap
            print(f"[{scene['id']}/{item['id']}] {duration:.3f}s + {gap:.2f}s pause")
        tail = float(scene.get("scene_tail_ms", default_tail_ms)) / 1000.0
        if tail > 0:
            parts.append(silence_wav(tail, seg_dir))
            local_time += tail

        if not parts:
            raise SystemExit(f"scene {scene['id']} has no narration")
        scene_wav = audio_dir / f"scene_{scene['id']}.wav"
        concat_wavs(parts, scene_wav, seg_dir)
        duration = wav_duration(scene_wav)
        timeline["scenes"].append({
            "id": scene["id"],
            "start": round(abs_start, 4),
            "duration": round(duration, 4),
            "frames": math.ceil(duration * fps),
            "cues": cues,
        })
        abs_start += duration
        full_parts.append(scene_wav)

    concat_wavs(full_parts, audio_dir / "narration_raw.wav", seg_dir)
    timeline["total_duration"] = round(wav_duration(audio_dir / "narration_raw.wav"), 4)
    (audio_dir / "timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"timeline written: {audio_dir / 'timeline.json'} ({timeline['total_duration']:.2f}s)")


if __name__ == "__main__":
    main()
