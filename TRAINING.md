# Beenga India LoRA — dataset spec and training plan

Everything except the footage is ready. This is the spec for the footage, written so that the
moment it exists, training starts the same day.

**Target:** `Wan-AI/Wan2.2-I2V-A14B` (served as `wan-video/wan-2.2-i2v-fast`).
**Ships as:** two `.safetensors` adapters, Apache-2.0, on Hugging Face under `beenga/`.
**Proven:** the serving chain was tested end to end on 2026-08-16 with a third-party LoRA — see
the README. Nothing about the delivery path is speculative.

---

## What the LoRA has to fix

One defect, measured at three seeds in wave 0, and it is the most valuable thing found in this
project:

> **A14B does not render India.** Asked for "a busy street in Mumbai" it produced a Chinese
> street, a Southeast Asian street and a European boulevard across seeds 1234 / 77 / 2026. Asked
> for "a young Indian woman on a rooftop in Delhi" it produced a woman who reads as non-Indian on
> all three. **0 of 3.**

It is not that A14B renders the *wrong kind* of India, the way FLUX did on the image side. It
falls back to a **different non-Indian prior each seed**, which is why prompting cannot reach it:
there is no consistent direction to push against.

**The "before" number already exists.** `out/base-a14b/`, `out/def-a14b-s77/`,
`out/def-a14b-s2026/` hold the baseline at three seeds. So "0/3 → n/3 on `VID-DEF-*`" is a
publishable claim the day training finishes, measured on a suite written before the model existed.

## Why the data must be real

`beenga-image` recorded the rule that applies here:

> Training "deep complexion" on images produced by a model that lightens complexion only
> relearns the bias.

Generating Indian street clips from a model that renders Chinese streets teaches it nothing. This
is the one place in the project where synthetic data is categorically unusable, and it is why
footage is the blocker rather than an optimisation.

(Contrast `VID-DANCE-001`, deferred: there the base produces *no* bharatanatyam technique at all
rather than subtly wrong technique, so synthetic augmentation would have been less poisoned. The
scene defect is the opposite case.)

## The dataset

**Size: 50–150 clips.** Below ~50 the LoRA overfits to specific scenes; above ~150 the return
flattens for a style/domain adapter of this kind. Start at 60 and add if the benchmark does not
move.

**Each clip:** 3–6 seconds, ≥480p, 16:9, no burned-in text, no watermark, no hard cuts inside the
clip. A cut mid-clip teaches the model to cut.

**Coverage — weight toward what the benchmark measures**, because that is what gets scored:

| Bucket | Clips | Why |
|---|---|---|
| Contemporary Indian streets | 15–20 | `VID-DEF-004`, the sharpest failure |
| Indian homes and interiors | 10–15 | `VID-DEF-006` |
| Indian people, medium and close | 10–15 | `VID-DEF-001`, `VID-DEF-002` — ordinary dress, not ceremonial |
| Workplaces, campuses, transit | 8–10 | `VID-DEF-003` |
| Groups and families | 8–10 | `VID-MOT-005`, where casting drifted Western |
| Festival and wedding | 5–8 | Keeps the traditional register intact — `VID-DEF-005` must not regress |

**Deliberately NOT in the dataset:** classical dance (deferred), anything ceremonial-heavy beyond
the last bucket, and stock footage that already looks like a stock library. The defect is that the
model's India is generic and foreign; feeding it generic footage will not fix that.

**Captions:** one line per clip, plain description, present tense, naming the place and the
everyday register — *"a busy street in Mumbai in the afternoon, traffic and pedestrians,
present-day"*. No trigger word. A style/domain LoRA of this kind should shift the default, not
hide behind a keyword the user has to know.

## Sourcing — three routes, honestly priced

| Route | Cost | Speed | Risk |
|---|---|---|---|
| **CC / public-domain harvest** | $0 | days | Licence hygiene per clip; CC-BY-SA is share-alike and would infect an Apache release. Quality varies. |
| **Licensed stock** | $50–500+ | hours | Most stock licences **forbid using the footage as AI training data** — read the specific licence, do not assume |
| **Shoot it** | crew + time | weeks | Cleanest rights story by far, and the footage is unambiguously contemporary India because you chose the frame |

⚠ **The stock route is the trap.** A standard stock licence permits use *in* a production, not
training a model on it. Several major libraries prohibit it explicitly. Buying 100 clips and
training on them could make the resulting weights unpublishable — which would defeat the entire
Apache-2.0 discipline this project has held from the first day.

**Recommendation: CC harvest for the first run, shoot for the second.** The first LoRA only has to
prove the benchmark moves. `beenga-image/scripts/harvest-commons.mjs` is the existing pattern for
the sourcing and licence-recording half of this; it needs adapting from stills to clips.

Record per clip: source URL, licence, author, date retrieved — the same discipline as
`PROVENANCE.md`. **Publish the manifest, never the media.**

## Training

**Rail:** fal `wan-22-trainer` (`i2v-a14b`), $0.005/step, minimum 100 steps.

- 1000 steps ≈ **$5/run**. Budget 3–4 runs → **$15–20**.
- ⚠ The i2v trainer **rejects image-only datasets** — it needs video. The t2v trainer accepts
  mixed; the i2v one does not.
- **Output is two adapters**, high-noise and low-noise, because A14B is mixture-of-experts. Every
  public Wan 2.2 LoRA ships both. Plan the HF repo layout for two files.

**Then measure, do not eyeball:**

```bash
node scripts/run-benchmark.mjs --model wan-video/wan-2.2-i2v-fast --tag lora-v1 \
  --only VID-DEF-001,VID-DEF-002,VID-DEF-003,VID-DEF-004,VID-DEF-005,VID-DEF-006 \
  --seed 1234   # then 77, then 2026
```

with `--lora-high` / `--lora-low` wired through, against `out/base-a14b/` and the two def-a14b
runs. Three seeds, same cases, same seeds. **`VID-DEF-005` is the guard**: it asks explicitly for
a traditional bridal scene and passes today. A LoRA that pushes everything contemporary and breaks
it has traded one bias for another.

## Definition of done

1. `VID-DEF-*` moves from 0/3 to a stated number, at three seeds.
2. `VID-DEF-005` does not regress.
3. Two `.safetensors` published on HF under `beenga/`, Apache-2.0, with a model card carrying the
   before/after and the dataset manifest.
4. `scripts/make-music-video.mjs --lora-high … --lora-low …` renders a three-minute video with it.

Step 4 already works. Steps 1–3 are waiting on step zero, which is the footage.
