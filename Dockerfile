# Beenga Video OS — RunPod serverless worker image.
#
# ⚠ THE WEIGHTS ARE NOT IN THIS IMAGE. That is the whole point.
#
# beenga-sync-1 baked ~46 GB of weights into a 114 GB Cog image and could not
# boot inside Replicate's 600s setup timeout. Here the weights live on a RunPod
# network volume mounted at /runpod-volume, so this image stays a few GB and a
# code change does not mean re-shipping the checkpoint.
#
# cuda 12.4, NOT 12.8: 12.8 maps to an Ubuntu 24.04 base which enforces PEP 668,
# making the system Python externally managed. That broke two builds on the
# image project in two different places.
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-dev python3-pip ffmpeg git \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3

WORKDIR /app

# Pinned to Wan's own requirements. transformers is capped there — do not float it.
#
# ⚠ einops/decord/loguru/omegaconf/peft are NOT in Wan's requirements.txt but its
# code imports them. Their file is incomplete; these arrive transitively in the
# authors' environment and are simply absent in a clean image. einops is the one
# that failed setup on Replicate — the rest were found by listing every import
# under wan/ so the next build does not discover them one at a time.
#
# flash_attn is in Wan's requirements and is deliberately absent: it compiles
# CUDA kernels, takes hours, and fails often. wan/modules/attention.py sets
# FLASH_ATTN_2_AVAILABLE = False on import failure and falls back to torch SDPA.
RUN pip3 install --no-cache-dir \
        torch==2.6.0 torchvision torchaudio \
        "opencv-python-headless>=4.9.0.80" \
        "diffusers>=0.31.0" \
        "transformers>=4.49.0,<=4.51.3" \
        "tokenizers>=0.20.3" \
        "accelerate>=1.1.1" \
        tqdm "imageio[ffmpeg]" imageio-ffmpeg easydict ftfy \
        "numpy>=1.23.5,<2" librosa soundfile huggingface_hub \
        einops decord loguru omegaconf peft \
        hf_transfer \
        runpod

# Beenga's fork of the inference code, not upstream's.
RUN git clone --depth 1 https://github.com/Beenga/Wan2.2.git /app/Wan2.2

COPY rp_handler.py /app/rp_handler.py

CMD ["python3", "-u", "/app/rp_handler.py"]
