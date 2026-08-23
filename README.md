# Beenga Video OS

A video-generation and lip-sync pipeline built for Indian users, by [Beenga](https://beenga.com).

Sibling to [`beenga-image`](https://github.com/Beenga/beenga-image), and built on the same
premise: not new weights, but a measured, versioned, licence-audited pipeline around
Apache-2.0 base models — with a benchmark that says whether any of it worked.

## What it does today

One song in, one lip-synced music video out, up to three minutes:

```bash
node scripts/make-music-video.mjs --song /path/to/song-dir
```

The song directory needs a `master.mp3` and a separated `guide-vocal.mp3`. The pipeline plans
shots against the vocal, routes each one, generates, stitches, and muxes the master back over
the top.

**Verified end to end:** 175.7 seconds, 36 of 36 shots, identity flat across the whole run.

Every decision inside it is a measured result rather than a default, and each one names the
benchmark case that produced it:

| Decision | Evidence |
|---|---|
| Route each shot to `s2v` or `i2v` by vocal activity | S2V drives motion from audio, i2v from a prompt — neither can do the other's job |
| Feed S2V the **vocal stem**, never the master | Given an instrumental passage, S2V articulates at 95% of the vocal rate (`VID-SING-010`) |
| `reanchor 2` chaining | Over 36 clips: pure chaining loses the singer's identity by ~20s; pure anchoring makes every seam a cut |
| Seams land on section boundaries | Only the reset seams are visible, and a chorus boundary is where a cut belongs |
| `interpolate_output: false` | It is on by default on one model and off on another, and it contaminates every temporal measurement |

**Status: pipeline deployed, model not yet trained.** The LoRA slot is wired
(`--lora-high` / `--lora-low`) and the loading mechanism is proven end to end against a
third-party adapter. What it waits on is training footage — see [`TRAINING.md`](TRAINING.md).

Prices and licences were checked on 2026-08-16 and should be re-checked before money moves.

---

## Why this exists

`beenga-image` started from a specification of ~69 concept buckets and 3,000–5,000 training
images. Measuring first reduced that to two real defects, and one of those then collapsed into
a prompt rule that cost $0. Total spend to date: **~$0.11.**

Three of that repo's four commits are corrections of earlier conclusions. That is the method,
not an embarrassment: **measure before you collect.**

This project applies the same method to video, where it matters more, because a video sample
costs $0.05–$1.00 against $0.001 for an image. The discipline that saved a few dollars there
saves a few thousand here.

## The ownership path, proven end to end 2026-08-16

The goal is a published, Apache-2.0, India-focused model that Beenga owns. Before spending
anything on training, the serving chain was tested with somebody else's LoRA — because
discovering it was broken *after* a training run would be the expensive way to learn it.

**Test:** loaded `starsfriday/Wan2.2-I2V-KungFu` (Apache-2.0) into `wan-video/wan-2.2-i2v-fast`
via `lora_weights_transformer` and `lora_weights_transformer_2`, pointing directly at HF
`.safetensors` URLs. Same reference still and seed as a no-LoRA render.

**Result: works, and works visibly.** Identity and setting held from the still; the motion changed
completely — raised fists, energetic posture, martial-arts vocabulary that is nowhere in the
prompt. Cost: $0.05.

So the whole chain is de-risked:

```
train on fal  →  publish .safetensors on Hugging Face  →  load by URL on Replicate  →  video
```

**Packaging note, confirmed by inspection:** every public Wan 2.2 LoRA ships a **high-noise and a
low-noise file**, because A14B is mixture-of-experts with two transformers. A Beenga LoRA is
**two adapters, not one** — that shapes the fal trainer output, the HF repo layout and the model
card.

### ⚠ Replicate credit is throttling this account

The no-LoRA control in that test failed with:

> *"Your rate limit for creating predictions is reduced to 6 requests per minute with a burst of
> 1 requests while you have less than $5.0 in credit."*

That is the cause of every HTTP 429 in this project, including the one that lost 16 of 23 clips
in the first wave-0 run and sent me rewriting the runner for concurrency I was never hitting.
**It is a credit threshold, not a concurrency limit.** Topping the account above $5 restores
normal rate limits; the retry logic in `scripts/run-benchmark.mjs` is still worth having, but it
has been compensating for a billing state rather than a real cap.

## Scope: what this repo owns, and what it does not

Decided 2026-08-15, after wave 1, and it is an architectural consequence rather than a
preference.

Production shots start from a reference still and run through i2v or s2v. **So the still decides
who the person is and what they are wearing, and the video model decides what happens after
frame 1.**

| Defect class | Owner | Why |
|---|---|---|
| Ceremonial default, garment, complexion, ethnicity | **`beenga-image`** | Fixed by the still. A sample there costs $0.001 against $0.05 here. |
| Motion integrity, cloth and hair dynamics, attribute decay across a clip, lip-sync, long-form joins | **`beenga-video-os`** | No still-image equivalent exists. Only this project can measure them. |

Wave 1 measured the ceremonial default and improved it — and that work belongs in the other
repo, run on stills. It is not repeated here. The `VID-DEF-*` cases stay in the suite as t2v
regression probes and are marked `owner: beenga-image`; 9 of 36 cases carry that flag.

The practical consequence: **wave 1.1 (stacking the dress instruction) is cancelled in this
repo.** It is the right experiment, on the wrong subject, at 50x the cost per sample.

## The method, inherited

1. Write a machine-readable benchmark of *specified* failures first — `must_obey` cases where
   the prompt names an attribute, `default_behavior` cases where it deliberately does not.
2. Run it raw against an Apache-2.0 base. That is the baseline every later wave scores against.
3. Separate **prompt-fixable** from **weights-level** defects before training anything.
4. Instrument the claim wherever an instrument is cheap. Quote orderings, not absolutes, and
   write down what the instrument cannot see.
5. Train only the residue. Include regression probes that the change must *not* affect.
6. Audit the licence chain of every component, including the ones nobody reads.

## Base model: Wan 2.2

Checked against the model cards, not against listicles.

| Candidate | Licence | Verdict |
|---|---|---|
| **Wan 2.2** — TI2V-5B, T2V-A14B, I2V-A14B, S2V-14B, Animate-2-14B | **Apache-2.0**, stated on the cards | **target** |
| HunyuanVideo 1.5 | Tencent Community licence — commercial review, territory carve-outs | rejected |
| LTX-2 | "Apache" but revenue-tiered above ~$10M ARR | rejected |

There is no open-weights Wan 2.5 or 2.7. The `Wan-AI` org tops out at the 2.2 family; the
newest drop is `Wan2.2-Animate-2-14B` (Apache-2.0, ~2026-08-08).

Wave 0 benchmarks **TI2V-5B and T2V-A14B side by side** rather than picking on reputation. One
consequence to go in with eyes open: fal's managed LoRA trainers are **A14B-only**. Choosing 5B
means building the training rail ourselves on RunPod, exactly as we did for Klein.

## What reading the API told us before spending anything

The runner resolves each model's OpenAPI schema rather than hardcoding inputs, because the
Wan variants are not one interface. Doing that surfaced four things at a cost of $0.

**1. Two of the defaults would have corrupted wave 0.**

| Field | Default | Why it is off in the benchmark |
|---|---|---|
| `interpolate_output` | **true** on `t2v-fast`, false on `i2v-fast` | Interpolates the clip to 30fps with ffmpeg. Makes t2v and i2v incomparable, and contaminates every temporal measurement in this suite — scoring motion coherence on synthesised in-between frames measures ffmpeg, not Wan. |
| `optimize_prompt` | false on `t2v-fast` | Translates the prompt to Chinese before generation. An unversioned prompt rewriter between the benchmark and the result. Off by default already; pinned explicitly so it stays that way. |

The first one is the reason to read schemas instead of trusting a default. A wave-0 baseline run
with interpolation on would have produced numbers that looked fine and meant nothing.

That `optimize_prompt` exists at all is worth noting for a project about Indian output: the
model's own prompt path has a translate-to-Chinese option. Whether that helps or hurts an Indian
prompt is a real experiment, deliberately out of scope for wave 0.

**2. Frame config is not shared, so we do not force it.**

`wan-2.2-5b-fast` is natively 121 frames at 24fps (≈5.04s); `t2v-fast` and `i2v-fast` are 81 at
16fps (≈5.06s). Both land at ~5 seconds, so leaving each on its default compares equal durations
at each model's native rate. Forcing one number across both would run at least one off-config and
confound the model comparison wave 0 exists to make. Whatever each used is recorded in
`runs.json`.

**3. Replicate serves custom Wan 2.2 LoRAs — correcting an earlier assumption.**

`t2v-fast` and `i2v-fast` both accept `lora_weights_transformer` and
`lora_weights_transformer_2` from arbitrary `.safetensors` URLs, with independent scales. So
Replicate is a serving rail for Beenga LoRAs, not just for stock models, and a LoRA published on
Hugging Face can be loaded straight from its URL. The earlier note that fal was the managed route
applies to **training**, not serving.

Note the two slots: A14B is a mixture-of-experts with separate high-noise and low-noise
transformers, so an A14B LoRA is **two adapters, not one**. Budget and packaging should assume
that. `5b-fast` exposes no LoRA fields at all — another cost of choosing 5B.

**4. All four planned endpoints exist and are reachable**, with required fields as expected:
`t2v-fast` needs `prompt`; `i2v-fast` needs `prompt` + `image`; `s2v` needs `prompt` + `image` +
`audio`.

## Architecture

Specialised models, replaceable individually, rather than one model asked to do everything.

```
                    Apache-2.0 image model
                             │
                             ▼
                     Wan 2.2 I2V  ──────────────┐
                             │                  │
                             ▼                  │
              LatentSync 1.6  ◄── WAV/MP3       │  ARM C bypasses both stages:
                  or MuseTalk 1.5               │  Wan 2.2 S2V-14B takes
                             │                  │  image + audio directly
                             ▼                  │
                          FFmpeg  ◄─────────────┘
                       mux + stitch
                             │
                             ▼
                     lip-synced clip
```

Post-hoc lip-sync is the right default over asking Wan to "sing this song": Wan has no access
to the phoneme timing of the final master, so it produces plausible mouth motion rather than
*our* mouth motion.

But that chain has a structural problem worth measuring, not assuming away:

> Wan I2V generates head and body motion with **no relationship to the audio**. The lip-sync
> stage then repairs only the mouth. In a music video the singer's body will not be on the
> beat — and off-beat body motion reads as wrong faster than a slightly soft viseme does.

### Arms A and B are excluded by policy, not by measurement

The requirement, stated 2026-08-15: **best quality, Apache-only, no licence locking, free to
distribute, upgradable forever.**

That decides the lip-sync stage before any benchmark runs. LatentSync's published checkpoints are
`openrail++` and MuseTalk's are `creativeml-openrail-m`. Both permit commercial use; neither
permits what is being asked for, because OpenRAIL propagates behavioural restrictions to every
downstream recipient and forecloses ever describing the pipeline as Apache-2.0.

So they are dropped. Not tested and rejected — **ruled out by a constraint that is not a
measurement question.** Recorded here so nobody re-adds them later on a quality argument.

### The Apache-only arm set

Every licence below verified through the Hugging Face API on 2026-08-15, not from summaries —
the ecosystem repeats "LatentSync is Apache-2.0" constantly, and its weights are not.

| Arm | Model | Licence | Length | Managed endpoint | Bet |
|---|---|---|---|---|---|
| **C** | `Wan-AI/Wan2.2-S2V-14B` | apache-2.0 | ~5s clips | **Replicate, today** | Same family as the base. Cheapest to test. Long-form needs stitching. |
| **D** | `MeiGen-AI/InfiniteTalk` | apache-2.0 | **unbounded** | none — self-host | Infinite-length audio-driven video. Solves the stitching problem outright. 30.6k downloads/30d, the most-used of these. |
| **E** | `BadToBest/EchoMimicV3` | apache-2.0 | — | none — self-host | Half and full body on 12GB VRAM, so cheapest to self-host. Unproven: 0 downloads/30d. |
| **F** | `Wan-AI/Wan2.2-Animate-2-14B` | apache-2.0 | — | none — self-host | Only if driving a performance from a reference video rather than from audio alone. |

`MeiGen-AI/MeiGen-MultiTalk` (apache-2.0) and `vinthony/SadTalker` (mit) are also clean, kept on
the list but not prioritised — MultiTalk is InfiniteTalk's predecessor, SadTalker is older and
lower fidelity.

**Order of work: C first, D as the serious contender.** C is on Replicate and can be benchmarked
today for a few dollars. D is the better architectural fit for a three-minute music video — a
song stitched from ~36 five-second clips makes cross-clip identity drift the dominant defect, and
unbounded generation removes the failure mode rather than mitigating it. D costs a RunPod session
to evaluate, which is worth spending only once C has set a quality floor.

### The residual risk Apache does not cover

Apache-2.0 governs the *weights*, not the *training data*. Wan's corpus is undocumented, as is
InfiniteTalk's. That is not a licence risk from the publisher — it is third-party claim exposure,
and it applies to essentially every open video model. LTX-2 markets licensed training data for
exactly this reason and is excluded here anyway for being revenue-tiered. Worth knowing that
"Apache-2.0 end to end" is a statement about redistribution rights, not about provenance.

## Where the licence chain breaks

Every summary says "LatentSync is Apache-2.0, safe for commercial." That is the **code**. The
published checkpoints are tagged **`openrail++`**, because the model is Stable-Diffusion-derived
and the VAE carries its licence along.

MuseTalk is worse than the ecosystem says, and the reason is not the one we first assumed. The
GitHub *code* repo is MIT. The Hugging Face *weights* repo is tagged
**`creativeml-openrail-m`**. We initially attributed MuseTalk's encumbrance to the
`sd-vae-ft-mse` VAE it pulls in — that was wrong; the VAE is tagged **`mit`** and is clean. The
restriction comes from MuseTalk's own card. Its bundled test data is separately
non-commercial-research-only.

Both corrections came from querying the Hub API instead of reading summaries. See
`PROVENANCE.md`. This is the second time on this project a licence has differed from the one
everybody repeats; assume a third.

OpenRAIL permits commercial use. It is not a blocker. It is a **propagating behavioural-use
restriction**, which means:

- Serving generated video to users — fine. Output is not encumbered.
- Publishing this pipeline as self-hostable, or shipping a fine-tuned LatentSync —
  **cannot be described as Apache-2.0**, and the OpenRAIL terms must be passed downstream.

This is the same class of mistake as the FLUX 4B-vs-9B trap recorded in `beenga-image`: a
component whose licence differs from the licence everyone assumes it has, discovered after the
work is built on it rather than before. Written down here first, deliberately.

Arm C is the only chain that stays Apache end to end. That is a point in its favour, but it does
not win the benchmark by itself.

**FFmpeg** is LGPL-2.1, or GPL once x264/x265 are built in. If we ship a self-hostable pipeline,
take the LGPL build and link dynamically.

## The Hindi assumption, which is half right

The working assumption has been that language is not the problem, because these models consume
audio features and Whisper is multilingual.

The audio encoder is genuinely multilingual. The **audio→viseme mapping is not.** It was
supervised on HDTF and VoxCeleb2, which are overwhelmingly English, and LatentSync's SyncNet
supervision is English-trained as well. The model learned *English lip shapes* for given audio
features.

Hindi carries visemes that English underweights — retroflex stops, aspirated /bʱ/ /dʱ/ — plus
mid-line Hinglish code-switching. Transfer is plausible. It is not established, and it is
exactly the kind of confident premise this project's history keeps overturning. It goes in the
benchmark as a case, not in the design as a given.

Sharpest single probe: **a sustained vowel held 1–2 seconds.** Speech-trained models almost
never see a mouth held in one open shape for 40 frames. Singing exposes what dialogue hides —
sustained vowels, rapid lyric lines, head movement, teeth and tongue visibility, musical timing.

## Instruments

`beenga-image` scored complexion with median Rec.709 luma rather than by eye. Lip-sync has
standard instruments, so this axis should not be eyeballed either.

| Metric | Measures |
|---|---|
| **LSE-C / LSE-D** (SyncNet confidence / distance) | sync accuracy |
| **CSIM** (ArcFace cosine, frame to frame) | did the singer stay the same person |
| **CSIM across clip boundaries** | identity drift when stitching a full song from 5–10s clips |

Same caveat as `score-complexion.py`, and it bites harder here: **SyncNet is itself
English-trained (LRS2).** LSE-C on Hindi singing is a biased instrument. Use it for *ordering*
between arms, never quote it as an absolute, and validate against human scoring on a sample.

Cross-clip CSIM is listed deliberately. Identity drift *within* a clip is the metric everyone
reports; drift *between* stitched clips is the one that ruins a music video.

## Benchmark axes

Four motion axes plus a singing set:

| Axis | What it probes |
|---|---|
| **Motion & dance realism** | casual dancing vs classical stereotype; natural hand movement; limb integrity across frames. Direct sequel to `IND-DANCE-*`. |
| **Cloth & hair dynamics** | pallu, dupatta, kurti drape, long hair in motion — where video models smear or freeze fabric. No image-side equivalent. |
| **Temporal identity & complexion** | does the face stay one person across 5s, and does a requested deep complexion drift lighter frame to frame. |
| **Contemporary India defaults** | does a generic Indian video prompt default to ceremonial/rural/weathered, and is it prompt-fixable as it was for images. |
| **Singing (Hindi/Hinglish)** | sustained vowels, rapid lyric lines, code-switching, head movement under sync. |

Proposed size: **24 motion cases** (6 per axis) plus **8 singing cases**. Video is noisier per
seed than images, so single-seed results are worth less here and the multi-seed budget below is
deliberate.

## Budget

Rates verified 2026-08-15. Quantities are estimates.

### ⚠ Cost per second, corrected 2026-08-16

Prices are per *video*, and the videos are not the same length. Measured from the files rather
than read off the schema:

| Model | Price/clip | **Measured** clip length | **$ per second of video** |
|---|---|---|---|
| `wan-2.2-t2v-fast` | $0.05 | 5.062s | **$0.0099** |
| `wan-2.2-i2v-fast` | $0.05 | 5.062s | **$0.0099** |
| `wan-2.2-5b-fast` | $0.05 | **3.375s** | **$0.0148** |
| `wan-2.2-s2v` | ~$0.09 | 4.812s | ~$0.0187 |

**5B is ~50% dearer per second of finished video than t2v-fast**, not cheaper — the opposite of
what the per-clip price implies, and the opposite of what this README said before. Its schema
advertises 121 frames at 24fps (5.04s) and it writes 81 (3.375s). Only 5B disagrees with itself.

Consequences: a three-minute video needs **36 clips on i2v-fast but 54 on 5B**; and the wave-0
base comparison ran 3.4s of 5B against 5.1s of A14B, so any *temporal* claim across those two is
invalid. The base-model decision itself stands — 1.7 seconds does not explain an Indian street
versus a Chinese one.

| Rail | Rate |
|---|---|
| Replicate `wan-2.2-t2v-fast` / `i2v-fast` | $0.05/video @480p, $0.10 @720p (~30s/gen) |
| Replicate unoptimised i2v | $0.40 @480p, $1.00 @720p |
| fal Wan 2.2 A14B | $0.04/video-sec @480p, $0.06 @580p, $0.08 @720p |
| fal `wan-22-trainer` | $0.004/step (t2v-a14b), $0.005/step (i2v-a14b) → $4–5 per 1000 steps |
| RunPod (community) | 4090 24GB $0.34/hr · A6000 48GB $0.33 · L40S $0.79 · A100 80GB $1.19 · H100 $1.99 |

| Wave | Scope | Cost |
|---|---|---|
| 0 | Benchmark + baseline, both 5B and A14B, 1 seed + 3-seed confirm on default-behaviour cases (~80 clips @480p) | $4–8 |
| 0b | 720p quality reference, 10-case subset, fal A14B | $4 |
| 0c | Lip-sync bake-off — 3 arms × 8 singing cases, on Replicate | $10–20 |
| 1 | Prompt layer + 2 full re-runs + multi-seed on what moved (~130 clips) | $10–20 |
| 2 | First LoRA on the residue — 3–4 runs + A/B with regression probes | $25–60 |
| — | RunPod persistent volume (A14B weights ~70GB; without it you re-download every session) | ~$15 |
| — | Weight mirror, object storage | ~$5 |
| — | Contingency 30% | ~$35 |

**Total to a shippable 1.0: ~$110–210.** Lean path — everything 480p on Replicate fast
variants, fal's managed trainer, no GPU rental — puts **waves 0+1 at ~$25**.

Not included: **training footage.** Synthetic clips from the base model relearn the base's bias,
which is the finding already recorded for complexion in `beenga-image`. CC harvest is $0;
licensed stock is $0–$500+ and is a business decision, not an engineering estimate.

Unlike waves 0–1 for images, **the prompt layer here is not free.** The fix is free; proving it
costs $10–20 in re-runs.

## What happens if Wan stops being Apache-2.0

Short answer: **the grant already received cannot be revoked, and most of what we build is not
weight-coupled anyway.** The real exposure is availability, not licensing, and it costs about
$5/month to close.

### The licence grant is irrevocable

Apache-2.0 §2 grants a *"perpetual, worldwide, non-exclusive, no-charge, royalty-free,
**irrevocable** copyright license"*. Alibaba can license Wan 3.0 however they like. They cannot
retroactively un-license the Wan 2.2 weights already published under Apache-2.0.

The only termination trigger is §3: the *patent* grant ends if **we** initiate patent litigation
alleging the Work infringes. That is entirely within our control.

### What is actually at risk

| Risk | Real? | Mitigation |
|---|---|---|
| Upstream relicenses existing 2.2 weights | **No** — legally foreclosed by §2 | none needed |
| Repo deleted, gated, or moved | **Yes** | mirror the weights; we keep the right but not the artifact |
| Model card edited so the licence claim is unprovable later | **Yes** | snapshot LICENSE + card text at a pinned SHA |
| Future versions closed, leaving us frozen on 2.2 | **Yes** | the benchmark makes swapping cheap — that is its main job |
| Upstream withdraws over a training-data dispute | Possible | grant survives; our own risk assessment would be separate |

### Most assets are model-independent by construction

| Asset | Survives a base-model change? |
|---|---|
| Benchmark suite | **Fully** |
| Scorers (LSE-C/D, CSIM, luma) | **Fully** |
| Rail / orchestration code | **Fully** |
| Prompt layer | **Mostly** — encodes Indian-context priors, needs retuning not rewriting |
| LoRA weights | **No** — the only weight-coupled asset |

The LoRA is the one perishable thing, and the measure-first order of operations already builds
it last and gates it on evidence. That is not a lucky accident; it is the reason to keep the
order.

### The insurance

Mirror the weights, pin the revision, snapshot the licence.

- Pin exact HF revision SHAs, not tags. Tags move.
- Mirror to Beenga-controlled object storage. Cloudflare R2 is $0.015/GB-month with no egress
  fees; Backblaze B2 is $0.006/GB-month.
- ~250GB to mirror everything, ~100GB for only the arms that survive wave 0 →
  **$1.50–$3.75/month.** Cheaper than one benchmark run.
- Record provenance per component: repo, revision SHA, licence file hash, date retrieved. That
  file is the evidence the grant existed at that revision.
- Vendor the inference code too, pinned by git SHA. Apache-licensed code disappears from GitHub
  as readily as weights disappear from Hugging Face.

Do this at wave 0, before anything is built on top — not after.

## Distribution: what goes where

Four destinations, four different jobs. Conflating them is how the mirror ends up somewhere
useless and the dataset ends up somewhere illegal.

| Destination | What goes there | Why |
|---|---|---|
| **GitHub** `Beenga/beenga-video-os` | Benchmark, prompt layer, scorers, rail code, docs | Apache-2.0. No weights, no media. |
| **Hugging Face** `beenga/*` | Our own LoRA adapters, with model cards | Where discovery and the ecosystem are; adapters are small |
| **Replicate** `beenga/*`, **fal** | Serving | HF is not a production video serving rail |
| **R2 / B2**, private | Mirror of upstream weights + pinned model cards | Durability — and it must be a *different failure domain* from HF |

### Yes: our LoRAs go on Hugging Face, as Apache-2.0

A LoRA trained on Wan 2.2 can be licensed Apache-2.0. Apache has no share-alike clause, so the
adapter we train is ours to license, and the user-facing chain stays Apache base + Apache
adapter.

Ship the **adapter, not a merged checkpoint**: ~100–600MB against ~70GB, it avoids most of the
§4 redistribution burden, and it keeps attribution unambiguous.

### No: the mirror does not go on Hugging Face

Re-uploading upstream weights to a public `beenga/` org is *legal* under Apache §4. It is also
pointless as insurance — if the Hub removes an upstream repo for a legal reason, our copy on the
same Hub goes with it. Insurance has to sit in a different failure domain.

It is also against the spirit of HF's own policy: there is no per-repo size limit, but uploads
count against the account quota, and they explicitly ask that large public uploads be useful to
the community. A duplicate of Alibaba's weights is not.

Mirror → object storage, private. See `PROVENANCE.md`.

### Never as Apache: anything derived from arms A or B

A fine-tuned LatentSync inherits `openrail++`. A fine-tuned MuseTalk inherits
`creativeml-openrail-m`. Both may be published — under the inherited licence, labelled as such.
Neither may be called Apache-2.0.

### Not published at all: training media

CC-BY-SA clips carry share-alike; licensed stock usually forbids redistribution outright.
Publish the **manifest** — source URLs, licence, captions, hashes — not the files. Same pattern
as `harvest-commons.mjs` and `datasets/recipes.mjs` in `beenga-image`, whose `.gitignore`
already excludes `dataset/`.

### If we ever redistribute upstream weights

Apache §4 obligations apply: include the licence, mark modified files as changed, retain
attribution notices. **§4(d) NOTICE propagation does not apply** — none of the upstream repos
ship a NOTICE file, checked 2026-08-15. Re-check if we re-vendor at a later commit; this is the
same conclusion, and the same caveat, that `beenga-image` recorded for BFL.

## Layout

```
benchmarks/beenga-video-v1.json   32 cases across 5 axes, machine-readable
lib/prompt.mjs                    the prompt layer — deliberately empty until wave 0 runs
scripts/run-benchmark.mjs         runner; schema-driven, dry-run first, cost-capped
scripts/score-clips.py            luma trend + CSIM; LSE hook, not reimplemented
scripts/mirror-weights.sh         pin a revision, archive the card, mirror the weights
PROVENANCE.md                     the licence lockfile
out/<tag>/                        clips + runs.json + scores.json per run
```

## Running it

```bash
cp .env.example .env               # add your Replicate token
                                   # node 18+ for global fetch; no npm dependencies

# ALWAYS dry-run first. Resolves version, schema, prompts and cost, and spends nothing.
node scripts/run-benchmark.mjs --model wan-video/wan-2.2-5b-fast --dry-run

# wave 0 baseline, both candidate bases
node scripts/run-benchmark.mjs --model wan-video/wan-2.2-5b-fast  --tag base-5b
node scripts/run-benchmark.mjs --model wan-video/wan-2.2-t2v-fast --tag base-a14b

# one case, three seeds, when something looks like it might be real
node scripts/run-benchmark.mjs --only VID-DEF-001 --seed 77 --tag spot

# measure rather than eyeball
python3 scripts/score-clips.py out/base-5b
```

The runner refuses to start if the estimate exceeds `--max-cost` (default $5). At $0.05/clip and
480p, the full 34-clip suite is about **$1.70** per model.

Two guards worth knowing about, both there because a wrong number is worse than no number:
`--enhance` warns loudly if `lib/prompt.mjs` still has no rules, so a baseline run cannot be
filed as a wave-1 result; and cases needing a still or an audio track are skipped by name rather
than sent as broken requests you would still pay for.

## Open questions

- Which base wins wave 0, and therefore whether training runs on fal (A14B) or RunPod (5B).
- Whether arm C's beat-locked motion beats arm A's mouth fidelity on singing. Genuinely unknown.
- Whether the English-supervised viseme mapping transfers to Hindi. Genuinely unknown.
- Training footage sourcing: CC harvest vs licensed stock. Business decision, unpriced here.
- Whether the wave-1 "$0 prompt fix" pattern repeats at all for temporal defects. Motion may not
  be describable in tokens the way complexion turned out to be.

## Licensing

Beenga Video OS will be released under Apache 2.0.

The base models are Apache-2.0. **The lip-sync stage is not, in arms A and B** — see the licence
chain section above, and do not let a README elsewhere claim otherwise.

"Beenga" is a trademark. Apache-2.0 grants no trademark rights.

## Sources

Model cards and pricing pages, checked 2026-08-15:
[Wan2.2-TI2V-5B](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B) ·
[Wan2.2-S2V-14B](https://huggingface.co/Wan-AI/Wan2.2-S2V-14B) ·
[Wan2.2-Animate-2-14B](https://huggingface.co/Wan-AI/Wan2.2-Animate-2-14B) ·
[LatentSync](https://github.com/bytedance/LatentSync) ·
[LatentSync-1.6 weights](https://huggingface.co/ByteDance/LatentSync-1.6) ·
[MuseTalk](https://github.com/TMElyralab/MuseTalk) ·
[Replicate Wan 2.2](https://replicate.com/blog/wan-22) ·
[Replicate pricing](https://replicate.com/pricing) ·
[fal Wan 2.2 A14B](https://fal.ai/models/fal-ai/wan/v2.2-a14b/text-to-video) ·
[fal wan-22-trainer](https://fal.ai/models/fal-ai/wan-22-trainer/t2v-a14b) ·
[RunPod pricing](https://www.runpod.io/pricing) ·
[Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/) ·
[Backblaze B2 pricing](https://www.backblaze.com/cloud-storage/pricing)

## Making a music video

`MUSIC-VIDEO.md` is the end-to-end record: the stills-first pipeline, measured
per-clip costs on our own H100, where lip sync works and where it does not, and
the prompting mistakes that cost renders. Start there for any new video job.

Produced this way: `out/chhupke/chhupke-se-aa.mp4` (1:54, 18 shots) and four
vertical shorts in `out/chhupke/shorts/`.

⚠ Two findings worth reading before planning any lip-sync work:

- **A harmony duet cannot be lip-synced by one on-screen face.** 96% of voiced
  frames in the test track carried two simultaneous pitches.
- **Four attempts at automatic singer identification all failed**, one of them
  anti-correlated with what a listener heard. Do not build a fifth; see the
  section in MUSIC-VIDEO.md.
