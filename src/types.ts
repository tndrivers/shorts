export type Expression = "neutral" | "smug" | "soft" | "happy";

export type Line = {
  index: number;
  speaker: string;
  shot: string;
  text: string;
  expression: Expression;
  react: Expression | null;
  emphasis: boolean;
  start: number;
  end: number;
  startFrame: number;
  endFrame: number;
};

export type Word = { text: string; start: number; end: number; line: number };

export type Segment = { shot: string; from: number; to: number; lines: number[]; emphasis: boolean };

export type Piece = { src: string; x: number; y: number; w: number; h: number };

export type Eye = { points: [number, number][]; lid: string; lash: string };

export type Face = {
  character: string | null;
  piece: number;
  mouth: { x: number; y: number; w: number; innerW: number; upperY: number; lowerY: number };
  jaw: { src: string; x: number; y: number; w: number; h: number } | null;
  eyes: Eye[];
  box: [number, number, number, number];
};

export type Shot = {
  id: string;
  full: string;
  plate: string;
  pieces: Piece[];
  faces: Face[];
  captionY: number;
};

export type FxSpec = {
  type: "stars" | "fire" | "grass" | "fairyLights" | "lightFlicker";
  layer?: "back" | "front";
  seed?: number;
  [key: string]: unknown;
};

export type Card = {
  title: string;
  from: number;
  to: number;
  position: "top" | "bottom" | "auto";
  accent: string;
  steps: { text: string; at: number; icon?: string | null }[];
};

export type Timeline = {
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  audio: string;
  lines: Line[];
  words: Word[];
  segments: Segment[];
  envelopes: Record<string, number[]>;
  shots: Record<string, Shot>;
  cards: Card[];
  fx: Record<string, FxSpec[]>;
  camera: { pushIn: number; emphasisPushIn: number; breath: number; breathSeconds: number };
  mouth: { maxOpen: number; color: string };
  captions: {
    font: string;
    weight: number;
    size: number;
    maxWords: number;
    color: string;
    highlight: string;
    stroke: string;
    uppercase: boolean;
  };
};

export type ShortProps = { timeline: Timeline | null; overlays?: boolean };
