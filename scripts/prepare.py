#!/usr/bin/env python3
"""Build everything Remotion needs from your raw files.

    python3 scripts/prepare.py --src /Users/you/Documents/Youtube

Expects in --src:
    stills/   S1*.png ... S6*.png  (any of png/jpg/webp)
    audio/    01_me.mp3, 02_sidekick.mp3, ...  (one file per line)
    script.md each line, which shot it uses (see scripts/shortkit/script_parser.py for formats)

Writes public/generated/: voice.wav, plates, cutouts, jaw pieces, timeline.json, debug/*.jpg
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shortkit.audio import SR, build_voice_track, loudness_envelope  # noqa: E402
from shortkit.script_parser import parse_script  # noqa: E402

DEFAULTS = {
    "source": "",
    "fps": 30,
    "width": 1080,
    "height": 1920,
    "audio": {
        "trimSilence": True,
        "silenceThresholdDb": -45,
        "keepSilence": 0.06,
        "leadIn": 0.25,
        "pause": 0.28,
        "emphasisPause": 0.55,
        "tail": 0.9,
    },
    "whisper": {"model": "small.en", "language": "en"},
    "stills": {"scale": 1.5, "cutoutModel": "isnet-general-use", "fillGrow": 0.018},
    "shotFaces": {
        "S1": ["me", "sidekick"],
        "S2": ["me"],
        "S3": ["sidekick"],
        "S4": ["me"],
        "S5": ["sidekick"],
        "S6": ["me", "sidekick"],
    },
    "defaultShot": {"me": "S2", "sidekick": "S3"},
    "camera": {"pushIn": 0.06, "emphasisPushIn": 0.16, "breath": 0.007, "breathSeconds": 3.8},
    "mouth": {"maxOpen": 0.26, "color": "#2b0d10", "speakerOnly": True},
    "captions": {
        "font": "Montserrat",
        "weight": 800,
        "size": 80,
        "maxWords": 3,
        "color": "#ffffff",
        "highlight": "#ffe14d",
        "stroke": "#000000",
        "uppercase": False,
        "preferY": [0.7, 0.62, 0.24, 0.4, 0.82],
        "positions": {},
    },
    "fx": {},
    "cards": [],
    "rig": {},
}

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".aiff", ".aif"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def _np(o):
    return o.item() if hasattr(o, "item") else o.tolist()


def norm_word(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", help="folder with stills/, audio/, script.md")
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--force", action="store_true", help="redo cutouts even if cached")
    ap.add_argument("--skip-whisper", action="store_true", help="spread words evenly instead of Whisper")
    args = ap.parse_args()

    user_cfg = json.loads(Path(args.config).read_text()) if Path(args.config).exists() else {}
    cfg = deep_merge(DEFAULTS, user_cfg)
    src = Path(args.src or cfg["source"] or ROOT / "input").expanduser().resolve()
    out = ROOT / "public" / "generated"
    out.mkdir(parents=True, exist_ok=True)
    fps = cfg["fps"]
    print(f"source: {src}")

    # ------------------------------------------------------------------ inputs
    audio_dir = src / "audio"
    files = []
    for p in sorted(audio_dir.iterdir()) if audio_dir.exists() else []:
        m = re.match(r"^(\d+)[\s_\-.]*([A-Za-z][\w\-]*)?", p.stem)
        if p.suffix.lower() in AUDIO_EXT and m:
            files.append((int(m.group(1)), (m.group(2) or "me").lower(), p))
    if not files:
        sys.exit(f"no audio files like 01_me.mp3 in {audio_dir}")
    files.sort()
    speakers = sorted({s for _, s, _ in files})

    script_path = next((p for p in [src / "script.md", src / "Script.md", src / "SCRIPT.md"] if p.exists()), None)
    script = parse_script(script_path.read_text(encoding="utf-8"), speakers) if script_path else []
    by_index = {l.index: l for l in script}
    if script and not all(i in by_index for i, _, _ in files):
        # numbering in script.md doesn't match filenames: fall back to order
        by_index = {files[n][0]: l for n, l in enumerate(script) if n < len(files)}
    print(f"{len(files)} audio lines, {len(script)} script lines, speakers: {speakers}")

    stills = {}
    for p in sorted((src / "stills").iterdir()) if (src / "stills").exists() else []:
        m = re.match(r"^(S\d+)", p.stem, re.I)
        if m and p.suffix.lower() in IMG_EXT:
            stills.setdefault(m.group(1).upper(), p)
    if not stills:
        sys.exit(f"no stills named S1..S6 in {src / 'stills'}")
    print(f"stills: {', '.join(f'{k}={v.name}' for k, v in stills.items())}")

    lines = []
    for n, (idx, speaker, path) in enumerate(files):
        sl = by_index.get(idx)
        shot = (sl.shot if sl and sl.shot else None) or cfg["defaultShot"].get(speaker) or next(iter(stills))
        if shot not in stills:
            print(f"  ! line {idx:02d} wants {shot} but there is no such still; using {next(iter(stills))}")
            shot = next(iter(stills))
        lines.append({
            "index": idx, "speaker": speaker, "file": path.name, "shot": shot,
            "text": sl.text if sl else "", "expression": sl.expression if sl else "neutral",
            "react": sl.react if sl else None, "emphasis": bool(sl and sl.emphasis),
        })

    # ------------------------------------------------------------------ 1. audio
    print("1/4 trimming silence and joining lines ...")
    items = [(l["index"], l["speaker"], audio_dir / l["file"],
              cfg["audio"]["emphasisPause"] if l["emphasis"] else cfg["audio"]["pause"]) for l in lines]
    placed, total_s = build_voice_track(items, cfg, out / "voice.wav")
    total_frames = int(np.ceil(total_s * fps))

    # ------------------------------------------------------------------ 2. whisper
    print("2/4 word timings ...")
    from shortkit.transcribe import word_timings

    words = []
    for l, p in zip(lines, placed):
        l["start"], l["end"] = p["start"], p["end"]
        if args.skip_whisper:
            from shortkit.transcribe import _even_split

            ws, how = _even_split(l["text"].split(), p["end"] - p["start"]), "even-split"
        else:
            ws, how = word_timings(p["audio"], l["text"], cfg["whisper"]["model"], cfg["whisper"]["language"])
        if not l["text"]:
            l["text"] = " ".join(w["text"] for w in ws)
        for w in ws:
            words.append({"text": w["text"], "start": round(p["start"] + w["start"], 3),
                          "end": round(p["start"] + w["end"], 3), "line": l["index"]})
        print(f"   {l['index']:02d} {l['speaker']:<9} {l['shot']}  [{how}]  {l['text'][:60]}")

    # mouth envelopes per speaker
    env = {}
    for sp in speakers:
        track = np.zeros(int(total_s * SR) + 1, np.float32)
        for p in placed:
            if p["speaker"] == sp:
                s = int(round(p["start"] * SR))
                track[s: s + p["audio"].size] = p["audio"][: max(0, track.size - s)]
        env[sp] = [round(float(v), 3) for v in loudness_envelope(track, fps)[:total_frames]]

    # ------------------------------------------------------------------ 3. shots / rig
    print("3/4 cutouts, background fill, face rig ...")
    from shortkit.rig import build_shot

    cache_file = out / "rig_cache.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    shots = {}
    for sid in sorted({l["shot"] for l in lines} | set(stills)):
        path = stills[sid]
        key_src = json.dumps([path.stat().st_mtime, path.stat().st_size, cfg["stills"], cfg["shotFaces"].get(sid),
                              cfg["rig"].get(sid), cfg["captions"]["positions"].get(sid), cfg["captions"]["preferY"],
                              cfg["width"], cfg["height"], 5])
        key = hashlib.sha1(key_src.encode()).hexdigest()
        if not args.force and sid in cache and cache[sid]["key"] == key and (out / f"{sid}_plate.jpg").exists():
            shots[sid] = cache[sid]["shot"]
            print(f"  {sid}: cached")
            continue
        shots[sid] = build_shot(sid, path, cfg, out, ROOT / ".cache", cfg["shotFaces"].get(sid, []))
        cache[sid] = {"key": key, "shot": shots[sid]}
        cache_file.write_text(json.dumps(cache, default=_np))

    # ------------------------------------------------------------------ 4. timeline
    print("4/4 timeline ...")
    segments = []
    for n, l in enumerate(lines):
        if n == 0:
            cut = 0
        else:
            prev_end = lines[n - 1]["end"]
            cut = int(round(max(prev_end + 0.05, l["start"] - 0.12) * fps))
        segments.append({"line": l["index"], "shot": l["shot"], "from": cut})
    for n, s in enumerate(segments):
        s["to"] = segments[n + 1]["from"] if n + 1 < len(segments) else total_frames
    # merge consecutive lines on the same shot into one continuous push-in
    merged = []
    for s in segments:
        if merged and merged[-1]["shot"] == s["shot"]:
            merged[-1]["to"] = s["to"]
            merged[-1]["lines"].append(s["line"])
        else:
            merged.append({**s, "lines": [s["line"]]})
    for s in merged:
        s.pop("line")
        ls = [l for l in lines if l["index"] in s["lines"]]
        s["emphasis"] = any(l["emphasis"] for l in ls)

    for l in lines:
        l["startFrame"] = l["start"] * fps
        l["endFrame"] = l["end"] * fps

    cards = []
    for c in cfg["cards"]:
        ls = [l for l in lines if c.get("fromLine", -1) <= l["index"] <= c.get("toLine", c.get("fromLine", -1))]
        if not ls:
            print(f"  ! card '{c.get('title')}' refers to lines that don't exist")
            continue
        start, end = ls[0]["start"] - 0.1, ls[-1]["end"] + c.get("hold", 0.6)
        steps = c.get("steps", [])
        rev = []
        for k, st in enumerate(steps):
            st = st if isinstance(st, dict) else {"text": st}
            t = start + 0.35 + k * min(0.7, (end - start - 0.5) / max(1, len(steps)))
            if st.get("word"):
                target = norm_word(st["word"])
                hit = next((w for w in words if w["line"] in [l["index"] for l in ls] and norm_word(w["text"]) == target), None)
                if hit:
                    t = hit["start"]
                else:
                    print(f"  ! step word '{st['word']}' not spoken in lines {c.get('fromLine')}-{c.get('toLine')}")
            rev.append({"text": st["text"], "at": round(t * fps, 2), "icon": st.get("icon")})
        cards.append({"title": c.get("title", ""), "from": round(start * fps, 2), "to": round(end * fps, 2),
                      "position": c.get("position", "auto"), "steps": rev, "accent": c.get("accent", "#ffe14d")})

    timeline = {
        "fps": fps, "width": cfg["width"], "height": cfg["height"], "durationInFrames": total_frames,
        "audio": "generated/voice.wav", "lines": lines, "words": words, "segments": merged,
        "envelopes": env, "shots": shots, "cards": cards, "fx": cfg["fx"],
        "camera": cfg["camera"], "mouth": cfg["mouth"], "captions": cfg["captions"],
        "builtAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (out / "timeline.json").write_text(json.dumps(timeline, indent=1, default=_np))
    print(f"done: {total_s:.1f}s, {total_frames} frames, {len(merged)} cuts -> public/generated/timeline.json")
    print("check the face rig in public/generated/debug/*.jpg, then: npm run studio")


if __name__ == "__main__":
    main()
