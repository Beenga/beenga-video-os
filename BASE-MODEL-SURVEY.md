# Base model survey — can it be fine-tuned, and can we own it?

Surveyed 2026-08-18, after `beenga-sync-1` failed to boot on Replicate and the question became
whether a different base model would serve better.

**Two tests, applied to everything.** A model passes only if it passes both.

1. **Ownable** — permissive licence on the *weights*, not just the code. This is where the
   ecosystem lies most: LatentSync's code is Apache-2.0 and its weights are `openrail++`;
   MuseTalk's code is MIT and its weights are `creativeml-openrail-m`. A 2026 blog post found
   during this survey still describes LatentSync as "Apache-2.0". Every licence below was read
   from the HuggingFace API, not from a summary.
2. **Fine-tunable** — training code that actually exists, in a trainer people use. An inference
   repo is not a base model you own; it is someone else's model you rent for free.

## Result

| Model | Weights licence | Trainable | Audio | Verdict |
|---|---|---|---|---|
| **Wan 2.2** | **apache-2.0** | **musubi-tuner + DiffSynth** | S2V variant | **keep** |
| LongCat-Video-Avatar-1.5 | **mit** | none — inference only | yes | no |
| LTX-2.3 / 2.5 | `ltx-2-community-license-agreement` | — | yes | **not open** |
| HunyuanVideo / 1.5 | `tencent-hunyuan-community` | musubi | — | **not open** |
| Mochi-1 | apache-2.0 | — | no | stale, T2V only |
| Open-Sora v2 | apache-2.0 | — | no | stale, T2V only |
| Allegro | apache-2.0 | — | no | stale (2024-10) |
| EchoMimicV3 | apache-2.0 | none | yes | **see below** |
| InfiniteTalk | apache-2.0 | none | yes | Wan-derived |
| MultiTalk | apache-2.0 | none | yes | Wan-derived |
| OmniAvatar-14B | apache-2.0 | none | yes | Wan-derived |
| FantasyTalking | apache-2.0 | none | yes | Wan-derived |
| prunaai/p-video | **none published** | — | yes | closed product |

## The finding: Wan is the substrate

Every permissively-licensed audio-driven model that passed the licence test is **built on Wan**.

- InfiniteTalk → Wan 2.1
- MultiTalk → Wan
- FantasyTalking → Wan
- OmniAvatar-14B → Wan 2.1 — the repo is **1.2 GB**, because it is an *adapter*, not a model
- EchoMimicV3 → Wan2.1-Fun-V1.1-1.3B-InP

This was not the expected answer. The question was "is there something better than Wan", and the
survey kept returning models that *are* Wan with a head on top. The size of `OmniAvatar-14B` is the
clearest tell: a repo named for 14B parameters that contains 1.2 GB is not a base model.

So the choice is not "Wan or something better". It is "Wan, or something built on Wan, or something
we are not allowed to own."

**Only LongCat is genuinely independent** — a real second foundation, MIT, natively pretrained on
video-continuation for minutes-long output, 30fps native against Wan S2V's 16fps. It is better than
Wan on several axes. It ships **no training code**, and no trainer supports it. It fails test 2, and
test 2 is the project.

## What the trainers actually support

Checked directly, because "supports Wan" is not the same as "supports the variant we run".

- **musubi-tuner** — HunyuanVideo, **Wan 2.1/2.2**, FramePack, FLUX.1 Kontext, FLUX.2, Qwen-Image,
  Z-Image, HiDream, HunyuanVideo 1.5, Kandinsky 5, Ideogram4, Krea 2. No LongCat, no InfiniteTalk,
  no HunyuanVideo-Avatar. **S2V is not listed as a distinct variant.**
- **DiffSynth-Studio** — Wan 2.2 with "LoRA training and full training", FP8 quantization,
  layer-by-layer offload, sequence parallelism. S2V training not explicitly documented.

⚠ **This matters for the plan and is worth being precise about.** The India LoRA trains on
**Wan 2.2 I2V-A14B** — which both trainers support — and S2V is used as-is for lip sync. The LoRA
targets the part that needs to learn India; the audio conditioning does not. `cog/predict.py`
already reflects this: it takes `lora_weights_high` / `lora_weights_low`, the A14B MoE experts.
Nothing in the survey changes that split. But if we ever want to fine-tune S2V *itself*, no trainer
currently claims support, and that would be new work.

## EchoMimicV3 — the one worth acting on

Apache-2.0, 1.3B parameters, **7.1 GB total**, 12 GB VRAM on the Flash-Pro build, long video via
"Long Video CFG", and built on Wan so it sits inside the family we already own.

Against `beenga-sync-1`'s 49 GB of weights and 114 GB image, this is the difference between a model
that cannot boot on Replicate and one that boots comfortably.

The tradeoffs are real: 768×768, portrait and semi-body rather than full scene, and no training
code. It is not a replacement for Wan 2.2 S2V on quality. It is a way to have something serving
while the quality tier goes to hardware that can hold it.

## Decision — revised, after the constraint changed

The first version of this section concluded "Wan 2.2 stays", on the reasoning that Wan is the only
model that is ownable *and* trainable. That held while fine-tuning the **video** model was assumed
to be mandatory. It was then made explicit that any combination doing animation and lip sync is
acceptable, which reopens the question — so the reasoning is redone here rather than defended.

**The India look does not have to come from the video model.**

`beenga/beenga-image-1` already generates contemporary-India stills, and it is ours and trainable.
LongCat-Avatar and Wan S2V are both **image-conditioned**: the reference still fixes the person,
the clothing, the setting, the lighting and the framing. The failure that motivated the India LoRA
— "a busy street in Mumbai" rendering as a Chinese street — is a **text-to-video** failure. In an
image-conditioned path, the street comes from the image.

So the trainable India component is the **image** model, which we already own. The video model's
job is animation fidelity.

⚠ **This is not a free pass, and the repo already contains the counter-evidence.** `REVIEW.md`
records a bharatanatyam failure — motion *idiom* is India-specific and is not carried by a still.
How a sari moves, how a crowd behaves, how a dance reads: those live in the video model. So
dropping video-model training has a real cost. The claim here is that the cost is narrower than
assumed, not that it is zero.

### Where that lands

| | Wan 2.2 (I2V-A14B + S2V) | LongCat-Video-Avatar-1.5 |
|---|---|---|
| Animation + lip sync | **two models** | **one model** |
| 3-minute output | internal chunking | **pretrained objective** |
| Native fps | 16 → we interpolate | **30** |
| Licence | apache-2.0 | **mit** |
| Deployable size | 49 GB / 28 GB fp8 | 74.9 GB / **19 GB Q8** |
| Trainable today | **yes, two trainers** | no |
| Quality vs each other | **unmeasured** | **unmeasured** |

LongCat wins on every axis except trainability — and it wins hardest on the one thing named as the
critical deliverable: *one solution for end-to-end generation and lip sync at three minutes*. Wan
reaches three minutes by chunking; LongCat was **pretrained** on video-continuation for it.

### Bake-off result — 2026-08-18

Run against `stills/singer.png` and `stills/bk.png`, driven by a real recorded Hinglish line
(`audio/hinglish-line.wav`) rather than a synthetic vocal. Identical image, audio and seed through
both models. Clips in `out/bakeoff/`.

| | Wan S2V | LongCat |
|---|---|---|
| Resolution (16:9 still) | **1216×704** | 896×448 |
| Resolution (1:1 still) | **960×960** | 640×640 |
| fps | 16 | 16 |
| Length from 5s audio | 4.81s | **5.82s** |
| **Preferred on lip-sync quality** | | **✅ chosen** |

**The human verdict went to LongCat**, on the `bk.png` dialogue pair. That is the deciding input:
resolution is measurable and Wan wins it, but perceived lip-sync quality is what the product sells,
and it is not something the metrics here capture.

⚠ **Weight of evidence.** This is one reference image, one audio clip, one judged pair. It is enough
to redirect the plan; it is not enough to call the question closed. It should be re-checked as more
cases are run — particularly against real camera footage, which has still never been tested.

### Corrections to earlier claims in this document

Two things asserted before the bake-off did not survive it:

- **"Native 30fps."** LongCat's avatar endpoint outputs **16fps**, same as Wan. The 30fps figure
  belongs to LongCat-Video's text-to-video path and was carried across without checking.
- **"LongCat ignores the prompt."** Wrong, and it was asserted on broken evidence. Three runs
  returned byte-identical output, which looked like the prompt having no effect. They were **failed
  renders** — first frame, then pure black (YAVG 16.8 against ~90 for valid clips). Measured against
  a clean baseline, prompt, seed and song all change the output:

  | Input changed | PSNR vs baseline | (identical = `inf`) |
  |---|---|---|
  | Seed | 15.83 | largest effect |
  | Prompt | 19.83 | prompt works |
  | Song | 21.79 | song works |

  So a devotional track and a party track do **not** produce the same performance.

### ⚠ LongCat fails silently to black

The failed renders returned HTTP success with a well-formed MP4 — correct duration, frame count,
container, plausible first frame — and the rest black. No error anywhere in the API response.

**Any production path needs a brightness gate on output**: mean luma below ~25 is a failure and must
be retried, not shipped. Without it this reaches users as a black video while the API reports
success. `enable_safety_checker: true` is the suspected trigger and has not been confirmed.

### What is actually decided — Wan stays

**Decision: Wan 2.2, served from quantized weights on RunPod serverless.**

The quality preference for LongCat was **slight, not decisive** — stated as "no huge preference",
with the real criterion being "whatever is cheap and better quality in the long run". An earlier
draft of this section treated the preference as decisive; that over-weighted a narrow margin from a
single judged pair.

**The correction that settles it: LongCat's size advantage does not exist.** This document
previously contrasted LongCat's 19 GB against Wan's 49 GB. But quantized Wan was already published:

| | Full pipeline, quantized |
|---|---|
| Wan 2.2 S2V (`QuantStack` Q8 DiT + fp8 T5 + wav2vec + VAE) | **~28 GB** |
| LongCat-Avatar-1.5 (Q8 DiT + Whisper + VAE) | ~23 GB |

Both fit a 48 GB L40S with headroom. Serving cost was the main argument for switching, and it is a
wash.

With that removed:

| | Wan | LongCat |
|---|---|---|
| Quality (human judgement, 1 pair) | | slight edge |
| Resolution | **2.1× the pixels** | |
| Quantized size | 28 GB | 23 GB |
| **Trainable** | **musubi-tuner + DiffSynth** | **no trainer exists** |
| Ecosystem | **the substrate everything builds on** | standalone |
| Already vendored | **mirrors, forks, benchmark, scorers** | nothing |
| Licence | apache-2.0 | mit |

**Trainability decides it, because that is what "better quality in the long run" means.** Quality
does not improve on its own; it improves by training on footage we own. Only Wan can absorb the
India LoRA. Choosing LongCat means shipping Meituan's model unchanged in two years, while Wan can
become a model nobody else has.

**What is given up:** a slight quality edge today, MIT instead of Apache, and two models instead of
one. All real; none structural.

### The deployment problem had a quantization fix, not a model fix

`beenga-sync-1` failed because a 114 GB image cannot boot inside Replicate's 600s limit. The whole
base-model search was triggered by that failure. It was the wrong diagnosis: the fix is quantized
weights (49 GB → 28 GB, image well under half) plus a host without a hard boot timeout.

The search was still worth running — it stopped a base-model switch justified on spec-sheet claims
that did not survive measurement (see corrections above).

### Target architecture

| | |
|---|---|
| Weights | Wan 2.2 S2V, Q8 DiT + fp8 T5 (~28 GB), mirrored under Beenga naming |
| Host | RunPod **serverless** — scale to zero, per-second billing, no boot-timeout wall |
| GPU | **L40S 48 GB** — 24 GB leaves no headroom for 720p, and OOM already killed one build |
| Storage | network volume, ~$1.33/month for the weights |
| Cost/video | ~$1–2 per 3 minutes (vs $27 on fal) — **assumes 14× realtime, unmeasured** |
| Cold start | ~8s same-host snapshot, ~110s new host (measured by a third party, not by us) |

### Revisit conditions

This decision is cheap to reverse — Wan stays vendored regardless. Reopen it if:

- LongCat's quality edge **widens** on more cases, especially real camera footage (never yet tested)
- A LoRA trainer gains LongCat support, removing the one decisive advantage Wan holds
- Measured generation time makes the cost picture materially different from the estimate above
Both models are unmeasured against each other, and a switch justified on spec sheets rather than
output would repeat the wave-0 mistake of comparing 3.4s of one model against 5.1s of another.

**Next step: bake-off before commitment.** fal.ai hosts `fal-ai/longcat-single-avatar` at
$0.15/video-second (480p), so LongCat can be measured against the existing
`benchmarks/beenga-video-v1.json` cases with no build, no droplet and no weights download. Roughly
$30 for the full set at 480p, or a few dollars for a decisive subset.

Wan stays vendored and unchanged either way — mirrors, forks and `beenga-sync-1` cost nothing to
keep, and Wan remains the fallback precisely because it is the trainable one.

## Not verified

Quality was **not** benchmarked. Licences, sizes, parameter counts and trainer support were read
from the HuggingFace API and the repos. Claims about LongCat's and EchoMimicV3's output quality come
from their model cards and have not been measured against Wan 2.2 S2V on our benchmark. If
EchoMimicV3 is adopted as a fast tier, it needs a run through `benchmarks/beenga-video-v1.json`
first.

## Sources

- https://huggingface.co/meituan-longcat/LongCat-Video-Avatar-1.5
- https://github.com/meituan-longcat/LongCat-Video
- https://github.com/antgroup/echomimic_v3
- https://github.com/kohya-ss/musubi-tuner
- https://github.com/modelscope/DiffSynth-Studio
- https://huggingface.co/QuantStack/Wan2.2-S2V-14B-GGUF
- https://replicate.com/prunaai/p-video
