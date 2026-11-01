import React, { useMemo } from "react";
import { AbsoluteFill, random, useCurrentFrame, useVideoConfig } from "remotion";
import { FxSpec } from "../types";

/** Twinkling stars in a region. { region:[x,y,w,h], count, color, size } */
export const Stars: React.FC<{ spec: FxSpec; seed: string }> = ({ spec, seed }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const [rx, ry, rw, rh] = (spec.region as number[]) ?? [0, 0, 1, 0.4];
  const count = (spec.count as number) ?? 60;
  const color = (spec.color as string) ?? "#fff8e7";
  const sizeMul = (spec.size as number) ?? 1;
  const stars = useMemo(
    () =>
      new Array(count).fill(0).map((_, i) => ({
        x: (rx + random(`${seed}-x${i}`) * rw) * width,
        y: (ry + random(`${seed}-y${i}`) * rh) * height,
        r: (1.2 + Math.pow(random(`${seed}-r${i}`), 3) * 3.2) * sizeMul,
        speed: 0.25 + random(`${seed}-s${i}`) * 0.9,
        phase: random(`${seed}-p${i}`) * Math.PI * 2,
        base: 0.35 + random(`${seed}-b${i}`) * 0.4,
        sparkle: random(`${seed}-k${i}`) < 0.08,
      })),
    [count, rx, ry, rw, rh, width, height, seed, sizeMul],
  );
  const t = frame / fps;
  return (
    <AbsoluteFill style={{ mixBlendMode: "screen" }}>
      <svg width={width} height={height} style={{ position: "absolute" }}>
        <defs>
          <radialGradient id={`star-${seed}`}>
            <stop offset="0%" stopColor={color} stopOpacity={1} />
            <stop offset="35%" stopColor={color} stopOpacity={0.55} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </radialGradient>
        </defs>
        {stars.map((s, i) => {
          const tw = 0.5 + 0.5 * Math.sin(2 * Math.PI * s.speed * t + s.phase);
          const o = s.base + (1 - s.base) * tw * tw;
          return (
            <g key={i} opacity={o}>
              <circle cx={s.x} cy={s.y} r={s.r * 2.6} fill={`url(#star-${seed})`} />
              {s.sparkle && (
                <path
                  d={`M ${s.x - s.r * 6 * tw} ${s.y} L ${s.x + s.r * 6 * tw} ${s.y} M ${s.x} ${s.y - s.r * 6 * tw} L ${s.x} ${s.y + s.r * 6 * tw}`}
                  stroke={color}
                  strokeWidth={0.9}
                  strokeLinecap="round"
                  opacity={0.7}
                />
              )}
            </g>
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};
