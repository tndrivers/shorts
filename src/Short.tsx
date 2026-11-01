import React from "react";
import { AbsoluteFill, Audio, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Captions } from "./Captions";
import { Shot, speakerAt } from "./Shot";
import { cardRegion, StepCards } from "./StepCards";
import { Segment, Shot as ShotT, ShortProps, Timeline } from "./types";

const CAPTION_HALF = 0.065;

/** Caption centre for this frame: the shot's face-free spot, moved if a step card is on screen. */
const faceSpans = (shot: ShotT, height: number): [number, number][] =>
  shot.faces.map((f) => [f.box[1] / height - 0.03, f.box[3] / height + 0.03]);

function captionYFor(shot: ShotT, timeline: Timeline, frame: number, height: number): number {
  const blocks = faceSpans(shot, height);
  for (const c of timeline.cards) {
    if (frame >= c.from - 2 && frame <= c.to + 20) blocks.push(cardRegion(c, faceSpans(shot, height)));
  }
  const clear = (y: number) => blocks.every(([a, b]) => y + CAPTION_HALF < a || y - CAPTION_HALF > b);
  const options = [shot.captionY, 0.7, 0.62, 0.78, 0.82, 0.24, 0.2, 0.16, 0.4, 0.5, 0.55];
  return options.find(clear) ?? shot.captionY;
}

export const Short: React.FC<ShortProps> = ({ timeline, overlays = true }) => {
  const frame = useCurrentFrame();
  const { height } = useVideoConfig();
  if (!timeline) return null;
  const seg: Segment =
    timeline.segments.find((s) => frame >= s.from && frame < s.to) ?? timeline.segments[timeline.segments.length - 1];
  const shot = timeline.shots[seg.shot];
  const firstLine = timeline.lines.find((l) => l.index === seg.lines[0]);
  const capY = captionYFor(shot, timeline, frame, height);

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      <Audio src={staticFile(timeline.audio)} />
      <Shot
        key={`${seg.shot}-${seg.from}`}
        shot={shot}
        timeline={timeline}
        from={seg.from}
        to={seg.to}
        emphasis={seg.emphasis}
        speaker={firstLine?.speaker ?? speakerAt(timeline.lines, frame).speaker}
        fx={timeline.fx[seg.shot] ?? []}
      />
      {overlays && <StepCards cards={timeline.cards} faces={faceSpans(shot, height)} />}
      {overlays && <Captions timeline={timeline} y={capY} />}
    </AbsoluteFill>
  );
};
