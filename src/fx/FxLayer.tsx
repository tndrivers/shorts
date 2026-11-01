import React from "react";
import { AbsoluteFill } from "remotion";
import { FxSpec } from "../types";
import { FairyLights } from "./FairyLights";
import { Fire } from "./Fire";
import { Grass } from "./Grass";
import { LightFlicker } from "./LightFlicker";
import { Stars } from "./Stars";

/** Living-background effects, configured per shot in config.json -> "fx". Coordinates are 0..1 of the frame. */
export const FxLayer: React.FC<{ specs: FxSpec[]; shotId: string }> = ({ specs, shotId }) => (
  <AbsoluteFill style={{ pointerEvents: "none" }}>
    {specs.map((s, i) => {
      const seed = `${shotId}-${i}-${s.seed ?? 0}`;
      switch (s.type) {
        case "stars":
          return <Stars key={i} spec={s} seed={seed} />;
        case "fire":
          return <Fire key={i} spec={s} seed={seed} />;
        case "grass":
          return <Grass key={i} spec={s} seed={seed} />;
        case "fairyLights":
          return <FairyLights key={i} spec={s} seed={seed} />;
        case "lightFlicker":
          return <LightFlicker key={i} spec={s} seed={seed} />;
        default:
          return null;
      }
    })}
  </AbsoluteFill>
);
