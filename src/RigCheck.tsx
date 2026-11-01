import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Shot } from "./Shot";
import { ShortProps } from "./types";

export const RIG_FRAMES_PER_SHOT = 75;

/** Each shot for 2.5s with the rig outlines drawn and every mouth flapping, to check placement. */
export const RigCheck: React.FC<ShortProps> = ({ timeline }) => {
  const frame = useCurrentFrame();
  if (!timeline) return null;
  const ids = Object.keys(timeline.shots).sort();
  const i = Math.min(ids.length - 1, Math.floor(frame / RIG_FRAMES_PER_SHOT));
  const shot = timeline.shots[ids[i]];
  const from = i * RIG_FRAMES_PER_SHOT;
  return (
    <AbsoluteFill>
      <Shot
        key={shot.id}
        shot={shot}
        timeline={timeline}
        from={from}
        to={from + RIG_FRAMES_PER_SHOT}
        emphasis={false}
        speaker={null}
        fx={timeline.fx[shot.id] ?? []}
        debug
        mouthOverride={(f) => Math.max(0, Math.sin(f / 3))}
      />
      <div style={{ position: "absolute", left: 30, top: 30, color: "#0f6", fontSize: 60, fontFamily: "sans-serif" }}>
        {shot.id}
      </div>
    </AbsoluteFill>
  );
};
