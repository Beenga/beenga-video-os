# Wave 0 — baseline results

Run 2026-08-15. 23 of 32 cases on each of two candidate bases, 480p, seed 1234, prompt layer
empty. Nine cases skipped: eight singing cases need audio, one needs a still.

**Total spend: $2.30.**

| Tag | Model | Native clip | Generated |
|---|---|---|---|
| `base-5b` | `wan-video/wan-2.2-5b-fast` | 121f @ 24fps (5.04s) | 23/23 |
| `base-a14b` | `wan-video/wan-2.2-t2v-fast` | 81f @ 16fps (5.06s) | 23/23 |

## CONFIRMED at three seeds — base model decided

Seeds 1234 / 77 / 2026, six default-behaviour cases, both bases. 24 additional clips, $1.20.
H1 and H2 below were written as one-seed hypotheses. Both held.

| | Renders India | Ceremonial default |
|---|---|---|
| **`wan-2.2-5b-fast`** | **3/3 correct** | **3/3 fail** — silk sari and gold jewellery on every seed |
| **`t2v-fast` (A14B)** | **0/3** | n/a — never gets far enough to stereotype |

**`VID-DEF-004`, "a busy street in Mumbai":** 5B rendered a recognisably Indian street with
Devanagari-like signage on all three seeds. A14B rendered a Chinese street, an East/Southeast
Asian street, and a European boulevard. **None of the three was India.**

That refines the defect and makes it worse, not better. A14B's failure is not "renders China" —
it is **"does not render India,"** falling back to a generic non-Indian urban prior that varies by
seed. A defect with a consistent direction can be pushed against. This one has no direction.

**`VID-DEF-001`, "a young Indian woman on a rooftop in Delhi":** 5B produced an unmistakably
Indian woman on all three seeds — in a ceremonial silk sari with gold jewellery on all three.
A14B produced a woman who reads as non-Indian on all three, plus a count error on seed 1234
(two women for a singular prompt).

### ⚠ THE BASE DECISION WAS REVERSED, 2026-08-16 — read this first

The decision below picked 5B, and it answered the wrong question. It optimised for *"which base
needs the least training"*, which is the right objective for `beenga-image` — a project whose
value came from avoiding unnecessary work — and the wrong one here.

**The goal of this project is to OWN a published, India-focused model.** Against that goal:

| | `wan-2.2-5b-fast` | A14B (`t2v-fast` / `i2v-fast`) |
|---|---|---|
| Renders India out of the box | **3/3 seeds** | 0/3 |
| Managed LoRA trainer | **none exists** | fal, ~$4–5 per 1000 steps |
| Serves a custom LoRA on Replicate | **no LoRA fields at all** | `lora_weights_transformer` ×2, any URL |
| $ per second of finished video | $0.0148 | **$0.0099** |

5B is the base you **cannot train and cannot serve a LoRA on.** Choosing it made a fine-tuned
Beenga model impossible, which was the entire point of the project.

**Base = A14B.** And its measured defect — *"a Chinese street for a Mumbai prompt, 3 of 3
seeds"* — is a far better training target than anything found later in the search that assumed
5B: broad, commercially central, affects every scene shot, and unfixed in any open model. It was
found in wave 0 and then set aside as "appearance, therefore `beenga-image`'s problem", which is
true of the *pipeline* and irrelevant to *owning a model*.

The 5B findings below stay on the record. They are correct measurements of a base that is no
longer the target.

### The superseded decision

**Base = `wan-2.2-5b-fast`.**

5B's defect is *exactly* the one `beenga-image` already solved on FLUX Klein — the ceremonial
prior — and solved for **$0**, in the prompt layer, with no training. A14B's defect is a missing
prior in the weights, which is the expensive kind: it needs real Indian footage, a training
program, and a dataset that cannot be synthesised because generating Indian streets from a model
that does not know Indian streets only relearns the gap.

Picking 5B converts the main defect from a training problem into a prompting problem.

**The known cost of this choice**, recorded so it is not a surprise later: 5B has no managed LoRA
trainer on fal, and `wan-2.2-5b-fast` exposes no LoRA fields on Replicate. If 5B eventually needs
training, the rail has to be built. That is a real cost — and it is smaller than the cost of
teaching A14B what India looks like.

---

## Arm C sync quality: checked by ear, 2026-08-16 — acceptable

Every instrument in this repo is visual. Whether the mouth matches the *audio* is an audio-visual
judgement and no script here can make it, so it stayed open until a human watched the clips.

Biren reviewed `/Users/hanumanji/demo/beenga-video-os/out/armc-s2v/` and returned **"looks ok"**,
after an earlier pass of **"not great but not bad either"**. Recorded as: *acceptable, not
excellent* — a working floor, not a selling point.

That matters more than it reads, because it closes the one question that could have invalidated
arm C. Frame-by-frame review had already scored the mouth SHAPES as good; that is not the same
claim and was never evidence for it.

## Arm C defect: the mouth does not know when to stop

Found by Biren watching the first 14-second reel: *"when simply music was in the end, still mouth
movement was there."* Reproduced under control, three probes, one seed each, $0.24.

All three use the same still and the same first 2.5 seconds of sung vocal. Only the second half
and the prompt vary. `mouth_activity` measures frame-to-frame change in the mouth region
normalised by change across the whole face, so head movement is not counted as speech.

| Case | Second half of audio | Prompt says | first→second | ratio |
|---|---|---|---|---|
| `VID-SING-009` | true digital silence | "singing" | 1.875 → 1.401 | ×0.75 |
| `VID-SING-010` | instrumental only | "singing" | 1.741 → 1.711 | **×0.98** |
| `VID-SING-011` | true digital silence | "lips closed, standing still" | 1.744 → 1.438 | ×0.83 |

**The clean result is `VID-SING-010`: music drives the mouth exactly as hard as singing does.**
No reduction at all. To S2V, an instrumental passage is indistinguishable from a vocal one.

Two secondary readings, both weaker and stated as such:

- Silence reduces articulation somewhat (×0.75, ×0.83) but does not stop it. Consistent with S2V
  responding to audio *energy* rather than to vocal *content*.
- Rewriting the prompt from "singing" to "lips closed and relaxed, standing still" changed almost
  nothing (×0.98 → ×0.83 against its own control). **Prompting is not the lever here.**

### ⚠ CORRECTION after adding the control clip

The table above is raw and two of its three rows were read wrongly. `VID-SING-012` — five
seconds of total digital silence, neutral prompt — establishes that this metric's **floor is
1.196, not zero.** A generated face blinks, breathes and shifts, so the mouth region always
changes. Re-expressed as excess over that floor:

| Case | Second half | excess first→second | ratio | verdict |
|---|---|---|---|---|
| `VID-SING-009` | true silence | 0.679 → 0.205 | **×0.30** | largely stopped |
| `VID-SING-010` | **instrumental** | 0.545 → 0.515 | **×0.95** | **did not stop** |
| `VID-SING-011` | true silence, neutral prompt | 0.548 → 0.242 | **×0.44** | largely stopped |

**Silence does stop the mouth.** The earlier claim that it "kept mouthing even through absolute
silence, which bleed cannot explain" was an artefact of an uncalibrated threshold, not a finding.
Withdrawn.

**The defect is narrower and cleaner than first written: S2V cannot distinguish music from
voice.** Given an instrumental passage it articulates at 95% of the vocal rate. Given actual
silence it drops by 56–70%.

### ⚠ RESOLVED 2026-08-16 — and the fix is cheaper still: do nothing

Three seeds per condition, sharing an identical verified-loud vocal head (−15.8 dB), differing
only in the tail:

| Condition | s1234 | s77 | s2026 | verdict |
|---|---|---|---|---|
| raw Demucs stem gap (−61 dB) | ×0.26 | *(rate-limited)* | ×0.38 | **stops, 2/2** |
| gated to true silence (−91 dB) | ×1.51 | ×0.56 | ×0.00 | **variable, no pattern** |

**The raw vocal stem already stops the mouth.** Gating it adds nothing measurable, and the gated
condition's spread — a complete stop on one seed, none on another — is wider than the effect it
was supposed to produce.

So `scripts/gate-vocal.mjs` is **not needed in the pipeline.** It stays in the repo because it is
correct, tested, and cheap to reach for if a noisier stem ever turns up — but the production rule
is simply:

> **Feed S2V the Demucs vocal stem. Never the master.**

That is one line, no new dependency, and `beenga-in/lib/separate.mjs` already produces the stem.

Two honest caveats. The one lost seed means the raw condition is 2/2 rather than 3/3. And the
`mouth_activity` instrument is noisier than this project has been treating it: ratios from 0.00
to 1.51 on nominally identical audio. **Single-seed mouth-activity results should not be quoted**
— including the ones earlier in this file, which is why the section above needed correcting twice.

### The fix that was proposed and is no longer needed

Not VAD segmentation, and not a pipeline rebuild. **Feed S2V the gated vocal stem rather than the
master.** Demucs already produces that stem — `beenga-in/lib/separate.mjs` has been doing it since
2026-08-14 — and pushing its inter-phrase gaps from their measured −62 dB down to true digital
silence is a noise gate, not an architecture.

Residual caveats, stated because ×0.30 is not ×0.00: articulation is *reduced*, not eliminated,
and each of these is one seed. A held shot over a long instrumental break may still show the
mouth drifting. Worth re-testing at three seeds before relying on it.

### Limits of this measurement, which are real

The 0.6 "stopped" threshold is arbitrary and was not calibrated against a known-still clip. Frame
sampling for the visual check was every 8th frame of 77, which is coarse. Both probe clips do
settle to a closed mouth in their final frames, so "keeps moving" overstates it — the honest
claim is **"does not stop when it should, and music does not reduce it at all."** A proper
version of this needs a still-face control clip to set the floor.

### Why it matters more than a lip-sync score

Every song has an intro, an instrumental break and an outro. On a three-minute track that is tens
of seconds where the singer must not be mouthing anything. No amount of sync accuracy fixes a
performer who sings through the guitar solo.

### What the fix has to be

Not prompting — `VID-SING-011` rules that out. Not gating the stem either: the vocal stem's gaps
sit at about −62 dB of Demucs bleed, but silencing them completely still left ×0.75.

So it is architectural: **run voice-activity detection over the track, generate S2V only across
vocal-active spans, and hold on I2V or a near-still for the rest.** That is a pipeline the
project has to build regardless of which arm wins, and it is worth knowing that before choosing
an arm on lip-sync quality alone.

## The one-seed write-up that produced those hypotheses

Kept as written, because the reasoning is the point and both calls happened to hold.

---

## H1 — The two candidate bases fail in opposite directions

This is the headline, and it was not anticipated in the plan.

**`5b-fast` reproduces the FLUX Klein defect almost exactly.** Given a generic Indian prompt it
reaches for the ceremonial:

| Case | Prompt | Result |
|---|---|---|
| `VID-DEF-001` | "A young Indian woman standing on a rooftop in Delhi" | Blue-and-magenta silk sari, gold jewellery, bangles, braided hair |
| `VID-DEF-002` | "A portrait video of an Indian woman" | Red-gold brocade sari, gold jhumkas, nose ring, jasmine in hair, festival bokeh |

`beenga-image` recorded the still-image version of this as *"maroon-gold silk, gold necklace"*.
Same failure, different model, different modality. If it holds across seeds, the wave-1 prompt
layer from `beenga-image` should port with minimal change — which would make wave 1 cheap.

**`a14b` (t2v-fast) does something different and, for Beenga, worse.** It does not over-index on
ceremonial India. It under-indexes on India at all — and the default it falls back to is not
neutral:

| Case | Prompt | Result |
|---|---|---|
| `VID-DEF-004` | "A busy street in **Mumbai**" | **A Chinese street.** CJK-style signage, Chinese urban architecture, boulevard layout, e-bikes |
| `VID-MOT-005` | "Four young **Indian** friends dancing" | Reads as Western/mixed stock casting |
| `VID-DEF-006` | "An **Indian** family having dinner at home" | Western family, Western food, Scandinavian-style kitchen |

FLUX rendered the wrong *kind* of India. A14B renders the **wrong country**. For a product whose
entire premise is Indian output, those are not equivalent problems.

Worth connecting to a schema detail found earlier at $0: `t2v-fast` ships an `optimize_prompt`
option whose description is *"Translate prompt to Chinese before generation."* A Chinese default
for an under-specified scene is consistent with a heavily Chinese training corpus.

## H2 — A14B holds Indian identity for people, loses it for places and groups

H1 is not uniform, and the split looks structured rather than random.

| Holds Indian identity | Loses it |
|---|---|
| `VID-DEF-002` portrait — clearly Indian, teal sari, bindi | `VID-DEF-004` street scene — Chinese |
| `VID-DEF-003` engineer in Bengaluru — reads Indian, modern office | `VID-MOT-005` four friends — Western casting |
| `VID-DEF-005` bridal — excellent: lehenga, sherwani, safa, mandap, marigolds | `VID-DEF-006` family dinner — Western |
| `VID-CLOTH-001` sari + pallu — unmistakably Indian | `VID-MOT-001` solo dancer, casual — ambiguous |

The pattern that fits: **A14B renders Indian identity when the prompt names a person as the
subject or carries a strong garment cue, and reverts to its default prior for wide scenes,
groups, and lifestyle framings.**

If that holds, the fix is not the `beenga-image` contemporary-default rule. It is scene and
ethnicity anchoring — a rule nobody planned for, aimed at the opposite failure.

## H3 — Both models honour explicit traditional intent

`VID-DEF-005` is the guard case: it asks explicitly for a traditional red bridal lehenga, and
exists to catch a future contemporary-default rule that over-corrects.

Both passed, and A14B's was genuinely good — bride in red lehenga, groom in cream sherwani and
safa, varmala garlands, draped mandap, guests. So there is real headroom for a default rule that
stays out of the way when intent is stated.

## What could not be measured, and why

**Complexion: instrument fixed mid-run, cases still not controlled.**

The first pass reported all three complexion cases drifting darker by an amount that scaled with
their brightness — the signature of the whole shot dimming, not of complexion drifting. Raw skin
luma cannot separate those. `score-clips.py` now reports skin luma normalised against frame
exposure. After the fix:

| Case | 5B (skin/scene Δ) | A14B (skin/scene Δ) |
|---|---|---|
| `VID-ID-002` deep | −0.095 DRIFT | +0.019 ok |
| `VID-ID-003` very deep | −0.153 DRIFT | −0.010 ok |
| `VID-ID-004` wheatish | −0.191 DRIFT | −0.164 DRIFT |

These still cannot support a claim. The three cases use different subjects, scenes and lighting,
so cross-tone comparison is uncontrolled — and within A14B the wheatish case reads *darker* than
the deep case, which is either an inversion or an artefact of three unrelated scenes. The image
project solved exactly this with `sweep-complexion.mjs`: one subject template, tone as the only
variable, three seeds. **The video equivalent is required before any complexion claim.**

**Identity: CSIM is running but mostly not interpretable yet.**

The first scoring pass produced a table of confident-looking cosine numbers from 0.20 to 0.89.
Reviewing the frames showed why the low ones were low: in `VID-CLOTH-001` (0.221) the subject
simply turns away from camera by the last frame. That is pose, not identity drift.

Worse, the first implementation embedded the highest-scoring face per frame, which in the
four-person `VID-MOT-005` silently switched subject between frames — measuring which face the
detector preferred, not whether one person stayed one person. It now takes the largest face and
marks a result `interpretable: false` when the face is absent from more than 20% of frames or
multiple faces appear.

**LSE-C / LSE-D: not run.** All eight singing cases are blocked on audio assets. Nothing about
lip-sync, Hindi visemes, or arms A/B/C has been tested.

## What this changes about the plan

1. **The model choice is now the live question, and it is not the one we expected.** The plan
   assumed the 5B-vs-A14B decision would be quality against cost. It looks more like *"a known,
   probably prompt-fixable stereotype problem"* versus *"a wrong-country default."* Confirm H1
   across three seeds before committing — this decides the training rail too.
2. **Wave 1 may need a rule the image project never needed.** Scene and ethnicity anchoring is a
   different rule class from negation rewriting or contemporary defaults.
3. **A controlled complexion sweep is required**, not opportunistic scoring of three unrelated
   cases.
4. **Nothing about lip-sync has moved.** Producing the five audio assets is now the cheapest
   unblocking step in the project.

## Next, in cost order

| Step | Cost | Why |
|---|---|---|
| 3-seed confirmation of the six `VID-DEF-*` cases on both models | ~$3.60 | Turns H1 and H2 from anecdote into finding. Decides the base model. |
| Record five audio assets, run the arm A/B/C bake-off | ~$10–20 | Unblocks the entire lip-sync half of the project |
| Controlled complexion sweep, video version of `sweep-complexion.mjs` | ~$4 | The only way to make the complexion axis measurable |
| Wave 1 prompt layer, once the defect is known | $10–20 | Not before H1 is settled — the rule differs by base model |
