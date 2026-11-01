import React, { useMemo } from "react";
import { AbsoluteFill, random, useCurrentFrame, useVideoConfig } from "remotion";
import { noise2D } from "@remotion/noise";
import { FxSpec } from "../types";

/** Grass blades swaying in a gust-y wind. { region:[x,y,w,h], color, count, wind } (region bottom = ground line) */
export const Grass: React.FC<{ spec: FxSpec; seed: string }> = ({ spec, seed }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const [rx, ry, rw, rh] = (spec.region as number[]) ?? [0, 0.88, 1, 0.12];
  const count = (spec.count as number) ?? 140;
  const color = (spec.color as string) ?? "#3f6b2a";
  const wind = (spec.wind as number) ?? 1;
  const blades = useMemo(
    () =>
      new Array(count).fill(0).map((_, i) => {
        const r = (k: string) => random(`${seed}-${k}${i}`);
        return {
          x: (rx + r("x") * rw) * width,
          base: (ry + rh) * height + 6 + r("b") * 8,
          h: rh * height * (0.45 + r("h") * 0.75),
          w: 5 + r("w") * 7,
          lean: (r("l") - 0.5) * 0.5,
          shade: 0.65 + r("s") * 0.5,
        };
      }),
    [count, rx, ry, rw, rh, width, height, seed],
  );
  const t = frame / fps;
  return (
    <AbsoluteFill>
      <svg width={width} height={height} style={{ position: "absolute" }}>
        {blades.map((b, i) => {
          // wind field travels across the screen: neighbours sway together, gusts roll through
          const gust = noise2D(`${seed}-g`, b.x / 600 - t * 0.35, 0) * 0.5 + 0.5;
          const sway = (b.lean + Math.sin(t * 2.1 + b.x / 140) * 0.12 * wind + gust * 0.35 * wind) * b.h;
          const tipX = b.x + sway;
          const tipY = b.base - b.h + Math.abs(sway) * 0.25;
          const midX = b.x + sway * 0.35;
          const midY = b.base - b.h * 0.55;
          const d = `M ${b.x - b.w / 2} ${b.base} Q ${midX - b.w * 0.3} ${midY} ${tipX} ${tipY} Q ${midX + b.w * 0.3} ${midY} ${b.x + b.w / 2} ${b.base} Z`;
          return <path key={i} d={d} fill={shade(color, b.shade)} />;
        })}
      </svg>
    </AbsoluteFill>
  );
};

const shade = (hex: string, k: number) => {
  const n = parseInt(hex.replace("#", ""), 16);
  const c = (v: number) => Math.round(Math.min(255, v * k));
  return `rgb(${c((n >> 16) & 255)},${c((n >> 8) & 255)},${c(n & 255)})`;
};
