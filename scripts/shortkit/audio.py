"""Audio: trim silence per line, join into one voice track, and build per-frame mouth envelopes."""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 48000


def decode(path: Path, trim: bool, threshold_db: float, keep_s: float) -> np.ndarray:
    """Decode any audio file to mono float32 @48k, optionally trimming leading/trailing silence."""
    filters = []
    if trim:
        sil = (
            f"silenceremove=start_periods=1:start_threshold={threshold_db}dB:"
            f"start_silence={keep_s}:detection=rms"
        )
        # trim the start, reverse, trim the (old) end, reverse back
        filters = [sil, "areverse", sil, "areverse"]
    cmd = ["ffmpeg", "-v", "error", "-i", str(path)]
    if filters:
        cmd += ["-af", ",".join(filters)]
    cmd += ["-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    audio = np.frombuffer(raw, dtype=np.float32).copy()
    if audio.size == 0:
        raise RuntimeError(f"{path.name}: nothing left after trimming silence (threshold {threshold_db} dB too high?)")
    # 8 ms fades so the cut points never click
    n = min(int(0.008 * SR), audio.size // 2)
    ramp = np.linspace(0, 1, n, dtype=np.float32)
    audio[:n] *= ramp
    audio[-n:] *= ramp[::-1]
    return audio


def write_wav(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def loudness_envelope(audio: np.ndarray, fps: int, floor_db: float = -42.0, ceil_db: float = -14.0) -> np.ndarray:
    """Per-video-frame mouth openness 0..1 from RMS loudness, smoothed so the mouth never chatters."""
    hop = SR / fps
    n_frames = int(np.ceil(audio.size / hop))
    win = int(hop * 1.5)
    out = np.zeros(n_frames, dtype=np.float32)
    for f in range(n_frames):
        c = int((f + 0.5) * hop)
        seg = audio[max(0, c - win // 2): c + win // 2]
        rms = float(np.sqrt(np.mean(seg ** 2))) if seg.size else 0.0
        db = 20 * np.log10(rms + 1e-9)
        out[f] = np.clip((db - floor_db) / (ceil_db - floor_db), 0, 1)
    # gentle curve: small sounds open a little, loud vowels open fully
    out = out ** 1.3
    # attack/release smoothing (fast open, slower close)
    sm = np.zeros_like(out)
    prev = 0.0
    for i, v in enumerate(out):
        k = 0.65 if v > prev else 0.35
        prev = prev + (v - prev) * k
        sm[i] = prev
    sm[sm < 0.04] = 0.0
    return sm


def build_voice_track(items, cfg, out_wav: Path):
    """items: list of (index, speaker, path). Returns placements [{index, speaker, start, end, audio}]."""
    a = cfg["audio"]
    pieces = []
    t = float(a["leadIn"])
    cursor = int(round(t * SR))
    chunks = [np.zeros(cursor, dtype=np.float32)]
    for n, (index, speaker, path, pause_before) in enumerate(items):
        if n > 0:
            gap = int(round(pause_before * SR))
            chunks.append(np.zeros(gap, dtype=np.float32))
            cursor += gap
        clip = decode(path, a["trimSilence"], a["silenceThresholdDb"], a["keepSilence"])
        start = cursor / SR
        chunks.append(clip)
        cursor += clip.size
        pieces.append({"index": index, "speaker": speaker, "start": start, "end": cursor / SR, "audio": clip})
    tail = int(round(float(a["tail"]) * SR))
    chunks.append(np.zeros(tail, dtype=np.float32))
    voice = np.concatenate(chunks)
    peak = float(np.max(np.abs(voice))) or 1.0
    gain = min(1.0, 0.95 / peak)
    voice *= gain
    write_wav(out_wav, voice)
    for p in pieces:
        p["audio"] = p["audio"] * gain
    return pieces, voice.size / SR
