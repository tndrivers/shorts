#!/usr/bin/env python3
"""Click-to-place face rig for faces the automatic detector misses (stylised / animal characters).

    python3 scripts/rig_editor.py

Opens http://localhost:8765 in your browser. For each shot: pick the character, click the mouth corners,
the chin and the eyes, press Save. Writes rig.json next to config.json; then run prepare.py again.
Needs public/generated/ from a previous `python3 scripts/prepare.py` run.
"""
from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "public" / "generated"
RIG = ROOT / "rig.json"
PORT = 8765

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Face rig editor</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; font: 14px/1.4 -apple-system, system-ui, sans-serif; background: #141418; color: #eee; display: flex; height: 100vh; }
  #side { width: 340px; padding: 16px; box-sizing: border-box; overflow-y: auto; border-right: 1px solid #2a2a33; }
  #stage { flex: 1; display: flex; align-items: center; justify-content: center; position: relative; }
  #wrap { position: relative; height: 94vh; }
  #wrap img { height: 100%; display: block; user-select: none; -webkit-user-drag: none; }
  #wrap canvas { position: absolute; left: 0; top: 0; width: 100%; height: 100%; cursor: crosshair; }
  h1 { font-size: 17px; margin: 0 0 10px; }
  .tabs button { margin: 0 4px 6px 0; }
  button { background: #2c2c36; color: #eee; border: 1px solid #444; border-radius: 6px; padding: 6px 10px; cursor: pointer; font: inherit; }
  button.on { background: #ffd400; color: #111; border-color: #ffd400; }
  button.primary { background: #2f7cf6; border-color: #2f7cf6; }
  #prompt { margin: 12px 0; padding: 10px; border-radius: 8px; background: #23232b; min-height: 40px; font-size: 15px; }
  #prompt b { color: #ffd400; }
  .face { padding: 6px 8px; margin: 4px 0; background: #1d1d24; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; }
  .muted { color: #999; font-size: 12px; }
  #status { margin-top: 10px; color: #7fdc7f; min-height: 20px; }
  select { background: #2c2c36; color: #eee; border: 1px solid #444; border-radius: 6px; padding: 5px; font: inherit; }
</style></head>
<body>
<div id="side">
  <h1>Face rig editor</h1>
  <div class="tabs" id="tabs"></div>
  <div class="muted">Green = found automatically. Orange = placed by you.</div>
  <div style="margin-top:12px">
    Character <select id="who"></select>
    <button id="add" class="primary">Place face</button>
  </div>
  <div id="prompt">Pick a shot, choose the character, press <b>Place face</b>.</div>
  <button id="skip" style="display:none">Skip eyes</button>
  <button id="undo" style="display:none">Undo click</button>
  <h3 style="margin:16px 0 6px;font-size:14px">Placed in this shot</h3>
  <div id="faces"></div>
  <div style="margin-top:16px"><button id="save" class="primary">Save rig.json</button></div>
  <div id="status"></div>
  <p class="muted">Tips: zoom the browser (⌘+) for precise clicks. Mouth corners = where the lips meet.
  Chin = lowest point of the jaw. Eyes: outer/inner corner, then the top of the upper lid.
  After saving, run <code>python3 scripts/prepare.py</code> again and check <code>public/generated/debug/</code>.</p>
</div>
<div id="stage"><div id="wrap"><img id="img"><canvas id="cv"></canvas></div></div>
<script>
const STEPS = [
  ["mouthL", "Click the <b>left corner of the mouth</b>"],
  ["mouthR", "Click the <b>right corner of the mouth</b>"],
  ["chin",   "Click the <b>bottom of the chin</b>"],
  ["e1a", "Left eye: click its <b>left corner</b>"],
  ["e1b", "Left eye: click its <b>right corner</b>"],
  ["e1t", "Left eye: click the <b>top of the upper lid</b>"],
  ["e2a", "Right eye: click its <b>left corner</b>"],
  ["e2b", "Right eye: click its <b>right corner</b>"],
  ["e2t", "Right eye: click the <b>top of the upper lid</b>"],
];
let data, rig, shot, pts = null, step = 0;
const $ = (id) => document.getElementById(id);
const img = $("img"), cv = $("cv"), ctx = cv.getContext("2d");

async function load() {
  data = await (await fetch("/data")).json();
  rig = data.rig || {};
  const who = $("who");
  data.characters.forEach((c) => who.add(new Option(c, c)));
  data.shots.forEach((s) => {
    const b = document.createElement("button");
    b.textContent = s.id; b.onclick = () => pick(s.id); b.id = "tab-" + s.id;
    $("tabs").appendChild(b);
  });
  pick((data.shots.find((s) => s.missing.length) || data.shots[0]).id);
}
function pick(id) {
  shot = data.shots.find((s) => s.id === id);
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.id === "tab-" + id));
  img.src = "/gen/" + shot.full.replace("generated/", "") + "?v=" + Date.now();
  if (shot.missing.length) $("who").value = shot.missing[0];
  pts = null; step = 0; prompt();
  img.onload = () => { cv.width = img.naturalWidth; cv.height = img.naturalHeight; draw(); };
  list();
}
function prompt() {
  const on = pts !== null;
  $("skip").style.display = on && step >= 3 ? "" : "none";
  $("undo").style.display = on && step > 0 ? "" : "none";
  $("prompt").innerHTML = on ? `<span class="muted">${$("who").value} · step ${step + 1}/9</span><br>` + STEPS[step][1]
    : shot.sharedWith && !(rig[shot.id] || []).length ? `${shot.id} uses the same image as <b>${shot.sharedWith}</b>, so it reuses the faces placed there.`
    : (shot.missing.length ? `No face found for <b>${shot.missing.join(", ")}</b> in ${shot.id}. Press <b>Place face</b>.`
                            : `${shot.id}: every expected character has a face. Add one anyway if a mouth is wrong.`);
}
$("add").onclick = () => { pts = {}; step = 0; prompt(); };
$("undo").onclick = () => { if (step > 0) { step--; delete pts[STEPS[step][0]]; prompt(); draw(); } };
$("skip").onclick = () => finish();
cv.onclick = (e) => {
  if (!pts) return;
  const r = cv.getBoundingClientRect();
  pts[STEPS[step][0]] = [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height];
  step++;
  if (step >= STEPS.length) finish(); else { prompt(); draw(); }
};
function eye(a, b, t) {
  if (!a || !b || !t) return null;
  const x = (a[0] + b[0]) / 2, w = Math.abs(b[0] - a[0]) * 1.1;
  const cy = (a[1] + b[1]) / 2, top = Math.min(t[1], cy - 0.002);
  const h = (cy - top) * 2 * 1.05;
  return { x, y: cy, w, h };
}
function finish() {
  if (!pts.mouthL || !pts.mouthR || !pts.chin) { $("prompt").innerHTML = "Need at least the mouth corners and chin."; return; }
  const L = pts.mouthL, R = pts.mouthR;
  // widths are fractions of frame width, heights of frame height; the frame is 9:16
  const face = {
    character: $("who").value,
    mouth: { x: (L[0] + R[0]) / 2, y: (L[1] + R[1]) / 2, w: Math.hypot(R[0] - L[0], (R[1] - L[1]) * 16 / 9) },
    chinY: pts.chin[1],
    eyes: [eye(pts.e1a, pts.e1b, pts.e1t), eye(pts.e2a, pts.e2b, pts.e2t)].filter(Boolean),
  };
  const xs = [L[0], R[0], ...face.eyes.flatMap((e) => [e.x - e.w / 2, e.x + e.w / 2])];
  const ys = [pts.chin[1], ...face.eyes.map((e) => e.y - e.h)];
  const pad = 0.02;
  face.box = [Math.min(...xs) - pad, Math.min(...ys) - pad * 2, Math.max(...xs) - Math.min(...xs) + 2 * pad,
              Math.max(...ys) - Math.min(...ys) + pad * 3];
  rig[shot.id] = (rig[shot.id] || []).filter((f) => f.character !== face.character).concat([face]);
  pts = null; step = 0; prompt(); list(); draw();
  $("status").textContent = "Not saved yet — press Save rig.json";
  $("status").style.color = "#ffd400";
}
function list() {
  const box = $("faces"); box.innerHTML = "";
  (rig[shot.id] || []).forEach((f, i) => {
    const d = document.createElement("div"); d.className = "face";
    d.innerHTML = `<span>${f.character}</span>`;
    const del = document.createElement("button"); del.textContent = "Remove";
    del.onclick = () => { rig[shot.id].splice(i, 1); if (!rig[shot.id].length) delete rig[shot.id]; list(); draw(); };
    d.appendChild(del); box.appendChild(d);
  });
  if (!(rig[shot.id] || []).length) box.innerHTML = '<span class="muted">none</span>';
}
function draw() {
  const W = cv.width, H = cv.height, s = W / 1080;
  ctx.clearRect(0, 0, W, H);
  ctx.lineWidth = 3 * s; ctx.font = `${28 * s}px sans-serif`;
  // automatic faces (stage px -> image px)
  shot.autoFaces.forEach((f) => {
    if ((rig[shot.id] || []).some((m) => m.character === f.character)) return;
    ctx.strokeStyle = ctx.fillStyle = "#3ddc84";
    const [x0, y0, x1, y1] = f.box.map((v) => v * s);
    ctx.strokeRect(x0, y0, x1 - x0, y1 - y0); ctx.fillText(f.character || "?", x0, y0 - 8 * s);
  });
  // placed faces
  (rig[shot.id] || []).forEach((f) => {
    ctx.strokeStyle = ctx.fillStyle = "#ff9d2e";
    const mx = f.mouth.x * W, my = f.mouth.y * H, mw = f.mouth.w * W;
    ctx.beginPath(); ctx.moveTo(mx - mw / 2, my); ctx.lineTo(mx + mw / 2, my); ctx.stroke();
    ctx.beginPath(); ctx.ellipse(mx, my, mw * 1.1, Math.max(4, f.chinY * H - my), 0, 0, Math.PI); ctx.stroke();
    f.eyes.forEach((e) => { ctx.beginPath(); ctx.ellipse(e.x * W, e.y * H, e.w * W / 2, e.h * H / 2, 0, 0, 2 * Math.PI); ctx.stroke(); });
    ctx.fillText(f.character, mx - mw / 2, my - mw * 0.6);
  });
  // in-progress clicks
  if (pts) {
    ctx.fillStyle = "#ff3b6b";
    Object.values(pts).forEach(([x, y]) => { ctx.beginPath(); ctx.arc(x * W, y * H, 6 * s, 0, 2 * Math.PI); ctx.fill(); });
  }
}
$("save").onclick = async () => {
  const r = await fetch("/save", { method: "POST", body: JSON.stringify(rig, null, 2) });
  $("status").style.color = r.ok ? "#7fdc7f" : "#ff6b6b";
  $("status").textContent = r.ok ? "Saved rig.json ✓  Now run: python3 scripts/prepare.py" : "Save failed: " + (await r.text());
};
load();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body: bytes, ctype="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        if path == "/data":
            tl = json.loads((GEN / "timeline.json").read_text())
            cfg = json.loads((ROOT / "config.json").read_text()) if (ROOT / "config.json").exists() else {}
            shot_faces = cfg.get("shotFaces", {})
            chars = sorted({l["speaker"] for l in tl["lines"]} | {c for v in shot_faces.values() for c in v})
            shots = []
            for sid, s in sorted(tl["shots"].items()):
                have = {f["character"] for f in s["faces"]}
                expected = shot_faces.get(sid, [])
                shots.append({"id": sid, "full": s["full"], "autoFaces": s["faces"],
                              "missing": [c for c in expected if c not in have]})
            rig = json.loads(RIG.read_text()) if RIG.exists() else cfg.get("rig", {})
            stills_map = cfg.get("stillsMap", {})
            for sh in shots:  # shots sharing an image share hand-placed faces (prepare.py does the same)
                same = [o for o, f in stills_map.items() if o != sh["id"] and f == stills_map.get(sh["id"]) and rig.get(o)]
                if same and not rig.get(sh["id"]):
                    sh["missing"] = [c for c in sh["missing"] if c not in {f["character"] for f in rig[same[0]]}]
                    sh["sharedWith"] = same[0]
            return self._send(200, json.dumps({"shots": shots, "characters": chars, "rig": rig}).encode(), "application/json")
        if path.startswith("/gen/"):
            f = (GEN / path[5:]).resolve()
            if GEN.resolve() in f.parents and f.exists():
                ctype = "image/jpeg" if f.suffix == ".jpg" else "image/png"
                return self._send(200, f.read_bytes(), ctype)
        self._send(404, b"not found")

    def do_POST(self):
        if self.path != "/save":
            return self._send(404, b"not found")
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            rig = json.loads(body)
        except json.JSONDecodeError as e:
            return self._send(400, str(e).encode())
        RIG.write_text(json.dumps(rig, indent=2) + "\n")
        print(f"saved {RIG}  ({sum(len(v) for v in rig.values())} face(s))")
        self._send(200, b"ok")


def main():
    if not (GEN / "timeline.json").exists():
        raise SystemExit("run python3 scripts/prepare.py first (the editor uses its output)")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"rig editor: {url}   (Ctrl+C to stop)")
    webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
