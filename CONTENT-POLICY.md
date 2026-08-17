# Content policy

Beenga Video OS generates video of people. This states what it is built to do, what it is not,
and — more usefully — where the *enforcement* actually sits, because a policy with no mechanism
behind it is decoration.

Set 2026-08-16.

## What this is for

Contemporary Indian video: music video, performance, lifestyle, devotional, advertising. The
register is mainstream commercial — the kind of thing that plays on television and streaming
platforms in India.

| | |
|---|---|
| Attractive adult woman or man | fine |
| Sari showing waist or midriff | fine |
| Bikini or swimwear | fine |
| Glamorous or sexy fashion photography | fine |
| Low-cut dress, cleavage | fine |
| Romantic adult couple | fine |
| Sensual but clothed poses | fine |

None of that is edgy. It is what Indian music video has looked like for forty years, and a model
that cannot render a sari showing a midriff is not usable for the purpose.

## What this is not for

| | |
|---|---|
| Explicit nudity | not generated — also against Replicate's terms, where this is served |
| Explicit sexual activity | not generated |
| Fetish or pornographic material | not generated |
| **Sexualised depiction of anyone who reads as a minor** | **absolutely not, under any framing** |
| **Sexual or intimate depiction of a real, identifiable person** | **absolutely not** |

The last two are different in kind from the others. The first three are a product decision and a
platform-terms question. Those two are not negotiable and no business reason changes them.

## Where enforcement actually is

Three layers, and it is worth being precise about which are real and which are aspirational.

**1. Upstream safety checkers — real, and now pinned.**
`wan-2.2-i2v-fast` and `wan-2.2-t2v-fast` expose `disable_safety_checker`, defaulting to `False`
(checker on). This project never enables it, and `cog/predict.py` now sets it to `False`
explicitly rather than relying on a default that is upstream's to change.

⚠ **`wan-2.2-s2v` has no safety field at all.** The lip-sync path is unchecked at the model level.
That is a real gap and it is stated here rather than glossed.

**2. Age specificity in the benchmark — real, and it caught two cases.**
Every benchmark case featuring a person states an explicit adult age. This is not pedantry: asked
for a "young" person with no age, a generative model will sometimes produce someone who reads as
a minor. Two cases said "young" with no age (`VID-MOT-005`, `VID-DEF-001`) and were rewritten on
2026-08-16. **The audit that found them is one regex and should be re-run whenever cases are
added.**

**3. The `reference_image` input — NOT enforced, and this is the honest gap.**

`reference_image` accepts any photograph. Combined with `say`, the product's function is
literally *"make this face speak these words."* That is a deepfake tool when the face belongs to
a real person who did not consent.

Nothing in the pipeline detects this. There is no identity check, no consent mechanism, no
watermark. The mitigations that exist are weak ones — the model page says what the input is for,
and the platform's own terms apply.

**If this ships more widely than a demo, that gap needs closing** — provenance metadata such as
C2PA on outputs, at minimum. It is listed here as an open risk rather than a solved problem,
because it is not solved.

## For anyone forking this

The pipeline is Apache-2.0 and the licence grants no power to restrict what you do with it. This
document is what *Beenga* does, stated so the intent is legible. The two non-negotiables above
are non-negotiable for good reasons and should stay that way in any fork.
