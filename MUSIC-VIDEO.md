# Making a music video, end to end

Written 2026-08-23, after producing a 1:54 video from a supplied track and a
shot-by-shot treatment. Everything here is measured on that job, not projected.

Output: `out/chhupke/chhupke-se-aa.mp4` — 18 shots, 113.8s, plus four vertical
shorts in `out/chhupke/shorts/`.

## The pipeline that worked

Stills first, then motion. Video models drift, and there is no fixing a face
after the fact — so the character is locked as a still and every shot is
generated with that still fed in as reference. The motion stage then only has to
animate a frame that is already correct.

| Stage | Script | What it does |
|---|---|---|
| 1. Character lock | — | 3 candidates per character, pick one, that PNG becomes the reference |
| 2. Shot manifest | — | `out/<job>/shots.json` — id, timecode, who is in it, mode, description |
| 3. Stills | `scripts/gen-shots.py` | 3 seeds per shot, 6 for shots with a prop; contact sheets for review |
| 4. Selection | — | one still per shot into `final/`, recorded in `review/final-selection.json` |
| 5. Motion | `scripts/animate-shots.py` | one clip per still |
| 6. Lip sync (optional) | `scripts/lipsync-batch.py` | replaces the clip for shots that need it |
| 7. Assembly | `scripts/assemble.py` | trims to the treatment's timings, dissolves, lays the master under |
| 8. Vertical | `scripts/make-shorts.py` | 1080x1920 cuts for Reels/Shorts |

⚠ **Review at stage 4, not stage 6.** A wrong still caught in review costs
nothing; the same still animated costs a render and is discarded anyway.

## Measured on our own H100 (RunPod, S2V)

| steps | generate | cost/clip |
|---|---|---|
| 4 | 65.1s | ~$0.09 |
| 20 | 217.6s | **~$0.29** |
| 40 | 405.6s | ~$0.60 |

20 steps was chosen: 54% of the cost of 40 with no difference visible at 832x448
inside a cut. Model load is ~110s and is paid **per worker**, not per clip —
raising `idleTimeout` so a batch lands on one warm worker is worth ~20%.

For comparison, hosted `wan-2.2-i2v-fast` renders a clip in ~37s for roughly
$0.05-0.10. Self-hosting is 3-6x more expensive per clip on this model and buys
LoRA slots and control, not a cheaper render. See RUNPOD.md.

⚠ **S2V returns ~4.74s no matter what duration is requested.** `max_seconds`
above ~4.8 does nothing. Shots longer than that are retimed in assembly, not
re-rendered.

## Lip sync: where it works and where it does not

Tried on eight shots, kept on four. The pattern held every time:

| Works | Fails |
|---|---|
| straight-on close-up | side profile — too little mouth visible |
| she is the only face | two people side by side |
| vocal is strong and clearly hers | mirrors and reflections |
| | quiet passages (~-28dB) — movement is too tentative |

⚠ **A harmony duet cannot be lip-synced by one on-screen singer.** Measured on
this track: 96% of voiced frames contain two independent simultaneous pitches.
Whoever is on screen mouths a blend of both voices, and there is no window long
enough to cut around. The customer's ear caught this immediately; see below for
why no measurement did.

## ⚠ Do not build a fifth voice detector

Four attempts to answer "who is singing right now", all unreliable:

1. `scripts/voice-map.py` — autocorrelation F0. Octave errors: reported 164Hz for
   notes that were 328Hz, so her low notes were labelled male.
2. `scripts/voice-id.py` — harmonic product spectrum with an octave check.
   Over-corrected the other way; called a section female that the listener heard
   as male.
3. Feature clustering (f0 + spectral centroid + rolloff + low-band energy, 2-means).
   **Anti-correlated with ground truth** — called the one clean shot the most
   male, and the shot that actually had him the least.
4. `scripts/lipsync-gate.py` — song-level solo/duet gate. Called three known-solo
   Lyria guide vocals *more* duet (73-84%) than the actual duet (62%). Useless.

The measurement that finally explained it was not a classifier at all: search
each frame for **two independent fundamentals**. That is a different question and
it has an answer.

For a product that cannot ask a human, the honest options are a purpose-built
diarization model, or one toggle at upload. Not more DSP.

## ⚠ `silencedetect` reports the END of a silence

`silence_end: 5.28` on a file that starts with sound means a gap ended at 5.28s.
It does **not** mean the vocal begins there. Read as the latter, it produced two
confident and wrong statements that the opening was instrumental — the customer
corrected it, and a per-second level dump settled it in one command.

Also: `volumedetect` and `silencedetect` log at INFO. `-v error` silences them
and every parse returns nothing.

## Prompting lessons that cost renders

**Describe the frame, not the scene.** "Final close-up of their joined hands"
returned a two-shot with a head cropped off. Naming what fills the rectangle —
and what is excluded — is what controls framing.

**Describe the end state, not the action.** "He places a flower behind her ear"
put the flower on *him* in two of three seeds. "A flower is tucked in her hair,
his ears are bare" does not have an object to get wrong.

**A still cannot show an arc.** "Disbelief becomes hope" made the model
over-act the end state. One held moment, described plainly, with the restraint
stated as positive detail.

**Anatomy needs stating, and framing can dodge it.** A walking two-shot produced
three hands. A rear view with a single hand clasp has almost nothing to get wrong.

## Assembly notes

- Every dissolve **overlaps** its two segments, so N shots lose (N-1) x XFADE.
  A first cut came out 9.3s short of a 114.5s song for exactly this reason;
  segments now carry an extra XFADE each.
- Audio comes from the master, never from the clips — each clip carries whatever
  slice drove its generation.
- Clips shorter than their slot are slowed with `setpts`, capped at 1.7x before
  it reads as slow motion rather than a slow camera.
- `SUBSTITUTE` in `assemble.py` lets one shot borrow another's footage. Used for
  four slots here, including closing on the opening image as a bookend.

## Vertical shorts

Blurred-fill, not a crop: a true 9:16 crop of an 832px-wide clip upscales a
261px strip about 4x and turns to mush. Blurred-fill keeps faces near native
scale. Native 9:16 renders would beat both but mean regenerating from the stills.

## What this job did not settle

- **Scene-accurate cutting.** Shots are asked for as a set; the treatment's own
  scene boundaries and time ranges are not honoured.
- **Real camera footage.** Every reference used has been model-generated. What
  customers upload has not been tested.
- **The India LoRA.** Still blocked on footage; see SHOOT-BRIEF.md. Nothing here
  changes that, and it remains the only thing that makes the output distinctive.
