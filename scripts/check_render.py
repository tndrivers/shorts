#!/usr/bin/env python3
"""Frame-by-frame check of a rendered short.

    npx remotion render ShortClean out/clean.mp4 --scale=0.5
    python3 scripts/check_render.py out/clean.mp4

Check the ShortClean render (no captions/cards), so text popping in isn't mistaken for camera shake.

For every pair of neighbouring frames inside a shot (cuts are skipped) it measures:
  * shake  - global sub-pixel translation (phase correlation). A slow push-in should be ~0 and smooth;
             back-and-forth motion = jitter / pixel snapping.
  * flicker - jumps in overall brightness that aren't part of a smooth trend.
It also writes out/check/contact.jpg (one frame every 0.5s) to eyeball, and lists the worst frames.
Exit code 1 if anything crosses the thresholds.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
W, H = 540, 960
SHAKE_PX = 0.9   # full-res (1080) pixels off the smooth camera path
FLICKER = 1.2    # luminance levels (0-255), beyond the local trend


def frames(path: Path):
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    size = W * H
    while True:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        yield np.frombuffer(buf, np.uint8).reshape(H, W)
    p.wait()


def main():
    video = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "out" / "clean.mp4")
    if not video.exists():
        sys.exit(f"{video} not found - render first: npm run render")
    tl = json.loads((ROOT / "public" / "generated" / "timeline.json").read_text())
    cuts = {s["from"] for s in tl["segments"]}
    fps = tl["fps"]
    out = ROOT / "out" / "check"
    out.mkdir(parents=True, exist_ok=True)

    # background mask per shot: everything outside the character cutouts (they breathe / talk)
    masks = {}
    for sid, shot in tl["shots"].items():
        m = np.full((H, W), 255, np.uint8)
        k = W / tl["width"]
        for p in shot["pieces"]:
            pad = 0.06 * tl["width"]
            cv2.rectangle(m, (int((p["x"] - pad) * k), int((p["y"] - pad) * k)),
                          (int((p["x"] + p["w"] + pad) * k), int((p["y"] + p["h"] + pad) * k)), 0, -1)
        masks[sid] = m
    seg_of = {}
    for sgm in tl["segments"]:
        for f in range(sgm["from"], sgm["to"]):
            seg_of[f] = sgm["shot"]

    motion, lum, thumbs = [], [], []
    prev = None
    for i, f in enumerate(frames(video)):
        lum.append(float(f.mean()))
        mv = (np.nan, np.nan, np.nan)
        if prev is not None and i not in cuts:
            mask = masks.get(seg_of.get(i, ""), None)
            pts = cv2.goodFeaturesToTrack(prev, 300, 0.01, 10, mask=mask)
            if pts is None or len(pts) < 25:
                pts = cv2.goodFeaturesToTrack(prev, 300, 0.01, 10)
            if pts is not None and len(pts) >= 8:
                nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, f, pts, None, winSize=(21, 21), maxLevel=3)
                good = st.ravel() == 1
                M, _ = cv2.estimateAffinePartial2D(pts[good], nxt[good], method=cv2.RANSAC, ransacReprojThreshold=0.5)
                if M is not None:
                    sc = 1080 / W
                    zoom = (np.hypot(M[0, 0], M[1, 0]) - 1) * W / 2 * sc  # edge displacement from zoom, px
                    mv = (M[0, 2] * sc, M[1, 2] * sc, zoom)
        motion.append(mv)
        prev = f
        if i % (fps // 2) == 0:
            thumbs.append(cv2.resize(f, (W // 3, H // 3)))
    n = len(lum)
    print(f"{video.name}: {n} frames ({n / fps:.1f}s), {len(cuts)} shots")

    problems = []
    # shake: camera motion (background only) should follow a smooth curve; flag frames that jump off it
    s = np.array(motion, float)
    for k in range(n):
        lo, hi = k - 3, k + 4
        if any(c in cuts for c in range(lo + 1, hi)) or np.isnan(s[k]).any():
            continue
        win_ = s[max(0, lo): min(n, hi)]
        win_ = win_[~np.isnan(win_).any(axis=1)]
        if len(win_) < 5:
            continue
        dev = np.abs(s[k] - np.median(win_, axis=0)).max()
        if dev > SHAKE_PX:
            problems.append((k, "shake", f"camera moved {dev:.2f}px off its smooth path"))
    # flicker: brightness minus its own 5-frame median trend
    L = np.array(lum)
    for k in range(2, n - 2):
        if any(c in cuts for c in range(k - 2, k + 3)):
            continue
        trend = np.median(L[k - 2: k + 3])
        if abs(L[k] - trend) > FLICKER:
            problems.append((k, "flicker", f"brightness off-trend by {L[k] - trend:+.2f}"))

    # contact sheet
    cols = 8
    rows = [thumbs[r: r + cols] for r in range(0, len(thumbs), cols)]
    rows[-1] += [np.zeros_like(thumbs[0])] * (cols - len(rows[-1]))
    cv2.imwrite(str(out / "contact.jpg"), np.vstack([np.hstack(r) for r in rows]))

    valid = s[~np.isnan(s).any(axis=1)]
    mags = np.abs(valid).max(axis=1)
    print(f"camera motion per frame (background): max {mags.max():.2f}px, median {np.median(mags):.3f}px")
    if problems:
        print(f"{len(problems)} suspicious frame(s):")
        for k, kind, msg in problems[:40]:
            print(f"  frame {k:5d} ({k / fps:6.2f}s)  {kind:7s} {msg}")
        print("Inspect them with:  npx remotion still Short out/check/f.png --frame=<n>")
    else:
        print("no jitter or flicker found")
    print(f"contact sheet: {out / 'contact.jpg'}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
