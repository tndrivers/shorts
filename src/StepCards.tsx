import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { MONTSERRAT } from "./fonts";
import { Card } from "./types";

export const CARD_TOP_Y = 0.1;
export const CARD_BOTTOM_Y = 0.6;

/** Card region (0..1 of height) for collision checks with captions. */
export const cardHeight = (card: Card) => 0.12 + card.steps.length * 0.075;

/**
 * Card region (0..1 of height). "top"/"bottom" are honoured; "auto" picks whichever side keeps
 * the card off every face in the current shot (faces = [top, bottom] spans, 0..1).
 */
export const cardRegion = (card: Card, faces: [number, number][]): [number, number] => {
  const h = cardHeight(card);
  const top: [number, number] = [CARD_TOP_Y, CARD_TOP_Y + h];
  const bottom: [number, number] = [CARD_BOTTOM_Y, Math.min(0.9, CARD_BOTTOM_Y + h)];
  if (card.position === "top") return top;
  if (card.position === "bottom") return bottom;
  const overlap = ([a, b]: [number, number]) =>
    faces.reduce((acc, [fa, fb]) => acc + Math.max(0, Math.min(b, fb) - Math.max(a, fa)), 0);
  return overlap(top) <= overlap(bottom) ? top : bottom;
};

/** Animated "how to enter" card: springs in, each step slides in when it's spoken, then exits. */
export const StepCards: React.FC<{ cards: Card[]; faces: [number, number][] }> = ({ cards, faces }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  return (
    <AbsoluteFill>
      {cards.map((card, ci) => {
        if (frame < card.from - 2 || frame > card.to + fps * 0.6) return null;
        const enter = spring({ frame: frame - card.from, fps, config: { damping: 15, stiffness: 140 } });
        const exit = spring({ frame: frame - card.to, fps, config: { damping: 20, stiffness: 160 } });
        const vis = enter - exit;
        const [y0] = cardRegion(card, faces);
        return (
          <div
            key={ci}
            style={{
              position: "absolute",
              left: width * 0.08,
              width: width * 0.84,
              top: y0 * height,
              opacity: Math.min(1, vis * 1.4),
              transform: `translateY(${(1 - enter) * -60 + exit * 40}px) scale(${0.9 + 0.1 * vis})`,
              transformOrigin: "50% 0%",
              background: "rgba(255,255,255,0.96)",
              borderRadius: 44,
              padding: "42px 48px 36px",
              boxShadow: "0 24px 60px rgba(0,0,0,0.35)",
              fontFamily: MONTSERRAT,
              color: "#14141a",
            }}
          >
            <div style={{ fontWeight: 900, fontSize: 58, letterSpacing: -1, marginBottom: 22 }}>
              {card.title}
              <div
                style={{
                  height: 8,
                  borderRadius: 4,
                  marginTop: 10,
                  background: card.accent,
                  width: `${interpolate(enter, [0, 1], [0, 38])}%`,
                }}
              />
            </div>
            {card.steps.map((s, i) => {
              const sp = spring({ frame: frame - s.at, fps, config: { damping: 13, stiffness: 180 } });
              return (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 26,
                    margin: "16px 0",
                    opacity: Math.min(1, sp * 1.5),
                    transform: `translateX(${(1 - sp) * -80}px)`,
                  }}
                >
                  <div
                    style={{
                      flex: "0 0 auto",
                      width: 70,
                      height: 70,
                      borderRadius: 35,
                      background: card.accent,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontWeight: 900,
                      fontSize: 38,
                      transform: `scale(${0.6 + 0.4 * sp})`,
                    }}
                  >
                    {s.icon ?? i + 1}
                  </div>
                  <div style={{ fontWeight: 800, fontSize: 46, lineHeight: 1.15 }}>{s.text}</div>
                </div>
              );
            })}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
