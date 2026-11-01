import React, { useMemo } from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { MONTSERRAT } from "./fonts";
import { Timeline, Word } from "./types";

type Page = { words: Word[]; start: number; end: number; line: number };

/** Split each line into short pages (max N words, break after punctuation). Pages never cross lines. */
function buildPages(words: Word[], maxWords: number): Page[] {
  const pages: Page[] = [];
  let cur: Word[] = [];
  const flush = () => {
    if (cur.length) pages.push({ words: cur, start: cur[0].start, end: cur[cur.length - 1].end, line: cur[0].line });
    cur = [];
  };
  words.forEach((w, i) => {
    if (cur.length && (cur[0].line !== w.line || cur.length >= maxWords)) flush();
    cur.push(w);
    const next = words[i + 1];
    const longGap = next && next.start - w.end > 0.35;
    if (/[.,!?;:…]$/.test(w.text) || longGap) flush();
  });
  flush();
  return pages;
}

/**
 * Word-by-word captions: each word pops in exactly when it's spoken, the current word is highlighted.
 * Clean Montserrat, outline + soft shadow for legibility, no background box.
 */
export const Captions: React.FC<{ timeline: Timeline; y: number }> = ({ timeline, y }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const c = timeline.captions;
  const pages = useMemo(() => buildPages(timeline.words, c.maxWords), [timeline.words, c.maxWords]);
  const t = frame / fps;

  // active page: started, and the next page hasn't; hide shortly after the line ends
  let page: Page | null = null;
  for (let i = 0; i < pages.length; i++) {
    const p = pages[i];
    const nextStart = pages[i + 1]?.start ?? Infinity;
    const hideAt = Math.min(nextStart, p.end + 0.6);
    if (t >= p.start - 0.04 && t < hideAt) page = p;
  }
  if (!page) return null;

  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: width * 0.07,
          width: width * 0.86,
          top: y * height,
          transform: "translateY(-50%)",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          alignItems: "baseline",
          columnGap: c.size * 0.28,
          rowGap: c.size * 0.05,
          fontFamily: MONTSERRAT,
          fontWeight: c.weight,
          fontSize: c.size,
          lineHeight: 1.12,
          letterSpacing: -0.5,
          textAlign: "center",
          textTransform: c.uppercase ? "uppercase" : "none",
        }}
      >
        {page.words.map((w, i) => {
          const startF = w.start * fps;
          const shown = frame >= startF - 1;
          const pop = spring({ frame: frame - startF + 1, fps, config: { damping: 14, stiffness: 220, mass: 0.6 } });
          const active = t >= w.start - 0.03 && (i === page!.words.length - 1 ? t < w.end + 0.25 : t < page!.words[i + 1].start - 0.03);
          const sc = interpolate(pop, [0, 1], [0.72, 1]);
          return (
            <span
              key={i}
              style={{
                display: "inline-block",
                opacity: shown ? Math.min(1, pop * 1.6) : 0,
                transform: `translateY(${(1 - pop) * 18}px) scale(${active ? sc * 1.06 : sc})`,
                color: active ? c.highlight : c.color,
                WebkitTextStroke: `${c.size * 0.11}px ${c.stroke}`,
                paintOrder: "stroke fill",
                textShadow: `0 ${c.size * 0.06}px ${c.size * 0.18}px rgba(0,0,0,0.55)`,
              }}
            >
              {w.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
