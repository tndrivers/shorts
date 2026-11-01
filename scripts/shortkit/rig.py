"""Stills -> background plate, character cutouts, and a face rig (mouth/jaw piece, eyes, lid colours).

Everything is written in "stage" pixels (the 1080x1920 frame) so Remotion can place it directly.
Images are saved at `scale`x (default 1.5x) so camera push-ins stay sharp.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

import cv2
import numpy as np

FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)

# MediaPipe face-mesh indices
INNER_LOWER_LIP = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308]
INNER_UPPER_LIP = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308]
FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377,
             152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
EYE_A = [33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7]
EYE_B = [263, 466, 388, 387, 386, 385, 384, 398, 362, 382, 381, 380, 374, 373, 390, 249]
CHEEKS = [50, 280]


# --------------------------------------------------------------------------- helpers
def cover_fit(img: np.ndarray, w: int, h: int) -> np.ndarray:
    ih, iw = img.shape[:2]
    s = max(w / iw, h / ih)
    nw, nh = int(round(iw * s)), int(round(ih * s))
    interp = cv2.INTER_LANCZOS4 if s > 1 else cv2.INTER_AREA
    r = cv2.resize(img, (nw, nh), interpolation=interp)
    x0, y0 = (nw - w) // 2, (nh - h) // 2
    return r[y0: y0 + h, x0: x0 + w]


def hex_color(rgb) -> str:
    r, g, b = [int(np.clip(v, 0, 255)) for v in rgb]
    return f"#{r:02x}{g:02x}{b:02x}"


def poly_mask(shape, pts) -> np.ndarray:
    m = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(m, [np.round(np.asarray(pts)).astype(np.int32)], 255)
    return m


def save_rgba(path: Path, rgb: np.ndarray, alpha: np.ndarray):
    rgba = np.dstack([rgb, np.clip(alpha * 255, 0, 255).astype(np.uint8)])
    cv2.imwrite(str(path), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA), [cv2.IMWRITE_PNG_COMPRESSION, 6])


# --------------------------------------------------------------------------- cutout
_SESSION = {}


def cutout_alpha(rgb: np.ndarray, model: str) -> np.ndarray:
    from PIL import Image
    from rembg import new_session, remove

    if model not in _SESSION:
        _SESSION[model] = new_session(model)
    mask = remove(Image.fromarray(rgb), session=_SESSION[model], only_mask=True, post_process_mask=False)
    a = np.asarray(mask).astype(np.float32) / 255.0
    # drop specks: keep components bigger than 0.3% of the frame
    n, lab, stats, _ = cv2.connectedComponentsWithStats((a > 0.5).astype(np.uint8), 8)
    keep = np.zeros_like(a, bool)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] > 0.003 * a.size:
            keep |= lab == i
    keep = cv2.dilate(keep.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    return a * keep


def split_pieces(alpha: np.ndarray, min_frac=0.02):
    """Separate characters that don't touch, so each can breathe on its own rhythm."""
    solid = (alpha > 0.5).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(solid, 8)
    comps = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] > min_frac * alpha.size]
    if not comps:
        return [alpha]
    # every soft-edge pixel belongs to its nearest solid component
    dist_labels = np.zeros_like(lab)
    seeds = np.zeros_like(solid)
    for k, i in enumerate(comps):
        seeds[lab == i] = k + 1
    inv = (seeds == 0).astype(np.uint8)
    _, nearest = cv2.distanceTransformWithLabels(inv, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    # map pixel-label -> seed id
    seed_ids = np.zeros(nearest.max() + 1, np.int32)
    ys, xs = np.nonzero(seeds)
    seed_ids[nearest[ys, xs]] = seeds[ys, xs]
    dist_labels = seed_ids[nearest]
    return [alpha * (dist_labels == k + 1) for k in range(len(comps))]


def fill_background(rgb: np.ndarray, alpha: np.ndarray, grow: float) -> np.ndarray:
    """Clean plate: remove the characters and fill the hole so no edges show when they move."""
    h, w = alpha.shape
    r = max(3, int(grow * w))
    hole = cv2.dilate((alpha > 0.03).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    try:  # best quality when installed: pip install simple-lama-inpainting
        from PIL import Image
        from simple_lama_inpainting import SimpleLama  # type: ignore

        out = np.asarray(SimpleLama()(Image.fromarray(rgb), Image.fromarray(hole * 255)))[:h, :w]
        return out
    except ImportError:
        pass
    # OpenCV fallback, done at half res and pasted back only inside the hole
    small = cv2.resize(rgb, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    hs = cv2.resize(hole, (w // 2, h // 2), interpolation=cv2.INTER_NEAREST)
    filled = cv2.inpaint(cv2.cvtColor(small, cv2.COLOR_RGB2BGR), hs, 12, cv2.INPAINT_TELEA)
    filled = cv2.cvtColor(filled, cv2.COLOR_BGR2RGB)
    # soften the smeared fill a bit so it reads like out-of-focus background
    filled = np.where(hs[..., None] > 0, cv2.GaussianBlur(filled, (0, 0), 6), filled)
    big = cv2.resize(filled, (w, h), interpolation=cv2.INTER_CUBIC)
    m = cv2.GaussianBlur(hole.astype(np.float32), (0, 0), 3)[..., None]
    return (rgb * (1 - m) + big * m).astype(np.uint8)


# --------------------------------------------------------------------------- faces
_LANDMARKER = None


def detect_faces(rgb: np.ndarray, cache: Path, expected: int = 1):
    global _LANDMARKER
    try:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
    except ImportError:
        print("  ! mediapipe not installed: no automatic face rig (use config.json 'rig' to place faces by hand)")
        return []
    if _LANDMARKER is None:
        model = cache / "face_landmarker.task"
        if not model.exists():
            cache.mkdir(parents=True, exist_ok=True)
            print("  downloading face landmarker model ...")
            urllib.request.urlretrieve(FACE_MODEL_URL, model)
        opts = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model)), num_faces=4,
            min_face_detection_confidence=0.25, min_face_presence_confidence=0.25,
        )
        try:
            _LANDMARKER = vision.FaceLandmarker.create_from_options(opts)
        except Exception as e:
            print(f"  ! MediaPipe face landmarker failed to start ({e}); use config.json 'rig' to place faces by hand")
            _LANDMARKER = False
    if _LANDMARKER is False:
        return []
    h, w = rgb.shape[:2]

    def run(x0, y0, x1, y1):
        crop = np.ascontiguousarray(rgb[y0:y1, x0:x1])
        res = _LANDMARKER.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=crop))
        cw, ch = x1 - x0, y1 - y0
        return [np.array([[x0 + p.x * cw, y0 + p.y * ch] for p in lms], np.float32) for lms in res.face_landmarks]

    faces = run(0, 0, w, h)
    if len(faces) < expected:
        # small faces in wide shots: search overlapping tiles too
        tw, th = int(w * 0.6), int(h * 0.4)
        for ty in np.linspace(0, h - th, 5).astype(int):
            for tx in np.linspace(0, w - tw, 3).astype(int):
                faces += run(tx, ty, tx + tw, ty + th)
    # de-duplicate (same face found in several tiles): keep the larger detection
    faces.sort(key=lambda p: -(np.ptp(p[:, 0]) * np.ptp(p[:, 1])))
    kept = []
    for f in faces:
        c = f.mean(axis=0)
        size = max(np.ptp(f[:, 0]), np.ptp(f[:, 1]))
        if size < 0.03 * w:
            continue
        if all(np.linalg.norm(c - k.mean(axis=0)) > 0.35 * max(np.ptp(k[:, 0]), np.ptp(k[:, 1])) for k in kept):
            kept.append(f)
    kept.sort(key=lambda p: p[:, 0].mean())
    return kept


def _sample(rgb, mask, fallback=(200, 160, 140)):
    px = rgb[mask > 0]
    if px.size == 0:
        return np.array(fallback, float)
    return np.median(px, axis=0)


def _expand(poly, k):
    c = poly.mean(axis=0)
    return c + (poly - c) * k


def rig_from_landmarks(pts: np.ndarray, rgb: np.ndarray, alpha: np.ndarray):
    h, w = alpha.shape
    lower = pts[INNER_LOWER_LIP]
    upper = pts[INNER_UPPER_LIP]
    corner_l, corner_r = pts[78], pts[308]
    mouth_w = float(np.linalg.norm(pts[61] - pts[291]))
    mouth_c = (pts[13] + pts[14]) / 2
    # jaw = everything of the face below the lower lip, down around the chin
    oval = pts[FACE_OVAL]
    below = [p for p in oval if p[1] > mouth_c[1] - 0.05 * mouth_w]
    ang = [np.arctan2(p[1] - mouth_c[1], p[0] - mouth_c[0]) for p in below]
    below = [p for _, p in sorted(zip(ang, below), key=lambda t: t[0])]
    jaw_poly = np.vstack([lower, np.array(below)]) if below else lower
    eyes = [_expand(pts[EYE_A], 1.18), _expand(pts[EYE_B], 1.18)]
    return _finish_face(rgb, alpha, jaw_poly, lower, upper, mouth_c, mouth_w, (corner_l, corner_r), eyes,
                        face_box=(oval[:, 0].min(), oval[:, 1].min(), oval[:, 0].max(), oval[:, 1].max()),
                        cheeks=pts[CHEEKS])


def rig_from_manual(spec: dict, rgb: np.ndarray, alpha: np.ndarray, sw: float, sh: float):
    """Hand-placed rig (normalized 0..1 coords) for faces MediaPipe can't find, e.g. animals."""
    h, w = alpha.shape
    m = spec["mouth"]
    mc = np.array([m["x"] * w, m["y"] * h])
    mw = m["w"] * w
    chin = spec.get("chinY", m["y"] + m["w"] * 0.9) * h
    lower = np.array([[mc[0] - mw * 0.45 + mw * 0.9 * t, mc[1] + np.sin(np.pi * t) * mw * 0.06] for t in np.linspace(0, 1, 11)])
    upper = lower.copy()
    jw = spec.get("jawWidth", m["w"] * 2.2) * w
    arc = [[mc[0] + np.cos(a) * jw / 2, mc[1] + np.sin(a) * (chin - mc[1])] for a in np.linspace(0, np.pi, 24)]
    jaw_poly = np.vstack([lower, np.array(arc)])
    eyes = []
    for e in spec.get("eyes", []):
        c = np.array([e["x"] * w, e["y"] * h])
        eyes.append(np.array([[c[0] + np.cos(a) * e["w"] * w / 2, c[1] + np.sin(a) * e["h"] * h / 2]
                              for a in np.linspace(0, 2 * np.pi, 24, endpoint=False)]))
    fb = spec.get("box")
    box = (fb[0] * w, fb[1] * h, (fb[0] + fb[2]) * w, (fb[1] + fb[3]) * h) if fb else (
        mc[0] - jw, (mc[1] - 2.2 * mw), mc[0] + jw, chin)
    return _finish_face(rgb, alpha, jaw_poly, lower, upper, mc, mw, (lower[0], lower[-1]), eyes, box, None)


def _finish_face(rgb, alpha, jaw_poly, lower, upper, mouth_c, mouth_w, corners, eyes, face_box, cheeks):
    h, w = alpha.shape
    # crisp top edge at the lip line, feathered sides/chin
    jaw = poly_mask(alpha.shape, jaw_poly).astype(np.float32) / 255
    sig = max(1.5, 0.07 * mouth_w)
    soft = np.clip(cv2.GaussianBlur(jaw, (0, 0), sig) * 2.0, 0, 1)
    lip_line = np.vstack([[[-10, lower[0][1]]], lower, [[w + 10, lower[-1][1]]], [[w + 10, h + 10]], [[-10, h + 10]]])
    lip_mask = poly_mask(alpha.shape, lip_line).astype(np.float32) / 255
    crisp = cv2.GaussianBlur(lip_mask, (0, 0), 0.8)
    feather = cv2.GaussianBlur(lip_mask, (0, 0), max(2.0, 0.14 * mouth_w))
    # taper sideways from the mouth: the chin moves fully, the cheeks barely, so no seam shows
    xs_ = np.arange(w, dtype=np.float32)[None, :]
    dx = np.abs(xs_ - mouth_c[0]) / max(mouth_w, 1)
    side = np.clip((1.05 - dx) / 0.6, 0, 1)
    side = side * side * (3 - 2 * side)
    # sharp lip line between the mouth corners, soft blend out toward the cheeks (no seam)
    wc = np.clip((0.75 - dx) / 0.3, 0, 1)
    below_lip = crisp * wc + feather * (1 - wc)
    jaw_a = soft * below_lip * side * np.clip(alpha * 1.2, 0, 1)
    ys, xs = np.nonzero(jaw_a > 0.01)
    jaw_piece = None
    if ys.size:
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        jaw_piece = {"crop": (x0, y0, x1, y1), "rgb": rgb[y0:y1, x0:x1], "alpha": jaw_a[y0:y1, x0:x1]}

    # eyelid colour: skin just above each eye (fall back to cheeks if it's hair/brow-dark)
    skin = _sample(rgb, sum(poly_mask(alpha.shape, [[c[0] - 6, c[1] - 6], [c[0] + 6, c[1] - 6], [c[0] + 6, c[1] + 6], [c[0] - 6, c[1] + 6]]) for c in cheeks)) if cheeks is not None else None
    eye_out = []
    for e in eyes:
        eh = e[:, 1].max() - e[:, 1].min()
        above = poly_mask(alpha.shape, e - [0, 0.75 * eh]) & ~poly_mask(alpha.shape, e)
        lid = _sample(rgb, above)
        if skin is not None and lid.mean() < 0.55 * skin.mean():
            lid = skin * 0.93
        lash = lid * 0.28
        eye_out.append({"poly": e, "lid": hex_color(lid), "lash": hex_color(lash)})
    return {
        "mouth": {"center": mouth_c, "width": mouth_w, "innerWidth": float(np.linalg.norm(corners[1] - corners[0])),
                  "upperY": float(np.max(upper[:, 1])), "lowerY": float(np.min(lower[:, 1]))},
        "jaw": jaw_piece,
        "eyes": eye_out,
        "box": face_box,
        "skin": hex_color(skin) if skin is not None else None,
    }


# --------------------------------------------------------------------------- captions
def pick_caption_y(face_boxes_norm, alpha_box_norm, prefs):
    """Choose a caption centre (0..1) that keeps the text block off every face."""
    half = 0.065
    blocks = [(b[1] - 0.03, b[3] + 0.03) for b in face_boxes_norm]
    if not blocks and alpha_box_norm:  # no faces found: assume heads are the top 35% of the cutout
        t, btm = alpha_box_norm[1], alpha_box_norm[3]
        blocks = [(t - 0.02, t + 0.35 * (btm - t))]

    def clearance(y):
        lo, hi = y - half, y + half
        return min([max(lo - b[1], b[0] - hi) for b in blocks] or [1.0])

    for y in prefs:
        if clearance(y) >= 0:
            return y
    return max(prefs, key=clearance)


# --------------------------------------------------------------------------- per shot
def build_shot(shot_id, path: Path, cfg, out_dir: Path, cache: Path, characters_for_faces):
    W, H = cfg["width"], cfg["height"]
    S = cfg["stills"]["scale"]
    w, h = int(W * S), int(H * S)
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"cannot read {path}")
    rgb = cover_fit(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), w, h)
    print(f"  {shot_id}: cutout ({cfg['stills']['cutoutModel']}) ...")
    alpha = cutout_alpha(rgb, cfg["stills"]["cutoutModel"])
    print(f"  {shot_id}: filling background ...")
    plate = fill_background(rgb, alpha, cfg["stills"]["fillGrow"])
    k = 1 / S  # image px -> stage px
    rel = lambda p: f"generated/{p}"

    cv2.imwrite(str(out_dir / f"{shot_id}_plate.jpg"), cv2.cvtColor(plate, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 94])
    cv2.imwrite(str(out_dir / f"{shot_id}_full.jpg"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 94])

    pieces_alpha = split_pieces(alpha)
    pieces = []
    for i, pa in enumerate(pieces_alpha):
        ys, xs = np.nonzero(pa > 0.01)
        if not ys.size:
            continue
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        name = f"{shot_id}_char{i}.png"
        save_rgba(out_dir / name, rgb[y0:y1, x0:x1], pa[y0:y1, x0:x1])
        pieces.append({"src": rel(name), "x": x0 * k, "y": y0 * k, "w": (x1 - x0) * k, "h": (y1 - y0) * k,
                       "mask": pa > 0.5})

    # faces: manual rig wins, else MediaPipe
    manual = cfg.get("rig", {}).get(shot_id)
    # hand-placed faces (rig editor / config "rig") + automatic detection for everyone else
    manual = manual or []
    faces_raw = [(m.get("character"), rig_from_manual(m, rgb, alpha, w, h)) for m in manual]
    taken = {c for c, _ in faces_raw}
    names = [n for n in characters_for_faces if n not in taken]
    auto = []
    if names or not manual:
        lms = detect_faces(rgb, cache, max(1, len(names)))
        # drop detections that sit on a hand-placed face
        def on_manual(pts):
            c = pts.mean(axis=0)
            return any(f["box"][0] <= c[0] <= f["box"][2] and f["box"][1] <= c[1] <= f["box"][3] for _, f in faces_raw)
        lms = [p for p in lms if not on_manual(p)]
        auto = [(names[i] if i < len(names) else None, rig_from_landmarks(p, rgb, alpha)) for i, p in enumerate(lms)]
    faces_raw = sorted(faces_raw + auto, key=lambda cf: cf[1]["mouth"]["center"][0])
    print(f"  {shot_id}: {len(pieces)} character piece(s), {len(faces_raw)} face(s) "
          f"{[c for c, _ in faces_raw]}{f' ({len(manual)} hand-placed)' if manual else ''}")
    missing = [n for n in characters_for_faces if n not in {c for c, _ in faces_raw}]
    if missing:
        print(f"  ! {shot_id}: no face for {missing} - their mouth won't move here. Place it: python3 scripts/rig_editor.py")

    faces = []
    dbg = rgb.copy()
    for n, (char, f) in enumerate(faces_raw):
        mc = f["mouth"]["center"]
        piece_idx = 0
        for pi, p in enumerate(pieces):
            if p["mask"][int(np.clip(mc[1], 0, h - 1)), int(np.clip(mc[0], 0, w - 1))]:
                piece_idx = pi
        jaw = None
        if f["jaw"]:
            x0, y0, x1, y1 = f["jaw"]["crop"]
            name = f"{shot_id}_jaw{n}.png"
            save_rgba(out_dir / name, f["jaw"]["rgb"], f["jaw"]["alpha"])
            jaw = {"src": rel(name), "x": x0 * k, "y": y0 * k, "w": (x1 - x0) * k, "h": (y1 - y0) * k}
        bx0, by0, bx1, by1 = f["box"]
        faces.append({
            "character": char,
            "piece": piece_idx,
            "mouth": {"x": float(mc[0] * k), "y": float(mc[1] * k), "w": f["mouth"]["width"] * k,
                      "innerW": f["mouth"]["innerWidth"] * k, "upperY": f["mouth"]["upperY"] * k,
                      "lowerY": f["mouth"]["lowerY"] * k},
            "jaw": jaw,
            "eyes": [{"points": (e["poly"] * k).round(2).tolist(), "lid": e["lid"], "lash": e["lash"]} for e in f["eyes"]],
            "box": [bx0 * k, by0 * k, bx1 * k, by1 * k],
        })
        # debug drawing
        cv2.rectangle(dbg, (int(bx0), int(by0)), (int(bx1), int(by1)), (0, 255, 0), 3)
        cv2.circle(dbg, (int(mc[0]), int(mc[1])), 6, (255, 0, 0), -1)
        if f["jaw"]:
            x0, y0, x1, y1 = f["jaw"]["crop"]
            ov = dbg[y0:y1, x0:x1]
            ov[:] = (ov * (1 - 0.45 * f["jaw"]["alpha"][..., None]) + np.array([255, 0, 255]) * 0.45 * f["jaw"]["alpha"][..., None]).astype(np.uint8)
        for e in f["eyes"]:
            cv2.polylines(dbg, [e["poly"].astype(np.int32)], True, (0, 200, 255), 2)
        cv2.putText(dbg, str(char), (int(bx0), int(by0) - 12), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 255, 0), 3)

    # caption placement
    face_norm = [[b / (W if i % 2 == 0 else H) for i, b in enumerate(f["box"])] for f in faces]
    ys, xs = np.nonzero(alpha > 0.5)
    abox = [xs.min() / w, ys.min() / h, xs.max() / w, ys.max() / h] if ys.size else None
    override = cfg["captions"].get("positions", {}).get(shot_id)
    cap_y = float(override) if override is not None else pick_caption_y(face_norm, abox, cfg["captions"]["preferY"])
    cy = int(cap_y * h)
    cv2.rectangle(dbg, (int(0.08 * w), cy - int(0.065 * h)), (int(0.92 * w), cy + int(0.065 * h)), (255, 255, 0), 3)
    cv2.putText(dbg, "captions", (int(0.1 * w), cy), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 0), 4)
    (out_dir / "debug").mkdir(exist_ok=True)
    cv2.imwrite(str(out_dir / "debug" / f"{shot_id}_rig.jpg"),
                cv2.cvtColor(cv2.resize(dbg, (W // 2, H // 2), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2BGR))

    for p in pieces:
        p.pop("mask")
    return {
        "id": shot_id,
        "full": rel(f"{shot_id}_full.jpg"),
        "plate": rel(f"{shot_id}_plate.jpg"),
        "pieces": pieces,
        "faces": faces,
        "captionY": cap_y,
    }
