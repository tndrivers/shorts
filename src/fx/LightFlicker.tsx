import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { noise2D } from "@remotion/noise";
import { FxSpec } from "../types";

/** Smooth warm light breathing over the whole shot. { color, strength, x, y } */
export const LightFlicker: React.FC<{ spec: FxSpec; seed: string }> = ({ spec, seed }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const strength = (spec.strength as number) ?? 0.12;
  const color = (spec.color as string) ?? "#ff9a3c";
  const x = ((spec.x as number) ?? 0.5) * 100;
  const y = ((spec.y as number) ?? 0.8) * 100;
  const f = 0.6 + 0.25 * noise2D(seed, t * 1.7, 0) + 0.15 * noise2D(seed, t * 5.3, 3);
  return (
    <AbsoluteFill
      style={{
        mixBlendMode: "soft-light",
        opacity: strength * 4 * f,
        background: `radial-gradient(ellipse at ${x}% ${y}%, ${color} 0%, transparent 70%)`,
      }}
    />
  );
};
