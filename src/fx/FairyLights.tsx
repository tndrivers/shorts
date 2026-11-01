import React, { useMemo } from "react";
import { AbsoluteFill, random, useCurrentFrame, useVideoConfig } from "remotion";
import { noise2D } from "@remotion/noise";
import { FxSpec } from "../types";

/**
 * Flickering fairy lights.
 *  A new strand:  { from:[x,y], to:[x,y], sag:0.05, count:18, wire:true }
 *  Glow on bulbs already in the still: { points:[[x,y], ...], wire:false }
 */
export const FairyLights: React.FC<{ spec: FxSpec; seed: string }> = ({ spec, seed }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const colors = (spec.colors as string[]) ?? ["#ffd27a", "#ffb35c", "#fff1c1", "#ff8f6b"];
  const size = ((spec.size as number) ?? 1) * 7;
  const { bulbs, wire } = useMemo(() => {
    if (spec.points) {
      return { bulbs: (spec.points as number[][]).map(([x, y]) => [x * width, y * height]), wire: null };
    }
    const [x0, y0] = (spec.from as number[]) ?? [0.05, 0.1];
    const [x1, y1] = (spec.to as number[]) ?? [0.95, 0.1];
    const sag = ((spec.sag as number) ?? 0.05) * height;
    const n = (spec.count as number) ?? 16;
    const at = (u: number) => [
      (x0 + (x1 - x0) * u) * width,
      (y0 + (y1 - y0) * u) * height + sag * 4 * u * (1 - u),
    ];
    const pts = new Array(n).fill(0).map((_, i) => at((i + 0.5) / n));
    const path = new Array(41).fill(0).map((_, i) => at(i / 40));
    return { bulbs: pts, wire: "M " + path.map((p) => p.join(" ")).join(" L ") };
  }, [spec, width, height]);
  const t = frame / fps;
  return (
    <AbsoluteFill>
      <svg width={width} height={height} style={{ position: "absolute" }}>
        {wire && spec.wire !== false && <path d={wire} stroke="#1b1712" strokeWidth={2.2} fill="none" opacity={0.85} />}
      </svg>
      <AbsoluteFill style={{ mixBlendMode: "screen" }}>
        <svg width={width} height={height} style={{ position: "absolute" }}>
          <defs>
            {colors.map((c, i) => (
              <radialGradient key={i} id={`fl-${seed}-${i}`}>
                <stop offset="0%" stopColor="#fffdf5" />
                <stop offset="12%" stopColor={c} stopOpacity={0.95} />
                <stop offset="40%" stopColor={c} stopOpacity={0.3} />
                <stop offset="100%" stopColor={c} stopOpacity={0} />
              </radialGradient>
            ))}
          </defs>
          {bulbs.map(([x, y], i) => {
            const ci = Math.floor(random(`${seed}-c${i}`) * colors.length);
            // slow breathing plus a little candle-like flutter, smooth noise (no per-frame randomness)
            const f = 0.72 + 0.2 * noise2D(`${seed}-n`, i * 3.1, t * 0.9) + 0.08 * noise2D(`${seed}-m`, i * 7.7, t * 6);
            return <circle key={i} cx={x} cy={y} r={size * 5 * (0.85 + 0.3 * f)} fill={`url(#fl-${seed}-${ci})`} opacity={f} />;
          })}
        </svg>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
