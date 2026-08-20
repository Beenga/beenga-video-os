# RunPod serverless worker

Beenga's own Wan 2.2 S2V weights, served from a GPU we control. No Wan API, no
Replicate.

## Why this replaces the Cog path

`beenga-sync-1` baked ~46 GB of weights into a 114 GB Cog image and **could not
boot** — Replicate kills any container that does not finish setup in 600
seconds, and no amount of tuning fixes a 114 GB pull. That is a platform
mismatch, not a bug.

RunPod serverless has no equivalent wall, bills per second, and scales to zero.
The weights sit on a network volume instead of inside the image, so the image
stays small and code changes do not re-ship the checkpoint.

## Cost

| | |
|---|---|
| Network volume (46 GB @ $0.07/GB/mo) | **~$3.20/month**, the only fixed cost |
| L40S 48 GB | $1.75/hr = $0.000486/sec |
| A100 80 GB | $2.72/hr |
| H100 80 GB | $4.79/hr |
| Idle | **$0** — scales to zero |

⚠ **Per-video cost is an estimate, not a measurement.** Extrapolating Wan's
Replicate timings (4.81s of video in 65–76s of GPU, ~14× realtime) gives roughly
**$1.23 for a 3-minute video on an L40S**, against $27 on fal. The 14× figure has
not been measured on our own hardware and is the first thing the deployment
should establish.

Cold start, measured by a third party rather than by us: **~8s** when RunPod's
scheduler reuses the same host (FlashBoot snapshot restore), **~110s** on a new
host. RunPod markets "under 1 second"; that is not what independent testing
shows.

## GPU choice

**L40S 48 GB.** The bf16 checkpoint plus activations at 480p fits in less, but a
24 GB card leaves no headroom for 720p or longer segments — and OOM is exactly
what killed the first Replicate build. The premium over a 4090 buys margin.

## Deploy

### 1. Network volume

Create one in the RunPod console, ≥60 GB, in a datacenter that has L40S. A
volume pins the endpoint to its datacenter, so pick one with the GPU you want.

### 2. Weights onto the volume

Start any cheap GPU pod with the volume attached, then:

```bash
pip install huggingface_hub
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('bkjha8/beenga-sync-14b',
                  local_dir='/workspace/wan-s2v-14b', max_workers=8)"
```

Then terminate the pod. The volume keeps the weights.

⚠ **Prune before or after copying** — the checkpoint carries ~3.4 GB that is
never loaded: `wav2vec2-*/flax_model.msgpack` (Flax, 1.26 GB),
`wav2vec2-*/pytorch_model.bin` (duplicate of the safetensors, 1.26 GB),
`wav2vec2-*/language_model/lm.binary` (KenLM decoder, 0.86 GB), and a sample
`assets/*.mp4`.

### 3. Image

No build machine is currently provisioned — the DigitalOcean builder was
destroyed. Two options:

**GitHub integration (preferred, no builder needed).** Point the RunPod console
at this repo with repo root as the build context; RunPod builds and hosts the
image.

**Manual build.** Requires a Linux x86 host with Docker:

```bash
docker build --platform linux/amd64 -t <user>/beenga-s2v:0.1 runpod/
docker push <user>/beenga-s2v:0.1
```

⚠ `--platform linux/amd64` is required. And do not tag `:latest` — it is mutable
and makes cache behaviour impossible to reason about.

### 4. Endpoint

Create a serverless endpoint from the image, attach the network volume, select
L40S, and set `BEENGA_CKPT` if the weights are not at `/runpod-volume/wan-s2v-14b`.

⚠ **`/runpod-volume` is the documented serverless mount point but has not been
verified by us.** Check it on the first run; the handler reads `BEENGA_CKPT` so
it can be corrected without a rebuild.

## Input

```json
{
  "input": {
    "prompt": "An Indian woman in her late twenties sings into a studio microphone, realistic video.",
    "image": "https://... or base64",
    "audio": "https://... or base64",
    "max_seconds": 20,
    "resolution": "480p",
    "sampling_steps": 40,
    "guide_scale": 5.0,
    "seed": -1,
    "interpolate": true,
    "auto_voiced": true
  }
}
```

Returns `video_base64` plus `meta` with `voiced_start_s`, `mean_luma` and an
ffprobe line.

## Two guards that exist because of real failures

**`auto_voiced`** — finds the voiced region of the audio instead of trusting the
first N seconds. A bake-off was run against the opening 5s of
`bhor-bhajan/guide-vocal.mp3`, which is ~20s of instrumental intro at −61.8 dB.
The model was driven by silence and the clips were judged on a mouth that
correctly never moved. All four songs in the library open quiet; two average −24
to −26 dB over their first 30 seconds. Set `auto_voiced: false` to disable.

**Black-render rejection** — any output whose mean luma is below 25 is returned
as an error rather than as a video. LongCat was observed returning HTTP 200 with
a well-formed MP4 — correct duration, frame count and container, plausible first
frame — that was pure black after frame 0. Valid clips measure ~90–150; that
failure measured 16.8. Without this guard, that class of failure ships to users
while the API reports success.

## First successful run — 2026-08-20

Beenga's own weights, on a GPU we control. No Wan API, no Replicate.

| | |
|---|---|
| Cold start | **7.2s** (FlashBoot snapshot; weights already on the volume) |
| Generation | **1471.8s** for 4.74s of video |
| Output | 832x448, 30fps, 4.74s, mean luma 86.9 (passed the black-render gate) |
| GPU | RTX 6000 Ada 48GB, US-IL-1 |

⚠ **310x realtime. The cost model assumed 14x, and was wrong by a factor of 22.**

| | assumed @14x | measured @310x |
|---|---|---|
| 5s clip | $0.14 | **$0.50** |
| 3-minute video | $0.85 | **~$19** |

At that rate self-hosting barely beats fal's $27 and is unusable interactively.

### The cause, and the fix

`flash_attention()` falls back to torch SDPA because flash-attn is not installed.
That fallback is what made the run possible at all, but attention is the dominant
cost in video diffusion — sequences are frames x patches — and losing the fused
varlen kernel is what costs the 22x.

The Dockerfile justified omitting flash-attn on the grounds that it "compiles CUDA
kernels, takes hours, and fails often". True of `pip install flash-attn` from
source. **Prebuilt wheels exist and install in seconds:**

```
https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3.post1/\
flash_attn-2.8.3.post1+cu12torch2.6cxx11abiFALSE-cp311-cp311-linux_x86_64.whl
```

Matches this image exactly — cu12, torch 2.6, cp311, linux_x86_64. `cxx11abiFALSE`
is the right variant for PyPI torch builds, which ship with `_GLIBCXX_USE_CXX11_ABI`
false.

**Keep the SDPA fallback in the fork regardless.** It costs nothing when flash-attn
is present and keeps the code runnable where it is not.

### Deploying a fix requires draining workers

Repointing the template at a new image does **not** recycle running workers. Two
runs failed identically on already-fixed code because RunPod kept serving a warm
worker with the previous image — visible as an unchanged traceback line number and
a ~16s delayTime with no image pull. Scale `workersMax` to 0, wait for the worker
count to reach zero, then scale back up.

## Not done

- Quantized weights. Q8/fp8 exist and would cut ~17 GB, but they are not a
  drop-in: `wan/configs/wan_s2v_14B.py` hardcodes `.pth` for T5 and the VAE while
  the fp8 repo ships `.safetensors`. Quantization was urgent only because of
  Replicate's timeout — here it is an optimisation, to be done with a load-time
  measurement in hand.
- Generation-time measurement, which the whole cost model rests on.
- 3-minute continuity validation on this host.
