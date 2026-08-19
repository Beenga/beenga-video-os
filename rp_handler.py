"""Beenga Video OS — RunPod serverless worker.

Runs Beenga's own copy of the Wan 2.2 S2V weights. No calls to any Wan API and
no calls to Replicate.

⚠ WHY RUNPOD SERVERLESS AND NOT REPLICATE.

`beenga-sync-1` on Replicate could not boot: a 114 GB image against a hard 600s
setup timeout, which no amount of tuning fixes. RunPod serverless has no
equivalent wall, bills per second, and scales to zero. The weights live on a
network volume rather than inside the image, so the image stays small and code
changes do not mean re-shipping ~46 GB.

⚠ WHY THE WEIGHTS ARE bf16 AND NOT QUANTIZED.

Quantized Wan exists (QuantStack Q8 GGUF, szwagros fp8) and would cut ~17 GB.
It is deliberately NOT used here yet, because it is not a drop-in:
`wan/configs/wan_s2v_14B.py` hardcodes `models_t5_umt5-xxl-enc-bf16.pth` and
`Wan2.1_VAE.pth` — both `.pth` — while the fp8 repo ships `.safetensors`. Using
it requires patching the loader, which is a change to make deliberately with a
measurement in hand, not while also standing up a new host. Quantization was
urgent only because of Replicate's timeout; here it is an optimisation.

Measure load time first. Quantize if it is actually slow.
"""
import os

# ⚠ MUST precede the torch import. The first Replicate run OOMed with 2.43 GiB
# "reserved but unallocated" — fragmentation, which is what this addresses.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import base64
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import runpod

sys.path.insert(0, "/app/Wan2.2")

# Network volume mount. RunPod mounts it at /runpod-volume on serverless.
CKPT = os.environ.get("BEENGA_CKPT", "/runpod-volume/wan-s2v-14b")

# The model writes 16fps and it reads as choppy. i2v could interpolate itself,
# s2v cannot, so raw output juddered in every lip-synced clip.
TARGET_FPS = 30

# Below this mean luma a clip is a failed render, not a dark scene. LongCat was
# observed returning HTTP 200 with a well-formed MP4 that was black after the
# first frame; this guard exists so that class of failure is never returned as
# success. Valid clips measured ~90-150; failures measured ~17.
BLACK_LUMA_THRESHOLD = 25.0

MODEL = None

# Written only after a verified-complete download. Its absence means the
# checkpoint is missing or partial, and either way the fix is the same: fetch.
READY_MARKER = Path(CKPT) / ".beenga-complete"

# Files in the upstream checkpoint that are never loaded — ~3.4 GB of dead
# weight: Flax params, a duplicate of the safetensors, a KenLM decoder for a
# task we do not run, and a sample video.
PRUNE = ["*flax_model.msgpack", "*pytorch_model.bin", "*lm.binary", "assets/*"]


def sh(args):
    return subprocess.run(args, capture_output=True, text=True)


def ensure_weights():
    """Populate the network volume on first boot.

    ⚠ WHY THIS IS HERE RATHER THAN IN A SEPARATE LOADER POD.

    The obvious approach — spin a cheap pod, download onto the volume, terminate —
    was tried and abandoned. RunPod's SSH proxy only offers an interactive PTY and
    refuses non-interactive command execution, while the direct SSH port refuses
    connections outright. Overriding the pod's `dockerArgs` to run the download as
    a start command *replaces RunPod's entrypoint*, which is what installs SSH: the
    container then reports RUNNING with 0% CPU while doing nothing at all, and
    there is no way in to see that. Two pods were billed for ~30 minutes of
    silence before that was diagnosed.

    Doing it here removes the whole class of problem. There is no second machine to
    coordinate with, no SSH, and the download is visible in the worker's own logs.

    ⚠ This runs at MODULE IMPORT, i.e. during worker init, not inside a request.
    That matters: a ~45 GB pull would blow any per-request execution timeout.

    Concurrency: several workers can cold-start at once. `snapshot_download`
    resumes rather than corrupting, and the marker is written only on success, so
    the worst case is duplicated bandwidth — not a broken checkpoint.
    """
    if READY_MARKER.exists():
        print(f"weights present at {CKPT}")
        return

    repo = os.environ.get("BEENGA_WEIGHTS_REPO", "bkjha8/beenga-sync-14b")
    print(f"weights missing — fetching {repo} to {CKPT} (one time, ~45 GB)")

    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
    from huggingface_hub import snapshot_download

    snapshot_download(repo, local_dir=CKPT, max_workers=8, ignore_patterns=PRUNE)

    # Verify before marking ready. A partial download that gets marked complete
    # would fail on every subsequent boot with a confusing error, and the marker
    # would stop it ever self-healing.
    required = ["Wan2.1_VAE.pth", "models_t5_umt5-xxl-enc-bf16.pth"]
    missing = [f for f in required if not (Path(CKPT) / f).exists()]
    shards = list(Path(CKPT).glob("diffusion_pytorch_model-*.safetensors"))
    if missing or not shards:
        raise RuntimeError(f"incomplete checkpoint: missing={missing} shards={len(shards)}")

    READY_MARKER.write_text("ok")
    total = sum(f.stat().st_size for f in Path(CKPT).rglob("*") if f.is_file())
    print(f"weights ready: {total / 1e9:.1f} GB, {len(shards)} DiT shards")


def _fetch(src, dest):
    """Accept a URL or a base64 data string."""
    if src.startswith(("http://", "https://")):
        urllib.request.urlretrieve(src, dest)
    else:
        Path(dest).write_bytes(base64.b64decode(src.split(",")[-1]))
    return dest


def measure_luma(path):
    """Mean luma over the whole clip. Used to catch black-render failures."""
    r = sh(["ffmpeg", "-hide_banner", "-i", str(path), "-vf",
            "signalstats,metadata=print:key=lavfi.signalstats.YAVG", "-f", "null", "-"])
    vals = []
    for line in r.stderr.splitlines():
        if "YAVG=" in line:
            try:
                vals.append(float(line.split("YAVG=")[1].split()[0]))
            except (ValueError, IndexError):
                pass
    return sum(vals) / len(vals) if vals else None


def find_voiced_start(path, window, floor_db=-40.0):
    """Return an offset whose `window` seconds are actually voiced.

    ⚠ THIS EXISTS BECAUSE OF A REAL BUG, NOT AS A PRECAUTION.

    A bake-off was run against the first 5s of `bhor-bhajan/guide-vocal.mp3`.
    That song opens with ~20s of instrumental, so the model was driven by
    silence (-61.8 dB) and every clip was judged on a mouth that correctly never
    moved. Measured across the library: all four songs open quiet, two of them
    averaging -24 to -26 dB over their first 30 seconds.

    Any pipeline that naively takes the first N seconds of a song will lip-sync
    to near-silence. So the product finds the voiced region rather than trusting
    the caller to.
    """
    dur = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "csv=p=0", str(path)]).stdout.strip()
    try:
        dur = float(dur)
    except ValueError:
        return 0.0
    if dur <= window:
        return 0.0

    best_t, best_db = 0.0, -999.0
    step = max(1.0, window / 2)
    t = 0.0
    while t + window <= dur:
        r = sh(["ffmpeg", "-hide_banner", "-ss", str(t), "-t", str(window),
                "-i", str(path), "-af", "volumedetect", "-f", "null", "-"])
        # ⚠ volumedetect logs at INFO. `-v error` silences it and every parse
        # returns nothing — that cost a debugging cycle once already.
        db = None
        for line in r.stderr.splitlines():
            if "mean_volume:" in line:
                try:
                    db = float(line.split("mean_volume:")[1].split("dB")[0].strip())
                except ValueError:
                    pass
        if db is not None and db > best_db:
            best_db, best_t = db, t
        if best_db > floor_db and t > 0:
            break  # good enough; don't scan a 3-minute song exhaustively
        t += step
    return best_t if best_db > -900 else 0.0


def load_model():
    global MODEL
    if MODEL is not None:
        return MODEL
    import torch
    from wan.configs import WAN_CONFIGS
    from wan.speech2video import WanS2V

    cfg = WAN_CONFIGS["s2v-14B"]
    MODEL = WanS2V(
        config=cfg,
        checkpoint_dir=CKPT,
        device_id=0,
        rank=0,
        # Single GPU: every distribution flag off. t5_cpu keeps the 11 GB text
        # encoder off the card, which is the difference between fitting on a
        # 48 GB L40S and needing 80 GB.
        t5_fsdp=False,
        dit_fsdp=False,
        use_sp=False,
        t5_cpu=True,
        init_on_cpu=True,
        convert_model_dtype=True,
    )
    return MODEL


def handler(job):
    inp = job.get("input") or {}
    prompt = inp.get("prompt", "A person singing, realistic video.")
    image = inp.get("image")
    audio = inp.get("audio")
    if not image or not audio:
        return {"error": "both `image` and `audio` are required"}

    max_seconds = float(inp.get("max_seconds", 20))
    resolution = inp.get("resolution", "480p")
    steps = int(inp.get("sampling_steps", 40))
    guide = float(inp.get("guide_scale", 5.0))
    seed = int(inp.get("seed", -1))
    interpolate = bool(inp.get("interpolate", True))
    auto_voiced = bool(inp.get("auto_voiced", True))

    work = Path(tempfile.mkdtemp(prefix="beenga-"))
    img = _fetch(image, str(work / "ref.png"))
    raw_audio = _fetch(audio, str(work / "in_audio"))

    start_at = find_voiced_start(raw_audio, min(max_seconds, 10.0)) if auto_voiced else 0.0

    aud = work / "audio.wav"
    sh(["ffmpeg", "-hide_banner", "-v", "error", "-ss", str(start_at),
        "-i", str(raw_audio), "-t", str(max_seconds),
        "-ar", "16000", "-ac", "1", "-y", str(aud)])

    # ⚠ max_area is the biggest memory lever and NOT passing it caused the first
    # OOM: generate() defaults to 720*1280, which allocated 41 GiB on a 44 GiB
    # card. Activation memory scales with area, so 480p is roughly half.
    area = 720 * 1280 if resolution == "720p" else 480 * 832

    import torch
    model = load_model()
    torch.cuda.empty_cache()
    from wan.utils.utils import merge_video_audio, save_video

    video = model.generate(
        input_prompt=prompt,
        ref_image_path=str(img),
        audio_path=str(aud),
        enable_tts=False,
        tts_prompt_audio=None,
        tts_prompt_text=None,
        tts_text=None,
        # num_repeat intentionally unset: the audio encoder derives it from the
        # audio length. That is the mechanism that yields one long continuous
        # take rather than stitched chunks — measured 20s audio -> 19.81s video.
        max_area=area,
        infer_frames=80,
        sampling_steps=steps,
        guide_scale=guide,
        seed=seed,
        offload_model=True,
    )

    raw = work / "raw.mp4"
    save_video(tensor=video[None], save_file=str(raw), fps=16,
               normalize=True, value_range=(-1, 1))
    merge_video_audio(video_path=str(raw), audio_path=str(aud))

    out = raw
    if interpolate:
        # Motion-compensated, not frame duplication — the difference between
        # "smoother" and "same judder, bigger file".
        cand = work / "out.mp4"
        r = sh(["ffmpeg", "-hide_banner", "-v", "error", "-i", str(raw), "-filter:v",
                f"minterpolate=fps={TARGET_FPS}:mi_mode=mci:mc_mode=aobmc:vsbmc=1",
                "-c:a", "copy", "-y", str(cand)])
        if cand.exists() and cand.stat().st_size > 0:
            out = cand
        else:
            print(f"interpolation failed ({r.stderr[:160]}) — returning native 16fps")

    luma = measure_luma(out)
    if luma is not None and luma < BLACK_LUMA_THRESHOLD:
        return {"error": f"black render (mean luma {luma:.1f} < {BLACK_LUMA_THRESHOLD})",
                "retryable": True}

    probe = sh(["ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-show_entries", "format=duration", "-of", "csv=p=0", str(out)]).stdout

    return {
        "video_base64": base64.b64encode(out.read_bytes()).decode(),
        "meta": {
            "voiced_start_s": round(start_at, 2),
            "mean_luma": round(luma, 1) if luma else None,
            "probe": probe.strip(),
        },
    }


if __name__ == "__main__":
    # ⚠ The __main__ guard is not decoration. RunPod's GitHub integration
    # statically scans for this exact shape — `runpod.serverless.start` inside
    # `if __name__ == '__main__':`, as in runpod-workers/worker-basic — and
    # reports "a handler function is required for queue-based endpoints" when it
    # cannot find it, even though a perfectly good handler is present. Calling
    # start() at module level is valid Python and fails that check.
    #
    # It is also correct on its own terms: ensure_weights() pulls ~45 GB, and
    # nothing that heavy should fire merely because something imported this file.
    ensure_weights()
    runpod.serverless.start({"handler": handler})
