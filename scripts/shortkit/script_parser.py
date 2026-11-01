"""Parse script.md into a list of lines: index, speaker, shot, text, expression, emphasis.

Supported formats (mix and match, one line of dialogue per row):

1. Markdown table, columns recognised by header name (order does not matter):
   | # | Speaker | Shot | Expression | Emphasis | Line |
   |---|---------|------|------------|----------|------|
   | 01 | me | S2 | smug | | Guess what I found. |

2. Free text, one line per dialogue line:
   01 [S2] me (smug): Guess what I found.
   02 - S3 - sidekick: What?
   07 [S5] sidekick (soft) !emphasis: "I'd love that."

The audio filename (01_me.mp3) is the source of truth for the speaker and the order.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

EXPRESSIONS = ("neutral", "smug", "soft", "happy", "squint", "sincere", "sad", "excited")
EXPRESSION_ALIASES = {"squint": "happy", "sincere": "soft", "excited": "happy", "sad": "soft"}
TRUTHY = {"y", "yes", "x", "true", "1", "strong", "emphasis", "emotional", "✓", "✔", "*", "!"}


@dataclass
class ScriptLine:
    index: int
    text: str = ""
    shot: str | None = None
    speaker: str | None = None
    expression: str = "neutral"
    emphasis: bool = False
    react: str | None = None  # expression for the listener, if any
    extra: dict = field(default_factory=dict)


def _norm_expr(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    for e in EXPRESSIONS:
        if e in v:
            return EXPRESSION_ALIASES.get(e, e)
    return None


def _split_row(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [c.strip() for c in row.split("|")]


def _header_key(name: str) -> str | None:
    n = name.strip().lower()
    if n in ("#", "no", "no.", "n", "id", "idx", "index", "line #", "line no", "num", "number"):
        return "index"
    if any(k in n for k in ("speaker", "who", "character", "voice")):
        return "speaker"
    if "react" in n or "listener" in n:
        return "react"
    if "shot" in n or "still" in n or "camera" in n:
        return "shot"
    if any(k in n for k in ("expression", "mood", "emotion", "face")):
        return "expression"
    if any(k in n for k in ("emphasis", "push", "emotional", "strong")):
        return "emphasis"
    if any(k in n for k in ("line", "text", "dialog", "script", "says", "words")):
        return "text"
    return None


def _clean_text(t: str) -> str:
    t = t.strip().strip("*_").strip()
    if len(t) >= 2 and t[0] in "\"“'‘" and t[-1] in "\"”'’":
        t = t[1:-1]
    return t.strip()


def parse_script(md: str, speakers: list[str]) -> list[ScriptLine]:
    lines: list[ScriptLine] = []
    rows = md.splitlines()
    i = 0
    seq = 0
    while i < len(rows):
        row = rows[i]
        # ---- table -------------------------------------------------------
        if row.strip().startswith("|") and i + 1 < len(rows) and re.match(r"^\s*\|?\s*:?-{2,}", rows[i + 1]):
            header = [_header_key(h) for h in _split_row(row)]
            i += 2
            while i < len(rows) and rows[i].strip().startswith("|"):
                cells = _split_row(rows[i])
                rec: dict = {}
                for key, cell in zip(header, cells):
                    if key:
                        rec[key] = cell
                i += 1
                text = _clean_text(rec.get("text", ""))
                if not text and not rec.get("shot"):
                    continue
                seq += 1
                m = re.search(r"\d+", rec.get("index", ""))
                shot = re.search(r"S\d+", rec.get("shot", ""), re.I)
                lines.append(
                    ScriptLine(
                        index=int(m.group()) if m else seq,
                        text=text,
                        shot=shot.group().upper() if shot else None,
                        speaker=(rec.get("speaker") or "").strip().lower() or None,
                        expression=_norm_expr(rec.get("expression")) or "neutral",
                        emphasis=(rec.get("emphasis", "").strip().lower() in TRUTHY),
                        react=_norm_expr(rec.get("react")),
                    )
                )
            continue
        # ---- free text ---------------------------------------------------
        i += 1
        raw = row.strip()
        if not raw or raw.startswith("#"):
            continue
        shot = re.search(r"\bS(\d+)\b", raw)
        num = re.match(r"^[-*>\s]*\**\s*(\d{1,3})\b", raw)
        if not shot and not num:
            continue
        if not shot:
            # a numbered line with no shot is still a line only if it has dialogue
            if ":" not in raw:
                continue
        # text = after first ':' that is not inside the metadata, else quoted part
        text = ""
        q = re.search(r"[\"“](.+)[\"”]", raw)
        if ":" in raw:
            text = raw.split(":", 1)[1]
        elif q:
            text = q.group(1)
        meta = raw.split(":", 1)[0] if ":" in raw else raw
        speaker = None
        for sp in speakers:
            if re.search(rf"\b{re.escape(sp)}\b", meta, re.I):
                speaker = sp
                break
        expr = None
        for m in re.finditer(r"[\(\[]([^\)\]]+)[\)\]]", meta):
            expr = expr or _norm_expr(m.group(1))
        react = None
        rm = re.search(r"react(?:s|ion)?\s*[:=]?\s*(\w+)", meta, re.I)
        if rm:
            react = _norm_expr(rm.group(1))
        emphasis = bool(re.search(r"!emphasis|!push|\bemotional\b|⭐|★|\[!\]", raw, re.I))
        seq += 1
        lines.append(
            ScriptLine(
                index=int(num.group(1)) if num else seq,
                text=_clean_text(text),
                shot=f"S{shot.group(1)}" if shot else None,
                speaker=speaker,
                expression=expr or "neutral",
                emphasis=emphasis,
                react=react,
            )
        )
    return lines
