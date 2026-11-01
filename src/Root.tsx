import React from "react";
import { CalculateMetadataFunction, Composition, staticFile } from "remotion";
import { Short } from "./Short";
import { RIG_FRAMES_PER_SHOT, RigCheck } from "./RigCheck";
import { ShortProps, Timeline } from "./types";

const loadTimeline: CalculateMetadataFunction<ShortProps> = async ({ props }) => {
  const res = await fetch(staticFile("generated/timeline.json"));
  if (!res.ok) {
    throw new Error("public/generated/timeline.json is missing. Run: python3 scripts/prepare.py --src <your folder>");
  }
  const timeline = (await res.json()) as Timeline;
  return {
    durationInFrames: timeline.durationInFrames,
    fps: timeline.fps,
    width: timeline.width,
    height: timeline.height,
    props: { ...props, timeline },
  };
};


const loadRig: CalculateMetadataFunction<ShortProps> = async (args) => {
  const meta = await loadTimeline(args);
  const t = (meta.props as ShortProps).timeline!;
  return { ...meta, durationInFrames: Object.keys(t.shots).length * RIG_FRAMES_PER_SHOT };
};

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="Short"
      component={Short}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={300}
      defaultProps={{ timeline: null } as ShortProps}
      calculateMetadata={loadTimeline}
    />
    {/* Same picture without captions/cards: what scripts/check_render.py analyses for jitter. */}
    <Composition
      id="ShortClean"
      component={Short}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={300}
      defaultProps={{ timeline: null, overlays: false } as ShortProps}
      calculateMetadata={loadTimeline}
    />
    {/* Every shot with the face rig drawn on top and the mouth flapping: check placement here first. */}
    <Composition
      id="RigCheck"
      component={RigCheck}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={300}
      defaultProps={{ timeline: null } as ShortProps}
      calculateMetadata={loadRig}
    />
  </>
);

