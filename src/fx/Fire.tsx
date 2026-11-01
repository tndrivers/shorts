import React, { useMemo } from "react";
import { AbsoluteFill, random, useCurrentFrame, useVideoConfig } from "remotion";
import { noise2D } from "@remotion/noise";
import { FxSpec } from "../types";

/**
 * Campfire / fireplace: licking flame tongues, rising embers, and a warm glow that flickers on the scene.
 * { x, y (base centre, 0..1), width, height (0..1 of frame), light (0..0.4 scene glow), embers }
 */
export const Fire: React.FC<{ spec: FxSpec; seed: string }> = ({ spec, seed }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const t = frame / fps;
  const bx = ((spec.x as number) ?? 0.5) * width;
  const by = ((spec.y as number) ?? 0.9) * height;
  const fw = ((spec.width as number) ?? 0.25) * width;
  const fh = ((spec.height as number) ?? 0.2) * height;
  const light = (spec.light as number) ?? 0.12;
  const nEmbers = (spec.embers as number) ?? 22;

  const flicker = 0.75 + 0.18 * noise2D(`${seed}-f`, t * 2.2, 0) + 0.07 * noise2D(`${seed}-f2`, t * 9, 1);

  const tongue = (k: number, layer: number) => {
    const spread = fw * (0.5 - layer * 0.12);
    const off = ((k + 0.5) / 5 - 0.5) * spread;
    const hh = fh * (0.55 + 0.45 * random(`${seed}-h${layer}-${k}`)) * (1 - layer * 0.22);
    const n1 = noise2D(`${seed}-a${layer}`, k * 1.7, t * 2.4);
    const n2 = noise2D(`${seed}-b${layer}`, k * 2.3, t * 3.1 + 5);
    const h = hh * (0.85 + 0.25 * n2) * flicker;
    const w = fw * (0.22 - layer * 0.03);
    const x = bx + off;
    const tipX = x + n1 * w * 0.9;
    const tipY = by - h;
    return `M ${x - w / 2} ${by} C ${x - w * 0.6} ${by - h * 0.45}, ${tipX - w * 0.15} ${by - h * 0.7}, ${tipX} ${tipY}
            C ${tipX + w * 0.15} ${by - h * 0.7}, ${x + w * 0.6} ${by - h * 0.45}, ${x + w / 2} ${by} Z`;
  };

  const embers = useMemo(
    () =>
      new Array(nEmbers).fill(0).map((_, i) => ({
        period: 1.6 + random(`${seed}-ep${i}`) * 1.8,
        offset: random(`${seed}-eo${i}`) * 4,
        x: (random(`${seed}-ex${i}`) - 0.5) * fw * 0.6,
        drift: (random(`${seed}-ed${i}`) - 0.5) * fw * 0.8,
        r: 1.4 + random(`${seed}-er${i}`) * 2.4,
      })),
    [nEmbers, fw, seed],
  );
  const layers = [
    { fill: `url(#fo-${seed})`, opacity: 0.9 },
    { fill: `url(#fm-${seed})`, opacity: 0.95 },
    { fill: `url(#fi-${seed})`, opacity: 1 },
  ];

  return (
    <AbsoluteFill>
      {/* warm light spilling onto the scene */}
      <AbsoluteFill
        style={{
          mixBlendMode: "soft-light",
          opacity: Math.min(1, light * 5 * flicker),
          background: `radial-gradient(circle at ${(bx / width) * 100}% ${(by / height) * 100}%, #ffb347 0%, rgba(255,140,40,0.5) 25%, transparent 65%)`,
        }}
      />
      <AbsoluteFill style={{ mixBlendMode: "screen" }}>
        <svg width={width} height={height} style={{ position: "absolute" }}>
          <defs>
            <linearGradient id={`fo-${seed}`} x1="0" y1="1" x2="0" y2="0">
              <stop offset="0%" stopColor="#ff4b1f" />
              <stop offset="100%" stopColor="#ff2a00" stopOpacity={0} />
            </linearGradient>
            <linearGradient id={`fm-${seed}`} x1="0" y1="1" x2="0" y2="0">
              <stop offset="0%" stopColor="#ffa31a" />
              <stop offset="100%" stopColor="#ff6a00" stopOpacity={0} />
            </linearGradient>
            <linearGradient id={`fi-${seed}`} x1="0" y1="1" x2="0" y2="0">
              <stop offset="0%" stopColor="#fff6c8" />
              <stop offset="100%" stopColor="#ffd34d" stopOpacity={0} />
            </linearGradient>
            <radialGradient id={`fg-${seed}`}>
              <stop offset="0%" stopColor="#ff9a3c" stopOpacity={0.55} />
              <stop offset="100%" stopColor="#ff9a3c" stopOpacity={0} />
            </radialGradient>
            <filter id={`fb-${seed}`} x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation={Math.max(1.5, fw * 0.012)} />
            </filter>
          </defs>
          <ellipse cx={bx} cy={by - fh * 0.3} rx={fw * 1.1} ry={fh * 0.9} fill={`url(#fg-${seed})`} opacity={flicker} />
          <g filter={`url(#fb-${seed})`}>
            {layers.map((l, layer) => (
              <g key={layer} opacity={l.opacity}>
                {[0, 1, 2, 3, 4].map((k) => (
                  <path key={k} d={tongue(k, layer)} fill={l.fill} />
                ))}
              </g>
            ))}
          </g>
          {embers.map((e, i) => {
            const life = ((t + e.offset) % e.period) / e.period;
            const ex = bx + e.x + e.drift * life + Math.sin((t + i) * 3) * 6;
            const ey = by - fh * 0.3 - life * fh * 1.8;
            return <circle key={i} cx={ex} cy={ey} r={e.r * (1 - life * 0.6)} fill="#ffcf6b" opacity={(1 - life) * 0.9} />;
          })}
        </svg>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
