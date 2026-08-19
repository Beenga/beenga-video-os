"""Beenga S2V — audio-driven video, running Beenga's own copy of the weights.

No calls to any Wan API. The checkpoint is baked into this image from
bkjha8/Wan2.2-S2V-14B, and inference runs through Beenga's fork of the Wan
inference code at github.com/Beenga/Wan2.2.

⚠ WHY THIS PRODUCES LONG VIDEO IN ONE CALL, unlike the orchestrator.

The orchestrator sliced audio into ~4.8s windows, generated each independently
and concatenated them — which is why it needed reanchoring, seam placement and
identity measurement. That was solving a problem the model does not have.

WanS2V.generate() takes `num_repeat`, and the audio encoder computes it from the
audio length: it produces `num_repeat` chunks of `infer_frames` each and keeps
continuity across them internally. Feed it twenty seconds of audio and it returns
twenty seconds of continuous video. Measured on the hosted endpoint before this
was written: 20s of vocal in, 19.81s of video out, one call, no seams.

So there is no stitching here at all.
"""
import os

# ⚠ MUST be set before torch is imported. The first run OOMed on a 44.4GiB L40S
# with 2.43GiB "reserved but unallocated" — i.e. fragmentation, which is exactly
# what expandable_segments addresses. The CUDA error message recommends it by name.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import subprocess
import sys
import tempfile
from pathlib import Path as PPath
from typing import Optional

from cog import BasePredictor, Input, Path

# Beenga's fork, cloned at build time.
sys.path.insert(0, "/src/Wan2.2")

CKPT = "/src/ckpt"

# 16fps is what the model writes, and it reads as choppy. The orchestrator learned
# this the hard way: i2v could interpolate itself, s2v cannot, and shipping raw
# output meant every lip-synced clip juddered.
TARGET_FPS = 30


def sh(args):
    return subprocess.run(args, capture_output=True, text=True)


class Predictor(BasePredictor):
    def setup(self):
        """Load the model once. ~28GB of weights in bf16, so this is the slow part."""
        import torch
        from wan.configs import WAN_CONFIGS
        from wan.speech2video import WanS2V

        self.torch = torch
        cfg = WAN_CONFIGS["s2v-14B"]
        self.model = WanS2V(
            config=cfg,
            checkpoint_dir=CKPT,
            device_id=0,
            rank=0,
            # ⚠ Single GPU: every distribution flag stays off. t5_cpu keeps the
            # 11GB text encoder off the card, which is the difference between
            # fitting on a 48GB L40S and needing an 80GB A100.
            t5_fsdp=False,
            dit_fsdp=False,
            use_sp=False,
            t5_cpu=True,
            init_on_cpu=True,
            convert_model_dtype=True,
        )

    def predict(
        self,
        image: Path = Input(description="Reference image. The person in this frame is the person who appears."),
        audio: Path = Input(description="Audio to drive the performance. Use an ISOLATED VOCAL, not a full mix — the model responds to audio energy rather than to voice, so a mix makes the performer mouth through the instrumental passages."),
        prompt: str = Input(description="What the video shows.", default="A person singing, realistic video."),
        max_seconds: float = Input(description="Cap on output length. The video matches the audio up to this. Longer audio costs proportionally more GPU time.", default=20, ge=1, le=180),
        resolution: str = Input(description="Output resolution. 480p fits a 48GB card comfortably; 720p needs 80GB and will OOM on smaller hardware.", default="480p", choices=["480p", "720p"]),
        sampling_steps: int = Input(description="Denoising steps. Lower is faster and rougher.", default=40, ge=10, le=60),
        guide_scale: float = Input(description="Prompt adherence.", default=5.0, ge=1.0, le=10.0),
        seed: int = Input(description="Random seed. -1 for random.", default=-1),
        interpolate: bool = Input(description="Lift the output from the model's native 16fps to 30fps. Off gives you the raw frames.", default=True),
    ) -> Path:

        work = PPath(tempfile.mkdtemp(prefix="beenga-s2v-"))
        img = work / "ref.png"
        aud = work / "audio.wav"
        img.write_bytes(PPath(str(image)).read_bytes())

        # Normalise the audio and trim to the cap in one pass. 16kHz mono is what
        # the wav2vec front end wants.
        sh(["ffmpeg", "-hide_banner", "-v", "error", "-i", str(audio),
            "-t", str(max_seconds), "-ar", "16000", "-ac", "1", "-y", str(aud)])

        # ⚠ max_area is the single biggest memory lever, and NOT passing it was the
        # first run's failure: generate() defaults to 720*1280, which allocated
        # 41GiB on a 44.4GiB L40S and died. Activation memory scales with area, so
        # 480p is roughly half.
        area = 720 * 1280 if resolution == "720p" else 480 * 832
        print(f"generating {resolution} from {max_seconds}s cap — model chunks internally, no stitching")

        self.torch.cuda.empty_cache()
        from wan.utils.utils import merge_video_audio, save_video

        video = self.model.generate(
            input_prompt=prompt,
            ref_image_path=str(img),
            audio_path=str(aud),
            enable_tts=False,
            tts_prompt_audio=None,
            tts_prompt_text=None,
            tts_text=None,
            # num_repeat left unset: the audio encoder derives it from the audio
            # length, which is the whole mechanism that makes one call produce a
            # long continuous take.
            max_area=area,
            infer_frames=80,
            sampling_steps=sampling_steps,
            guide_scale=guide_scale,
            seed=seed,
            offload_model=True,
        )

        raw = work / "raw.mp4"
        save_video(tensor=video[None], save_file=str(raw), fps=16, normalize=True, value_range=(-1, 1))
        merge_video_audio(video_path=str(raw), audio_path=str(aud))

        if not interpolate:
            return Path(raw)

        # Motion-compensated interpolation, not frame duplication — the difference
        # between "smoother" and "same judder, bigger file".
        out = work / "beenga-s2v.mp4"
        r = sh(["ffmpeg", "-hide_banner", "-v", "error", "-i", str(raw), "-filter:v",
                f"minterpolate=fps={TARGET_FPS}:mi_mode=mci:mc_mode=aobmc:vsbmc=1",
                "-c:a", "copy", "-y", str(out)])
        if out.exists() and out.stat().st_size > 0:
            return Path(out)
        print(f"interpolation failed ({r.stderr[:120]}) — returning native 16fps")
        return Path(raw)
