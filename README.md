# Shorts: stills + voice lines → animated 1080×1920 Remotion video

This project turns 6 stills, one audio file per line and a `script.md` into a 30 fps vertical Short:

- **Voice track:** trims the silence from each line and joins the lines with short pauses (longer before an emotional line).
- **Captions:** word-by-word timings come from Whisper, but the words use your script's spelling. They're set in Montserrat with no background box, and each shot gets its own caption spot that never covers a face.
- **Shots:** each line cuts to its shot, and a slow push-in drifts toward whoever is talking. The emotional line gets the strongest push.
- **Characters:** they're cut out (rembg) and gently breathe. The background behind them is filled in, so no edges show.
- **Faces:** mouths move with the loudness of the voice, frame by frame, using a jaw-drop cutout with a mouth interior. Blinks are natural, and expressions (smug, soft, happy squint) come from the eyelids.
- **Living backgrounds:** stars, fairy lights, fire with embers and glow, grass in the wind, and warm light flicker. All are coded and fully deterministic.
- **Step cards:** each step pops in on the word where it's spoken ("subscribe", "comment" and so on).
- **No jitter:** there's no grain, randomness or pixel snapping. `npm run check` analyses the render frame by frame.

## 1. One-time setup (Mac)

```bash
brew install ffmpeg node python@3.12
```

```bash
cd /Users/gokulnathbaskaran/Documents/Youtube
git clone <this repo> remotion && cd remotion
```

```bash
npm install
```

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

The first run downloads the cutout model (~180 MB), the face landmark model (4 MB) and the Whisper model.

## 2. Your files

```
/Users/gokulnathbaskaran/Documents/Youtube/
  stills/   S1_wide.png  S2_me.png  S3_sidekick.png  S4_me_react.png  S5_sidekick_sincere.png  S6_behind.png
  audio/
    main_character_audio/   ElevenLabs_2026-11-01T21_39_57_....mp3  ...   (speaker "me")
    buddy_audio/            ElevenLabs_2026-11-01T21_34_26_....mp3  ...   (speaker "sidekick")
  script.md                 (written for you on the first run if it's missing)
```

- **Stills** need `S1`…`S6` somewhere in the name (`S1 wide.png`, `wide_s1.jpg`, `Shot 1.png` and `1.png` all work), or a `"stillsMap": {"S1": "file.png", …}` entry in `config.json`. Use png/jpg/webp; convert HEIC first. Any aspect ratio works; they're cover-cropped to 9:16.
- **Audio filenames can be anything.** Each speaker gets a folder, and the folder name sets the speaker:
  - `main_character_audio`, `main`, `hero` → **me**
  - `buddy_audio`, `buddy`, `friend` → **sidekick**
  - Any other folder name is used as the speaker name, minus the `_audio` ending. Add your own in `speakerAliases` in `config.json`.
- Flat files named `01_me.mp3`, `02_sidekick.mp3` also work.

### First run without script.md

`prepare.py` transcribes every clip with Whisper and writes a draft `script.md`. Each row has the speaker, what was said, and the exact audio file. The rows come out in **generation order** (from the ElevenLabs timestamps), not conversation order. Then:

1. Put the rows in the order they're spoken and renumber `#`.
2. Delete rows for takes you don't want, such as a `(1)` duplicate download.
3. Pick a `Shot` for each line, and optionally an `Expression`, `Emphasis` and `React`.
4. Run `prepare.py` again.

### script.md

```markdown
| #  | Speaker  | Shot | Expression | Emphasis | React | Line | File |
|----|----------|------|------------|----------|-------|------|------|
| 01 | me       | S1   | smug       |          |       | Guess who's giving away a camera? | main_character_audio/ElevenLabs_..._21_39_57_....mp3 |
| 02 | sidekick | S3   |            |          |       | Wait, seriously? | buddy_audio/ElevenLabs_..._21_34_26_....mp3 |
| 05 | sidekick | S5   | soft       | yes      | happy | You all made this channel. | ... |
```

**How each line finds its audio file:**
1. The `File` column, if every row has one. A bare file name is enough.
2. Otherwise `"audioMap"` in `config.json`, e.g. `{"1": "main_character_audio/xyz.mp3"}`.
3. Otherwise Whisper listens to each clip and matches it to the closest `Line` of the same speaker.
4. Without Whisper, the k-th file in a speaker's folder (in name order) becomes that speaker's k-th line.

`prepare.py` prints the final mapping every time, and lists any audio file it didn't use.

**Columns:**
- **Line** is used for caption spelling. Leave it as `(type the line here)` to caption with Whisper's words.
- **Expression:** `neutral`, `smug`, `soft`, `happy` (also accepted: `squint`→happy, `sincere`→soft). It applies to the speaker.
- **React:** the listener's expression while this line plays.
- **Emphasis:** the emotional line. It gets a longer pause before it and a strong, slow push-in.

## 3. Build

```bash
python3 scripts/prepare.py --src /Users/gokulnathbaskaran/Documents/Youtube
```

(`source` in `config.json` is already set to that folder, so plain `python3 scripts/prepare.py` works too.)

This writes `public/generated/`: `voice.wav`, background plates, character cutouts, jaw pieces and `timeline.json`.
Cutouts are cached, so re-running after a script or audio change is fast. Add `--force` to redo them.

**Check the face rig before rendering:**

- `public/generated/debug/S*_rig.jpg` shows the face boxes, which character each face was assigned to, the jaw (magenta), the eyes (orange) and the caption zone (yellow).
- In `npm run studio`, open the **RigCheck** composition: every shot plays with flapping mouths and the rig drawn on top.

## 4. Preview, render, check

```bash
npm run studio
```

```bash
npm run render
```

```bash
npm run check
```

- `npm run render` writes `out/short.mp4`.
- `npm run check` renders a caption-free copy and tracks background points frame by frame. It flags any frame where the camera leaves its smooth path (jitter) or the brightness jumps (flicker), and writes `out/check/contact.jpg`.

## config.json reference

| key | what it does |
|---|---|
| `shotFaces` | Characters left-to-right for each shot, e.g. `"S1": ["me","sidekick"]`. Swap the order if the wrong mouth moves. |
| `camera.pushIn` / `emphasisPushIn` | Push-in amount per shot (0.06 = 6%) and for the emphasis line. |
| `camera.breath` / `breathSeconds` | Breathing stretch and its period. |
| `mouth.maxOpen` | How far the jaw drops at full volume, as a fraction of mouth width (0.26). |
| `audio.pause` / `emphasisPause` / `silenceThresholdDb` | Gaps between lines and the silence trimming level. |
| `whisper.model` | `small.en` by default; use `medium.en` for better timing on fast speech. |
| `stills.cutoutModel` | rembg model: `isnet-general-use` (default), `isnet-anime` for 2D/anime art, `birefnet-general` for best edges (slower). |
| `captions.positions` | Force a caption centre per shot, e.g. `"S4": 0.22` (0 = top, 1 = bottom). |
| `captions.*` | `size`, `weight`, `maxWords` per page, `highlight` colour, `uppercase`. |
| `fx` | Living-background effects per shot (see below). |
| `cards` | Step cards (see below). |
| `rig` | Hand-placed faces for shots where detection fails (see below). |

### Living backgrounds (`fx`)

All coordinates are fractions of the frame (0–1). Effects sit behind the characters unless you set `"layer": "front"`; grass defaults to front.

```json
"fx": {
  "S1": [
    { "type": "stars", "region": [0, 0, 1, 0.4], "count": 70 },
    { "type": "fairyLights", "from": [0.02, 0.06], "to": [0.98, 0.1], "sag": 0.06, "count": 18 },
    { "type": "fairyLights", "points": [[0.21, 0.13], [0.33, 0.15]], "wire": false }
  ],
  "S2": [{ "type": "fire", "x": 0.82, "y": 0.97, "width": 0.3, "height": 0.22, "light": 0.14 }],
  "S6": [{ "type": "grass", "region": [0, 0.9, 1, 0.1], "color": "#3f6b2a", "count": 160 }],
  "S5": [{ "type": "lightFlicker", "color": "#ff9a3c", "strength": 0.1, "x": 0.5, "y": 0.9 }]
}
```

- Use `points` with `wire: false` to make bulbs that are already in the still twinkle.
- Place `fire` on top of a fire in the still so it flickers, throws embers and lights the scene.

### Step cards (`cards`)

```json
"cards": [{
  "fromLine": 3, "toLine": 4, "title": "How to enter", "position": "auto",
  "steps": [
    { "text": "Subscribe", "word": "subscribe" },
    { "text": "Comment your dream shot", "word": "comment" },
    { "text": "Share this Short", "word": "share" }
  ]
}]
```

- Each step appears when its `word` is spoken. Without a `word`, steps appear one after another.
- `position: "auto"` puts the card on whichever side has no faces, and the captions move out of its way.

### Manual face rig (`rig`)

MediaPipe finds most human and Pixar-style faces. For an animal sidekick or a face it misses, place the face by hand. Coordinates are 0–1 of the 9:16 frame, so read them off `debug/S*_rig.jpg`:

```json
"rig": {
  "S3": [{
    "character": "sidekick",
    "mouth": { "x": 0.52, "y": 0.41, "w": 0.06 },
    "chinY": 0.45,
    "eyes": [{ "x": 0.46, "y": 0.33, "w": 0.04, "h": 0.02 }, { "x": 0.57, "y": 0.33, "w": 0.04, "h": 0.02 }]
  }]
}
```

A manual rig replaces detection for that shot, so list every face you want animated.

## How it's built

```
scripts/prepare.py            pipeline entry point (steps 1-4)
scripts/shortkit/audio.py     silence trim, joining, loudness → mouth envelope
scripts/shortkit/transcribe.py  Whisper word timings aligned to script spelling
scripts/shortkit/rig.py       cover-crop, rembg cutout, background fill, MediaPipe face rig, caption spot
scripts/check_render.py       frame-by-frame jitter/flicker check
src/Short.tsx                 cuts, captions, cards, audio
src/Shot.tsx                  camera push-in, plate, fx, breathing cutouts
src/Face.tsx                  jaw-drop lip sync, mouth interior, eyelids
src/Captions.tsx  src/StepCards.tsx  src/fx/*
```

### Notes

- **Lip sync** is a puppet-style jaw drop driven by loudness, not generated mouth shapes. It reads well at Shorts size. If a mouth opens too wide or not enough, tune `mouth.maxOpen`.
- **Background fill** uses OpenCV by default. For a cleaner fill on wide shots, run `pip install simple-lama-inpainting` and LaMa is used automatically.
- **Font:** Montserrat is bundled from npm, so renders don't need the network.
