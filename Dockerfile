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
ARG WAN_SHA=51f3107
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-dev python3-pip ffmpeg git \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3

WORKDIR /

# Pinned to Wan's own requirements. transformers is capped there — do not float it.
#
# ⚠ einops/decord/loguru/omegaconf/peft are NOT in Wan's requirements.txt but its
# code imports them. Their file is incomplete; these arrive transitively in the
# authors' environment and are simply absent in a clean image. einops is the one
# that failed setup on Replicate — the rest were found by listing every import
# under wan/ so the next build does not discover them one at a time.
#
# ⚠ flash-attn IS required for usable speed. Installed from a PREBUILT WHEEL.
#
# Earlier builds omitted it on the grounds that it "compiles CUDA kernels, takes
# hours, and fails often". That is true of `pip install flash-attn`, which builds
# from source -- and it wrongly ruled out the prebuilt wheels, which install in
# seconds.
#
# The cost of omitting it was measured, not guessed: with the SDPA fallback a
# 4.74s clip took 1471.8s (310x realtime). The same model and resolution on a
# hosted endpoint with flash-attn took 65-76s. Attention dominates video
# diffusion -- sequences are frames x patches -- so losing the fused varlen
# kernel costs roughly 20x.
#
# The wheel must match the image exactly: cu12, torch 2.6, cp311, linux_x86_64.
# cxx11abiFALSE is correct for PyPI torch builds, which ship with
# _GLIBCXX_USE_CXX11_ABI = False. Picking abiTRUE against a FALSE torch produces
# an import-time symbol error, not a build failure.
#
# The SDPA fallback stays in Beenga/Wan2.2 regardless: it costs nothing when
# flash-attn is present and keeps the code runnable where it is not.
RUN pip3 install --no-cache-dir \
      "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3.post1/flash_attn-2.8.3.post1+cu12torch2.6cxx11abiFALSE-cp311-cp311-linux_x86_64.whl" \
 && python3 -c "import flash_attn, torch; print('flash_attn', flash_attn.__version__, '| torch', torch.__version__, '| cxx11abi', torch._C._GLIBCXX_USE_CXX11_ABI)"

# Beenga's fork of the inference code, not upstream's.
ARG WAN_SHA
RUN echo "wan=$WAN_SHA" && git clone --depth 1 https://github.com/Beenga/Wan2.2.git /app/Wan2.2 && \
    git -C /app/Wan2.2 rev-parse --short HEAD > /app/wan-sha.txt

COPY rp_handler.py /

CMD ["python3", "-u", "rp_handler.py"]
