# Raw material — Beenga Video OS

Facts, numbers and findings. Not a post. Written to be combined with the equivalent
from `beenga-image` and turned into a story elsewhere.

Everything below is measured unless it says otherwise. Nothing is rounded in our favour.

---

## The one-line version

Built a pipeline that turns one song into a three-minute lip-synced Indian music video,
on Apache-2.0 models only, for **$11.20 of total compute**. Along the way, measurement
overturned four of our own conclusions — including which base model to use.

## Hard numbers

- **$11.20** total spend, everything included
- **165 video clips** generated across 18 benchmark runs
- **175.7 seconds** — the finished video, 36 of 36 shots, one command
- **42-case benchmark** written before any model was chosen
- **4 songs** generated and stem-separated (Lyria 3) at $0.10 each
- **6 model cards** archived at pinned revisions as licence evidence
- 3-minute video costs **$2.84 at 480p**, ~$6 at 720p

## The finding that decided the project

Asked for **"a busy street in Mumbai"**, Wan 2.2 A14B returned:

- seed 1234 — a Chinese street
- seed 77 — a Southeast Asian street
- seed 2026 — a European boulevard

**None of the three was India. 0 of 3.**

It is not that the model renders the *wrong kind* of India — the way image models tend to
default to ceremonial silk and gold. It falls back to a *different* non-Indian prior each
seed. That matters practically: a defect with a consistent direction can be pushed against
with prompting. One with no direction cannot.

The 5B variant, asked the same thing, produced a recognisably Indian street with
Devanagari-like signage on **3 of 3** seeds.

## Four times measurement overturned us

**1. The base model.** Chose 5B because it renders India correctly out of the box. Then
realised that answered the wrong question: the goal was to *own* a fine-tuned model, and 5B
is the variant with no managed trainer and no LoRA hook on the serving rail. Reversed to
A14B — whose India defect is exactly what training would fix. Then reversed *again* when
self-hosting entered the picture, because that removed the constraint that made 5B
untenable. The reversals are in the repo, not edited out.

**2. The lip-sync licence.** Every summary says LatentSync is Apache-2.0. That is the
**code**. The published checkpoints are tagged `openrail++`. MuseTalk is the same shape from
the other direction: MIT code, `creativeml-openrail-m` weights. Both permit commercial use;
neither permits *free redistribution*, which was the requirement. Found by querying the
Hugging Face API rather than reading blog posts. Two claims the ecosystem repeats, disproved
in about five seconds.

**3. The lip-sync defect, and the fix that turned out to be unnecessary.** Wan's
speech-to-video model **cannot distinguish music from voice** — fed an instrumental
passage it articulates at **95%** of the vocal rate, so the singer mouths through the intro,
the break and the outro. First proposed a two-pipeline architecture with voice-activity
detection. Then narrowed it to a noise gate, built the gate, measured it — and found the
plain separated vocal stem already solved it. The gate was retired. The fix is one line:
*feed it the vocal stem, never the master.*

**4. "Three minutes" needed three strategies, not one.**
- Chaining each clip off the previous: seamless joins, but the singer becomes a
  **different person by about 20 seconds** (identity 0.859 → 0.518)
- Anchoring every clip to one reference: identity perfectly flat, but every seam is a
  visible cut
- **Re-anchoring every second clip: both.** Identity bounded — trend −0.029 over three
  minutes — with joins a fifth the size of the anchored version

## Six times an instrument lied

The most transferable lesson. Each of these produced a number that looked like a result:

1. A mouth-movement threshold with **no floor clip** — it flagged its own control as failing
2. `ffmpeg -v error` **suppressing the very output being parsed** — returned "zero silences"
   for every input, which reads as a measurement and is nothing of the kind
3. A model schema advertising **121 frames** while writing **81** — so two models were
   compared at 3.4s versus 5.1s while a code comment claimed they were matched
4. Reading **stdout** where ffmpeg writes **stderr**
5. `-sseof` silently writing nothing on one model's output and working on another's,
   exiting 0 both times — crashed a render six shots after the actual fault
6. Face-similarity scoring calling a singer with **closed eyes mid-note** a different person

Every one was caught by looking at the artefact instead of trusting the number. **Two of
the six were caught by a human watching output that had already been reviewed and passed.**

## What is Apache-2.0 and what only looks it

| Component | Reality |
|---|---|
| Wan 2.2 (all variants) | Apache-2.0, confirmed on the cards |
| InfiniteTalk, EchoMimicV3, MultiTalk | Apache-2.0 |
| LatentSync | **code** Apache-2.0, **weights** `openrail++` |
| MuseTalk | **code** MIT, **weights** `creativeml-openrail-m` |
| HunyuanVideo 1.5 | Tencent Community licence, territory carve-outs |
| LTX-2 | "Apache" but revenue-tiered above ~$10M ARR |

None of these repos ships a `LICENSE` file. The licence is declared only in the YAML header
of an editable `README.md` — so the evidence of a grant is the card *as it read at a specific
commit*. Archived accordingly.

## The strategic turn

Apache-2.0 permits forking everything — weights, inference code, training code. So rather
than re-evaluating base models every six months, vendor the stack: fork the code to GitHub,
mirror the weights, and build against copies you control. A dependency becomes an asset.

Worth being precise about what that does and does not buy: the Apache grant is already
irrevocable, so vendoring protects **access**, not rights.

## What was NOT built

- **No fine-tuned model.** The pipeline is real; the owned weights are not, and it is
  blocked on one thing: **real footage of contemporary India.** Synthetic data cannot fix
  this — a model that doesn't know Indian streets cannot teach itself Indian streets.
- Roughly **$4–5 of the $11.20 was spent on work later superseded**, mostly benchmarking a
  base model that was subsequently reversed.

## Links

- Pipeline, benchmark, findings: https://github.com/Beenga/beenga-video-os
- Sibling image project: https://github.com/Beenga/beenga-image
- Live image model: https://replicate.com/beenga/beenga-image-1

## Angles worth building the story around

1. **Measure before you collect.** The image project's original plan was ~69 concept buckets
   and 3,000–5,000 training images. Measuring first reduced it to two defects, then one, at
   a total spend of $0.11. The video project reached the same shape: most of what would have
   been trained did not need training.
2. **The ecosystem repeats licence claims that are wrong**, and it takes one API call to
   check. Two of them here.
3. **Instruments lie more often than models do.** Six times in one project.
4. **A wrong turn documented is worth more than a clean narrative.** Both repos keep their
   reversals in the commit history on purpose.
