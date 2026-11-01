import React from "react";
import { Img, staticFile } from "remotion";
import { Eye, Face as FaceT } from "./types";

/**
 * Mouth + eyelids for one face, drawn in stage coordinates on top of the character cutout.
 * Lip sync: the jaw (lower lip to chin, cut from the still) drops with the voice loudness and a
 * dark mouth interior shows in the gap. Lids are vector shapes coloured from the skin above the eye.
 */
export const FaceRig: React.FC<{
  face: FaceT;
  id: string;
  open: number; // 0..1
  maxOpen: number;
  mouthColor: string;
  upper: number; // 0..1 lid closure
  lower: number;
  debug?: boolean;
}> = ({ face, id, open, maxOpen, mouthColor, upper, lower, debug }) => {
  const m = face.mouth;
  const drop = open * m.w * maxOpen;
  const top = Math.min(m.upperY, m.lowerY);
  const bottom = m.lowerY + drop;
  const ry = Math.max(0, (bottom - top) / 2);
  const rx = m.innerW * 0.5 * (0.62 + 0.3 * open);
  const cy = top + ry;
  const showMouth = drop > 0.25;

  return (
    <>
      {showMouth && (
        <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }} width={1} height={1}>
          <defs>
            <radialGradient id={`mg-${id}`} cx="50%" cy="40%" r="60%">
              <stop offset="0%" stopColor={mouthColor} />
              <stop offset="100%" stopColor="#0d0405" />
            </radialGradient>
            <clipPath id={`mc-${id}`}>
              <ellipse cx={m.x} cy={cy} rx={rx} ry={ry} />
            </clipPath>
          </defs>
          <ellipse cx={m.x} cy={cy} rx={rx} ry={ry} fill={`url(#mg-${id})`} />
          <g clipPath={`url(#mc-${id})`}>
            {/* upper teeth hint and tongue */}
            <rect x={m.x - rx} y={top - 1} width={rx * 2} height={Math.min(ry * 0.45, m.w * 0.07) + 1} fill="#ece6dc" opacity={0.85} />
            <ellipse cx={m.x} cy={bottom + ry * 0.15} rx={rx * 0.62} ry={ry * 0.55} fill="#a3454b" opacity={0.75} />
          </g>
        </svg>
      )}
      {face.jaw && (
        <Img
          src={staticFile(face.jaw.src)}
          style={{
            position: "absolute",
            left: face.jaw.x,
            top: face.jaw.y,
            width: face.jaw.w,
            height: face.jaw.h,
            transform: `translateY(${drop}px)`,
          }}
        />
      )}
      {face.eyes.map((e, i) => (
        <Lids key={i} eye={e} id={`${id}-e${i}`} upper={upper} lower={lower} />
      ))}
      {debug && <RigDebug face={face} />}
    </>
  );
};

const Lids: React.FC<{ eye: Eye; id: string; upper: number; lower: number }> = ({ eye, id, upper, lower }) => {
  if (upper < 0.01 && lower < 0.01) return null;
  const xs = eye.points.map((p) => p[0]);
  const ys = eye.points.map((p) => p[1]);
  const x0 = Math.min(...xs) - 2;
  const x1 = Math.max(...xs) + 2;
  const y0 = Math.min(...ys);
  const y1 = Math.max(...ys);
  const h = y1 - y0;
  const cx = (x0 + x1) / 2;
  const poly = eye.points.map((p) => p.join(",")).join(" ");

  // upper lid edge: corners at yU, centre bulges down (a real lid is an arc)
  const yU = y0 - 1 + upper * (h + 2);
  const bulgeU = h * 0.28 * Math.min(1, upper * 1.5);
  const upperPath = `M ${x0} ${y0 - h} L ${x1} ${y0 - h} L ${x1} ${yU} Q ${cx} ${yU + bulgeU * 2} ${x0} ${yU} Z`;
  const upperEdge = `M ${x1} ${yU} Q ${cx} ${yU + bulgeU * 2} ${x0} ${yU}`;
  // lower lid edge: rises from the bottom, centre bulges up
  const yL = y1 + 1 - lower * h * 0.8;
  const bulgeL = h * 0.2 * lower;
  const lowerPath = `M ${x0} ${y1 + h} L ${x1} ${y1 + h} L ${x1} ${yL} Q ${cx} ${yL - bulgeL * 2} ${x0} ${yL} Z`;
  const lash = Math.max(1.2, h * 0.11);

  return (
    <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }} width={1} height={1}>
      <defs>
        <clipPath id={`ec-${id}`}>
          <polygon points={poly} />
        </clipPath>
        <linearGradient id={`lg-${id}`} gradientUnits="userSpaceOnUse" x1={0} y1={y0 - h * 0.3} x2={0} y2={yU + bulgeU}>
          <stop offset="0%" stopColor={eye.lid} />
          <stop offset="100%" stopColor={eye.lid} stopOpacity={1} />
        </linearGradient>
      </defs>
      <g clipPath={`url(#ec-${id})`}>
        {upper > 0.01 && (
          <>
            <path d={upperPath} fill={`url(#lg-${id})`} />
            <path d={upperEdge} fill="none" stroke={eye.lash} strokeWidth={lash} strokeLinecap="round" opacity={Math.min(1, upper * 4)} />
          </>
        )}
        {lower > 0.01 && (
          <>
            <path d={lowerPath} fill={eye.lid} />
            <path
              d={`M ${x1} ${yL} Q ${cx} ${yL - bulgeL * 2} ${x0} ${yL}`}
              fill="none"
              stroke={eye.lash}
              strokeWidth={lash * 0.5}
              opacity={Math.min(0.6, lower * 2)}
            />
          </>
        )}
      </g>
    </svg>
  );
};

const RigDebug: React.FC<{ face: FaceT }> = ({ face }) => {
  const [bx0, by0, bx1, by1] = face.box;
  return (
    <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }} width={1} height={1}>
      <rect x={bx0} y={by0} width={bx1 - bx0} height={by1 - by0} fill="none" stroke="#00ff66" strokeWidth={3} />
      <text x={bx0} y={by0 - 10} fill="#00ff66" fontSize={34} fontFamily="sans-serif">
        {face.character ?? "?"}
      </text>
      <circle cx={face.mouth.x} cy={face.mouth.y} r={5} fill="#ff2a6d" />
      {face.eyes.map((e, i) => (
        <polygon key={i} points={e.points.map((p) => p.join(",")).join(" ")} fill="none" stroke="#ffd400" strokeWidth={2} />
      ))}
      {face.jaw && (
        <rect x={face.jaw.x} y={face.jaw.y} width={face.jaw.w} height={face.jaw.h} fill="none" stroke="#ff00ff" strokeDasharray="8 6" strokeWidth={2} />
      )}
    </svg>
  );
};
