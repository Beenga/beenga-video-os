# Motion and cloth review — the cases this repo actually owns

Reviewed 2026-08-15 on `wan-2.2-5b-fast`, wave 0 baseline clips, one seed, visual inspection of
3–4 sampled frames per clip. No new generation, **$0 spent**.

## Result

| Case | Requirement | Verdict |
|---|---|---|
| `VID-CLOTH-001` pallu in motion | Fabric moves with the body, drape stays coherent | **pass** |
| `VID-CLOTH-002` dupatta flow | One continuous piece, trails with the walk | **pass** |
| `VID-MOT-002` hand integrity | Fingers survive every clap | **pass** |
| `VID-MOT-006` music without instruments | No band or rig pulled into frame | **pass** |
| `VID-MOT-004` one hand raised | Raised hand stays raised for the clip | **FAIL** — hand lowers partway |
| `VID-MOT-005` four friends | Exactly four people | **FAIL** — renders three, all three frames |
| `VID-CLOTH-003` long hair | Volume and length constant | **not measurable** |
| `VID-CLOTH-005` sleeveless persists | Blouse stays sleeveless under movement | **not measurable** |
| `VID-CLOTH-006` two braids | Exactly two, one per shoulder | **not measurable** |
| `VID-MOT-003` walking gait | Feet contact ground, stride consistent | **not measurable** |

Four pass, two fail, **four cannot be judged.**

> **Rewrites verified 2026-08-16** on `wan-2.2-t2v-fast`, `out/rewritten-a14b/`, $0.20.
> All four now generate and all four are scoreable. `VID-CLOTH-005` reads cleanly — dropping the
> sari removed the pallu that was hiding the armhole, and the blouse is visibly sleeveless
> throughout. `VID-CLOTH-006` shows exactly two braids, one per side, because the framing is now
> stated. **The framing fix worked: a case that could not be scored became one that could.**
>
> Second finding, unlooked for: **both subjects read as ambiguously non-Indian.** The A14B India
> defect is not confined to the `VID-DEF-*` scene cases — it shows up on cloth cases too, which
> widens the evidence for the training target rather than narrowing it.

## The benchmark is the problem in four of ten cases

This is a defect in the suite, not in the model, and it is the more useful finding.

- `VID-CLOTH-005` asks whether a blouse stays sleeveless — but the prompt also specifies a sari,
  and **the pallu drapes over the shoulder and hides the armhole.** The attribute is occluded by
  another requested attribute.
- `VID-CLOTH-006` asks for exactly two braids, one per shoulder, and the model framed a
  head-and-shoulders shot in which only one shoulder is in frame. One braid is visible. The
  second may or may not exist.
- `VID-CLOTH-003` asks about hair volume across a fast head turn, and the render is a tight
  face crop with an arm across it.
- `VID-MOT-003` asks whether feet contact the ground across a gait cycle, which three sampled
  frames cannot answer at all — it needs per-frame foot tracking.

**The prompts do not force the framing that makes the attribute visible.** A case that cannot be
scored is worse than no case: it looks like coverage and produces nothing. These four need
rewriting with explicit framing ("full body, both shoulders visible, wide shot") before they are
run again, and `VID-MOT-003` needs an instrument rather than an eye.

## The two real defects, and why they may not be training targets

**`VID-MOT-004` — attribute decay.** "One hand raised above her head, the other at her waist."
Frame 1 is correct. By the end the raised hand has come down. Limb count stays right; the
*instruction* decays over time. This is the flagship video-unique failure class — there is no
still-image equivalent, and it is the kind of thing only this project can find.

**`VID-MOT-005` — count error.** Four friends requested, three rendered, stable across all
sampled frames. Note the contrast with A14B, which got the count closer but rendered Western
casting; 5B gets the people right and the number wrong.

### The uncomfortable observation

**Neither defect is India-specific.**

Attribute decay and miscounting are generic weaknesses of current video models. Every user of
Wan 2.2 has them, in every language and every country. A LoRA that fixed them would make Beenga
*better at counting people*, which is a different product from *better for Indian users*.

Every India-specific defect measured so far — ceremonial default, garment prior, complexion,
ethnicity — is an **appearance** defect, and in an image-to-video pipeline appearance is fixed by
the reference still. That is `beenga-image`'s territory, where a sample costs $0.001.

So the honest position after wave 0, wave 1, the arm C bake-off and this review:

> **No India-specific video-side training target has been found.** The differentiator is looking
> like the still plus the pipeline, not a video LoRA.

That is not a negative result. It is the same shape as the finding that saved `beenga-image` from
a 69-bucket training program — measuring first said the expensive work was not needed. It cost
$7.30 to establish here, and it redirects the training budget to the repo where the defects
actually live.

---

## Probed 2026-08-16 — and one target survives

Six `indian_dance` cases, $0.30, plus $0.30 for 3-seed confirmation on the failures.

| Case | Verdict |
|---|---|
| `VID-DANCE-005` sari under fast spin | **pass** — sari flares with rotation, fabric keeps weight and coherence |
| `VID-DANCE-006` dupatta under dance | **pass** — tracks the arms, stays one piece |
| `VID-DANCE-003` bhangra | **pass** — raised-arm vocabulary, fists, bounce all recognisable |
| `VID-DANCE-002` kathak chakkar | partial — real rotation without smearing, but slow turns, not fast continuous chakkar |
| `VID-DANCE-004` garba | partial — clapping present, circular formation not visibly rendered |
| `VID-DANCE-001` **bharatanatyam** | **FAIL, 3/3 seeds** |

### The garment-physics hypothesis was wrong

Both cloth cases that passed earlier tested gentle movement — a walk and a turn — so the working
theory was that fast movement would break them. **It does not.** A silk sari under a fast spin is
the sharpest garment test in the suite and it passes cleanly. There is no cloth-dynamics training
target.

### `VID-DANCE-001` is the one real find

Three seeds, three failures, and the failure mode is consistent:

- seed 1234 — static *anjali* (namaste), held for the whole clip
- seed 2026 — static *anjali* again
- seed 77 — **the head is not in frame at all.** Every frame is cropped at the collarbone: torso,
  arms and crossed legs, no head, no face, for the whole 3.4 seconds. The hands do form
  mudra-like shapes, so some vocabulary is present — but the shot has no performer's face in it.

**Correction, 2026-08-16.** Seed 77 was first written up here as "a woman seated cross-legged in
what reads as a yoga pose", which skipped the most notable thing in the frame. Biren caught it
from the contact sheet. The headless framing is a **separate and more serious defect than the
missing dance vocabulary** — a music-video shot with no face is unusable regardless of technique,
and it is not specific to bharatanatyam. It also silently breaks every face-based instrument in
`/Users/hanumanji/demo/beenga-video-os/scripts/score-clips.py`: CSIM on this clip would report
"no face found" and be discarded as a measurement failure rather than recorded as a generation
failure, which is exactly backwards.

**Open:** how often does 5B frame a human subject with the head out of shot? One occurrence in
six dance clips is not a rate. It needs a dedicated case and three seeds, and the scorer needs to
treat "no face detected in a clip that requested a person" as a FINDING rather than a gap.

No araimandi half-sit on any seed. No mudra sequence. No dance movement.

**And the costume is correct on 3 of 3.** Silk, jewellery, jasmine, temple-adjacent backdrop —
all right. The model has learned bharatanatyam **as a look and not as a movement system**, so
asked to animate it, it falls back to adjacent "posed Indian person" concepts.

That split is exactly the ownership line this repo is organised around, and it is the cleanest
demonstration of it yet: **appearance correct, motion absent.** Appearance is the still's job and
it works. Motion is this repo's job and it fails.

### So: is it worth training?

Honestly assessed rather than argued for.

**For it.** It is confirmed at three seeds, it is unambiguously video-specific, it is
unambiguously India-specific, and no open model does it — which is the definition of a
differentiator. Classical dance is also well documented, so a dataset of 50–150 clips is
tractable to source, and this is motion data where synthetic generation is not automatically
poisoned the way synthetic *appearance* data is: the base model's failure is that it produces no
technique at all, not that it produces subtly wrong technique.

**Against it.** For a Hindi/Hinglish music-video product, bhangra and garba are more common than
bharatanatyam, and both largely work. This may be a narrow slice of demand.

**The counter to that**, worth weighing: the devotional bhajan is a real content type — one was
generated for Geet Suhane this week — and devotional music video in India pairs with classical
dance routinely. The slice may be less narrow than a first pass suggests.

**Recommendation:** this is the first defect that has earned a training scope discussion. It is
not an obvious yes. It is the only candidate, and it is real.

### DECIDED 2026-08-16 — not now

Biren: *"not required now."* Bhangra and garba cover the content that matters; classical dance
technique is not on the near roadmap.

**So this repo has no training programme.** Every India-specific defect measured across wave 0,
wave 1, the arm C bake-off and this review turned out to be either an appearance defect — which
belongs to `beenga-image`, where a sample costs $0.001 — or a generic video-model weakness that
is not India-specific at all.

That is a real result, not an absence of one. It cost **$9.90** to establish, and it redirects
the entire training budget to the repo where the defects actually live. The same shape as
`beenga-image` collapsing a 69-bucket programme into two defects and then one.

**What Beenga Video OS is, therefore:** a measured, licence-audited pipeline and a benchmark —
not a fine-tune. The differentiator is the reference still plus the chaining strategy plus the
knowledge of which knobs are traps. `VID-DANCE-001` stays in the suite as a known, documented
limitation of the base model, ready if the content roadmap changes.

### What would change this

A defect that is *both* video-specific and India-specific. Candidates not yet tested:

- **Indian classical and folk dance motion** — bharatanatyam mudras, kathak spins, bhangra.
  Highly specific movement vocabularies that a Western-weighted corpus is likely to render
  badly, and they are unambiguously motion rather than appearance.
- **Garment physics under Indian movement** — a sari during a spin, a dupatta during dance
  rather than a walk. The two cloth cases that passed both tested gentle movement.

Neither has been probed. Both are cheap. **If a training target exists for this repo, it is most
likely there** — and it is worth a targeted run before concluding there is nothing to train.
