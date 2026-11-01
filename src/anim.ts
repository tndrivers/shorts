import { random } from "remotion";
import { Expression, Line } from "./types";

/** Eyelid closure per expression: upper lid down, lower lid up (0 = open, 1 = shut). */
export const EXPRESSIONS: Record<Expression, { upper: number; lower: number }> = {
  neutral: { upper: 0, lower: 0 },
  smug: { upper: 0.4, lower: 0.12 },
  soft: { upper: 0.22, lower: 0.06 },
  happy: { upper: 0.14, lower: 0.42 },
};

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

/** Natural blinks: random 2.2-5.2s gaps, sometimes a double blink. Fully deterministic per seed. */
const blinkCache = new Map<string, number[]>();
export function blinkFrames(seed: string, fps: number, total: number): number[] {
  const key = `${seed}-${fps}-${total}`;
  const hit = blinkCache.get(key);
  if (hit) return hit;
  const out: number[] = [];
  let t = fps * (0.6 + random(`${seed}-first`) * 1.6);
  let k = 0;
  while (t < total + fps) {
    out.push(t);
    if (random(`${seed}-double-${k}`) < 0.18) out.push(t + fps * 0.32);
    t += fps * (2.2 + random(`${seed}-gap-${k}`) * 3.0);
    k++;
  }
  blinkCache.set(key, out);
  return out;
}

// close fast, open slower (frames at 30fps)
const PROFILE = [0.3, 0.75, 1, 1, 0.78, 0.5, 0.25, 0.08];
export function blinkAmount(frame: number, frames: number[], fps: number): number {
  const scale = fps / 30;
  let v = 0;
  for (const b of frames) {
    const d = (frame - b) / scale;
    if (d < 0 || d >= PROFILE.length) continue;
    // linear interpolation between profile samples keeps it smooth at any fps
    const i = Math.floor(d);
    const f = d - i;
    const a = PROFILE[i];
    const c = PROFILE[i + 1] ?? 0;
    v = Math.max(v, a + (c - a) * f);
  }
  return v;
}

/** Expression for a character at a frame, blended across line changes. */
export function expressionAt(frame: number, lines: Line[], character: string | null, fps: number) {
  const lead = fps * 0.2;
  let i = 0;
  for (let n = 0; n < lines.length; n++) if (lines[n].startFrame - lead <= frame) i = n;
  const exprFor = (l: Line): Expression =>
    character && l.speaker === character ? l.expression : (l.react ?? "neutral");
  const cur = EXPRESSIONS[exprFor(lines[i])] ?? EXPRESSIONS.neutral;
  const prev = i > 0 ? (EXPRESSIONS[exprFor(lines[i - 1])] ?? EXPRESSIONS.neutral) : cur;
  const t = clamp01((frame - (lines[i].startFrame - lead)) / (fps * 0.35));
  const e = t * t * (3 - 2 * t);
  return { upper: prev.upper + (cur.upper - prev.upper) * e, lower: prev.lower + (cur.lower - prev.lower) * e };
}

/** Sample a per-frame envelope with linear interpolation (frame may be fractional). */
export function sampleEnv(env: number[] | undefined, frame: number): number {
  if (!env || env.length === 0) return 0;
  const i = Math.floor(frame);
  if (i < 0 || i >= env.length) return 0;
  const f = frame - i;
  return env[i] + ((env[i + 1] ?? env[i]) - env[i]) * f;
}
