"""Word-level timings with Whisper, snapped onto the script's own spelling."""
from __future__ import annotations

import difflib
import re
import tempfile
from pathlib import Path

import numpy as np

from .audio import SR, write_wav

_MODEL = None
_BACKEND = None


def _load(model_name: str):
    global _MODEL, _BACKEND
    if _MODEL is not None:
        return
    try:
        from faster_whisper import WhisperModel  # type: ignore

        _MODEL = WhisperModel(model_name, device="cpu", compute_type="int8")
        _BACKEND = "faster-whisper"
        return
    except ImportError:
        pass
    except Exception as e:  # model download blocked etc.
        print(f"  ! faster-whisper failed to load: {e}")
    try:
        import whisper  # type: ignore

        _MODEL = whisper.load_model(model_name)
        _BACKEND = "openai-whisper"
        return
    except ImportError:
        pass
    except Exception as e:
        print(f"  ! openai-whisper failed to load: {e}")
    _BACKEND = "none"


def _whisper_words(audio: np.ndarray, model_name: str, language: str | None, prompt: str):
    _load(model_name)
    if _BACKEND == "faster-whisper":
        a16 = audio[:: SR // 16000] if SR % 16000 == 0 else audio
        segs, _ = _MODEL.transcribe(
            a16.astype(np.float32), language=language, word_timestamps=True,
            initial_prompt=prompt or None, vad_filter=False, beam_size=5,
        )
        return [{"text": w.word.strip(), "start": float(w.start), "end": float(w.end)} for s in segs for w in s.words]
    if _BACKEND == "openai-whisper":
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "line.wav"
            write_wav(p, audio)
            res = _MODEL.transcribe(str(p), language=language, word_timestamps=True, initial_prompt=prompt or None)
        return [
            {"text": w["word"].strip(), "start": float(w["start"]), "end": float(w["end"])}
            for s in res["segments"] for w in s.get("words", [])
        ]
    return None


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower().replace("’", "'"))


def _even_split(words: list[str], dur: float, envelope_voiced=None):
    if not words:
        return []
    """Fallback without Whisper: spread words by character length across the line."""
    weights = np.array([max(2, len(w)) + 1.5 for w in words], dtype=float)
    edges = np.concatenate([[0], np.cumsum(weights)]) / weights.sum() * dur
    return [{"text": w, "start": float(edges[i]), "end": float(edges[i + 1])} for i, w in enumerate(words)]


def word_timings(audio: np.ndarray, script_text: str, model_name: str, language: str | None):
    """Return [{text, start, end}] relative to the line start. Uses script spelling when we have it."""
    dur = audio.size / SR
    script_words = script_text.split() if script_text else []
    heard = _whisper_words(audio, model_name, language, script_text)
    if heard is None:
        if not script_words:
            return [], "none"
        return _even_split(script_words, dur), "even-split (no Whisper installed)"
    heard = [w for w in heard if w["text"]]
    if not script_words:
        return heard, _BACKEND
    if not heard:
        return _even_split(script_words, dur), "even-split (Whisper heard nothing)"

    # Align script tokens to heard tokens and borrow the timings
    a = [_norm(w) for w in script_words]
    b = [_norm(w["text"]) for w in heard]
    out = [None] * len(script_words)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                h = heard[j1 + k]
                out[i1 + k] = {"text": script_words[i1 + k], "start": h["start"], "end": h["end"]}
        elif tag == "replace" and j2 > j1:
            # spread the script words over the heard span
            s, e = heard[j1]["start"], heard[j2 - 1]["end"]
            n = i2 - i1
            for k in range(n):
                out[i1 + k] = {"text": script_words[i1 + k], "start": s + (e - s) * k / n, "end": s + (e - s) * (k + 1) / n}
    # fill gaps (script words Whisper missed) by interpolation
    for i, w in enumerate(out):
        if w is None:
            prev_end = next((out[j]["end"] for j in range(i - 1, -1, -1) if out[j]), 0.0)
            nxt = next((out[j]["start"] for j in range(i + 1, len(out)) if out[j]), dur)
            run = [k for k in range(i, len(out)) if out[k] is None]
            run = run[: next((n for n, k in enumerate(run) if k != i + n), len(run))]
            span = max(nxt - prev_end, 0.05 * len(run))
            for n, k in enumerate(run):
                out[k] = {
                    "text": script_words[k],
                    "start": prev_end + span * n / len(run),
                    "end": prev_end + span * (n + 1) / len(run),
                }
    # monotonic + clamp
    last = 0.0
    for w in out:
        w["start"] = float(np.clip(max(w["start"], last), 0, dur))
        w["end"] = float(np.clip(max(w["end"], w["start"] + 0.04), 0, dur))
        last = w["start"]
    return out, f"{_BACKEND} (aligned to script)"
