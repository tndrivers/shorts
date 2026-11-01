import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { blinkAmount, blinkFrames, expressionAt, sampleEnv } from "./anim";
import { FaceRig } from "./Face";
import { FxLayer } from "./fx/FxLayer";
import { FxSpec, Line, Shot as ShotT, Timeline } from "./types";

/**
 * One shot: clean plate -> living-background fx -> breathing character cutouts with face rigs -> front fx,
 * all inside a camera that slowly pushes in toward whoever is talking.
 * `from`/`to` are absolute frames; useCurrentFrame() is absolute because Short renders shots without <Sequence>.
 */
export const Shot: React.FC<{
  shot: ShotT;
  timeline: Timeline;
  from: number;
  to: number;
  emphasis: boolean;
  speaker: string | null;
  fx: FxSpec[];
  debug?: boolean;
  mouthOverride?: (frame: number) => number;
}> = ({ shot, timeline, from, to, emphasis, speaker, fx, debug, mouthOverride }) => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const cam = timeline.camera;
  const local = frame - from;
  const dur = Math.max(1, to - from);

  // ---- camera push-in (continuous, never snapped) --------------------------------------
  const amount = emphasis ? cam.emphasisPushIn : cam.pushIn;
  const p = interpolate(local, [0, dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: emphasis ? Easing.bezier(0.45, 0, 0.35, 1) : Easing.bezier(0.25, 0.1, 0.4, 1),
  });
  const scale = 1 + amount * p;
  const focusFace = shot.faces.find((f) => f.character && f.character === speaker) ?? shot.faces[0];
  const ox = focusFace ? (focusFace.box[0] + focusFace.box[2]) / 2 : width / 2;
  const oy = focusFace ? (focusFace.box[1] + focusFace.box[3]) / 2 : height * 0.4;

  const back = fx.filter((f) => (f.layer ?? (f.type === "grass" ? "front" : "back")) === "back");
  const front = fx.filter((f) => (f.layer ?? (f.type === "grass" ? "front" : "back")) === "front");
  const t = frame / fps;

  return (
    <AbsoluteFill style={{ overflow: "hidden", backgroundColor: "#000" }}>
      <AbsoluteFill style={{ transform: `scale(${scale})`, transformOrigin: `${ox}px ${oy}px` }}>
        <Img src={staticFile(shot.plate)} style={{ position: "absolute", left: 0, top: 0, width, height }} />
        <FxLayer specs={back} shotId={shot.id} />
        {shot.pieces.map((piece, i) => {
          // gentle breathing: stretch up from the feet, each character on its own rhythm
          const phase = i * 2.1 + shot.id.charCodeAt(1);
          const s = Math.sin((2 * Math.PI * t) / cam.breathSeconds + phase);
          const sy = 1 + cam.breath * s;
          const sx = 1 - cam.breath * 0.35 * s;
          return (
            <AbsoluteFill
              key={i}
              style={{
                transform: `scale(${sx}, ${sy})`,
                transformOrigin: `${piece.x + piece.w / 2}px ${piece.y + piece.h}px`,
              }}
            >
              <Img
                src={staticFile(piece.src)}
                style={{ position: "absolute", left: piece.x, top: piece.y, width: piece.w, height: piece.h }}
              />
              {shot.faces
                .map((face, n) => ({ face, n }))
                .filter(({ face }) => face.piece === i)
                .map(({ face, n }) => {
                  const who = face.character ?? `${shot.id}-face${n}`;
                  const expr = expressionAt(frame, timeline.lines, face.character, fps);
                  const blink = blinkAmount(frame, blinkFrames(who, fps, durationInFrames), fps);
                  const open = mouthOverride
                    ? mouthOverride(frame)
                    : face.character
                      ? sampleEnv(timeline.envelopes[face.character], frame)
                      : 0;
                  return (
                    <FaceRig
                      key={n}
                      id={`${shot.id}-${n}`}
                      face={face}
                      open={open}
                      maxOpen={timeline.mouth.maxOpen}
                      mouthColor={timeline.mouth.color}
                      upper={expr.upper + (1 - expr.upper) * blink}
                      lower={expr.lower * (1 - blink * 0.4) + blink * 0.12}
                      debug={debug}
                    />
                  );
                })}
            </AbsoluteFill>
          );
        })}
        <FxLayer specs={front} shotId={shot.id} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const speakerAt = (lines: Line[], frame: number): Line => {
  let cur = lines[0];
  for (const l of lines) if (l.startFrame - 4 <= frame) cur = l;
  return cur;
};
