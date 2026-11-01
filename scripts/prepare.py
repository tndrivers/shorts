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
    # audio folder name -> speaker name used in script.md / shotFaces ("_audio" is stripped first)
    "speakerAliases": {"main_character": "me", "main": "me", "maincharacter": "me", "hero": "me",
                       "buddy": "sidekick", "friend": "sidekick", "side": "sidekick"},
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


def natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(p))]


def speaker_name(folder: str, aliases: dict) -> str:
    n = folder.strip().lower()
    n = re.sub(r"[\s_\-]*(audio|voice|vo|lines|clips)$", "", n)
    n = re.sub(r"[\s\-]+", "_", n)
    return aliases.get(n, n)


def discover_audio(audio_dir: Path, aliases: dict):
    """Find voice lines in audio/ and any subfolders. Returns [(index|None, speaker|None, path)].

    Filenames can be anything. The speaker comes from the folder (audio/me/..., audio/sidekick/...);
    a line number is only taken from a number at the very START of the name (01_x.mp3, "3 - hey.wav")
    or from a numbered folder, so dates/timestamps in exported names are ignored.
    """
    if not audio_dir.exists():
        sys.exit(f"audio folder not found: {audio_dir}")
    found = []
    for p in sorted(audio_dir.rglob("*"), key=natural_key):
        if not p.is_file() or p.name.startswith(".") or p.suffix.lower() not in AUDIO_EXT:
            continue
        folders = list(p.relative_to(audio_dir).parts[:-1])
        num = re.match(r"^\s*(\d{1,3})(?!\d)", p.stem)
        index = int(num.group(1)) if num else None
        if index is None:
            index = next((int(f) for f in reversed(folders) if re.fullmatch(r"\d{1,3}", f)), None)
        speaker = next((speaker_name(f, aliases) for f in reversed(folders) if not re.fullmatch(r"[\d\s_\-]+", f)), None)
        if speaker is None and num:  # 01_me.mp3 style
            m = re.match(r"^\s*\d{1,3}[\s_\-.]*([A-Za-z][\w\-]*)", p.stem)
            speaker = m.group(1).lower() if m else None
        found.append((index, speaker, p))
    if not found:
        listing = "\n".join(f"  {q.relative_to(audio_dir)}" for q in sorted(audio_dir.rglob("*"))[:40]) or "  (empty)"
        sys.exit(f"no audio files ({', '.join(sorted(AUDIO_EXT))}) found in {audio_dir}\nwhat's there:\n{listing}")
    return found


def _words(t: str):
    return [w for w in (norm_word(x) for x in t.split()) if w]


def resolve_order(files, script, audio_dir, cfg, use_whisper=True):
    """Decide which audio file is which script line. Returns [(index, speaker, path)] in video order.

    1. config.json "audioMap"  {"1": "me/take 3.mp3", ...}  -> exactly that
    2. every file starts with a unique number (01_...)     -> that order
    3. script.md has the text and Whisper is installed     -> match by what is said (speaker folder respected)
    4. script.md names speakers                            -> k-th file in a speaker's folder = their k-th line
    5. otherwise                                           -> alphabetical order
    """
    by_path = {str(p.relative_to(audio_dir)): (i, sp, p) for i, sp, p in files}
    how = ""
    if script and all(l.file for l in script):
        out = []
        for l in script:
            hit = by_path.get(l.file) or next((v for k, v in by_path.items() if Path(k).name == Path(l.file).name), None)
            if not hit:
                sys.exit(f'script.md line {l.index}: audio file "{l.file}" not found in {audio_dir}')
            out.append((l.index, l.speaker or hit[1] or "me", hit[2]))
        how = "File column in script.md"
    elif cfg.get("audioMap"):
        out = []
        for k, rel in sorted(cfg["audioMap"].items(), key=lambda kv: int(kv[0])):
            if rel not in by_path:
                sys.exit(f'audioMap: "{rel}" not found in {audio_dir}')
            _, sp, p = by_path[rel]
            line = next((l for l in script if l.index == int(k)), None)
            out.append((int(k), (line.speaker if line and line.speaker else sp) or "me", p))
        how = "config.json audioMap"
    elif all(i is not None for i, _, _ in files) and len({i for i, _, _ in files}) == len(files):
        out = sorted(((i, sp or "me", p) for i, sp, p in files), key=lambda f: f[0])
        how = "numbers at the start of the filenames"
    else:
        out = None
        if script and all(l.text for l in script) and use_whisper:
            out = _match_by_content(files, script, cfg)
            how = "matching what's said to script.md (Whisper)"
        if out is None and script and all(l.speaker for l in script):
            by_sp = {}
            for _, sp, p in files:
                by_sp.setdefault(sp, []).append(p)
            if None in by_sp or not set(l.speaker for l in script) <= set(by_sp):
                sys.exit("Can't tell which file is which line: put each speaker's files in a folder named like the "
                         f"speaker in script.md ({sorted(set(l.speaker for l in script))}), install Whisper, "
                         "or list them in config.json \"audioMap\".")
            out, used = [], {sp: 0 for sp in by_sp}
            for l in script:
                if used[l.speaker] >= len(by_sp[l.speaker]):
                    sys.exit(f"script.md has more '{l.speaker}' lines than files in audio/{l.speaker}/")
                out.append((l.index, l.speaker, by_sp[l.speaker][used[l.speaker]]))
                used[l.speaker] += 1
            how = "speaker folders, files in name order (no Whisper to match by content)"
        if out is None:
            out = [(n + 1, sp or "me", p) for n, (_, sp, p) in enumerate(files)]
            how = "alphabetical order (no script.md speakers / Whisper)"
    used_paths = {p for _, _, p in out}
    print(f"audio -> lines ({how}):")
    for i, sp, p in out:
        print(f"   {i:02d}  {sp:<10} {p.relative_to(audio_dir)}")
    for _, _, p in files:
        if p not in used_paths:
            print(f"  ! not used: {p.relative_to(audio_dir)}")
    print("   (wrong? pin it in config.json, e.g. \"audioMap\": {\"1\": \"me/file.mp3\", ...})")
    return out


def _match_by_content(files, script, cfg):
    from shortkit.audio import decode
    from shortkit import transcribe as tr

    heard = []
    for _, sp, p in files:
        audio = decode(p, True, cfg["audio"]["silenceThresholdDb"], cfg["audio"]["keepSilence"])
        ws = tr._whisper_words(audio, cfg["whisper"]["model"], cfg["whisper"]["language"], "")
        if ws is None:
            return None  # no Whisper installed
        heard.append(" ".join(w["text"] for w in ws))
    import difflib

    scores = []
    for fi, (_, sp, p) in enumerate(files):
        hw = _words(heard[fi])
        for li, l in enumerate(script):
            if sp and l.speaker and sp != l.speaker.lower():
                continue  # different speaker folder
            sc = difflib.SequenceMatcher(a=hw, b=_words(l.text), autojunk=False).ratio()
            scores.append((sc, fi, li))
    scores.sort(reverse=True)
    f_used, l_used, pairs = set(), set(), {}
    for sc, fi, li in scores:
        if fi in f_used or li in l_used:
            continue
        f_used.add(fi)
        l_used.add(li)
        pairs[li] = (fi, sc)
    out = []
    for li, l in enumerate(script):
        if li not in pairs:
            print(f"  ! no audio file matched line {l.index}: {l.text[:50]}")
            continue
        fi, sc = pairs[li]
        _, sp, p = files[fi]
        flag = "" if sc >= 0.5 else f"   <-- weak match ({sc:.0%}), heard: \"{heard[fi][:50]}\""
        if flag:
            print(f"  ! line {l.index:02d} -> {p.name}{flag}")
        out.append((l.index, l.speaker or sp or "me", p))
    return out


def stills_hint(src: Path):
    d = src / "stills"
    return sorted({m.group(1).upper() for p in (d.iterdir() if d.exists() else []) if (m := re.match(r"^(S\d+)", p.stem, re.I))})


def write_draft_script(src, files, audio_dir, cfg, stills, use_whisper=True):
    """No script.md yet: transcribe every clip and write a draft to reorder and fill in."""
    from shortkit.audio import decode
    from shortkit import transcribe as tr

    print("no script.md found - transcribing every clip to write a draft ...")
    rows = []
    for _, sp, p in files:
        text = ""
        if use_whisper:
            audio = decode(p, True, cfg["audio"]["silenceThresholdDb"], cfg["audio"]["keepSilence"])
            ws = tr._whisper_words(audio, cfg["whisper"]["model"], cfg["whisper"]["language"], "")
            text = " ".join(w["text"] for w in ws) if ws else ""
        stamp = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}_\d{2}_\d{2}", p.name)
        rows.append((stamp.group() if stamp else f"{p.stat().st_mtime:.0f}", sp or "me", p, text))
        print(f"   {sp or '?':<10} {p.name[:60]}  {text[:60]}")
    rows.sort(key=lambda r: r[0])
    shot_for = cfg["defaultShot"]
    lines = [
        "# Script",
        "",
        "Put the rows in the order they're spoken, renumber #, pick a Shot for each line,",
        "optionally an Expression (neutral / smug / soft / happy), and `yes` under Emphasis for the emotional line.",
        "Delete rows for takes you don't want. Then run prepare.py again.",
        f"Shots available: {', '.join(stills) or 'S1..S6'}",
        "",
        "| # | Speaker | Shot | Expression | Emphasis | React | Line | File |",
        "|---|---------|------|------------|----------|-------|------|------|",
    ]
    for n, (_, sp, p, text) in enumerate(rows, 1):
        lines.append(f"| {n:02d} | {sp} | {shot_for.get(sp, 'S1')} | | | | {text or '(type the line here)'} | {p.relative_to(audio_dir)} |")
    out = src / "script.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote a draft: {out}")
    print("Rows are in the order the clips were generated, NOT the conversation order.")
    print("Reorder them, set the shots, then run:  python3 scripts/prepare.py")


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
    files = discover_audio(audio_dir, cfg["speakerAliases"])
    speakers = sorted({s for _, s, _ in files if s}) or ["me", "sidekick"]

    script_path = next((p for p in [src / "script.md", src / "Script.md", src / "SCRIPT.md"] if p.exists()), None)
    script = parse_script(script_path.read_text(encoding="utf-8"), speakers) if script_path else []
    if not script:
        write_draft_script(src, files, audio_dir, cfg, stills_hint(src), use_whisper=not args.skip_whisper)
        return
    files = resolve_order(files, script, audio_dir, cfg, use_whisper=not args.skip_whisper)
    by_index = {l.index: l for l in script}
    if script and not all(i in by_index for i, _, _ in files) and len(script) == len(files):
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
            "index": idx, "speaker": speaker, "file": str(path.relative_to(audio_dir)), "shot": shot,
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
