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

# ── Python deps ──────────────────────────────────────────────────────────────
#
# Pinned to Wan's own requirements. transformers is capped there — do not float it.
#
# ⚠ einops/decord/loguru/omegaconf/peft are NOT in Wan's requirements.txt but its
# code imports them. Their file is incomplete; these arrive transitively in the
# authors' environment and are simply absent in a clean image. einops is the one
# that failed setup on Replicate — the rest were found by listing every import
# under wan/ so the next build does not discover them one at a time.
# ⚠ torch COMES FROM THE PYTORCH INDEX, NOT PyPI.
#
# Every prebuilt flash-attn wheel — 6 releases x 2 ABI variants, all tested —
# failed against PyPI's torch 2.6.0+cu124 with the same missing symbol:
#   c10::Error::Error(SourceLocation, std::__cxx11::string)
# Since all twelve wanted the identical symbol, the wheels agree with each other
# and it is our torch that is the odd one out. flash-attn builds against the
# official download.pytorch.org builds, so that is where torch has to come from.
RUN pip3 install --no-cache-dir --index-url https://download.pytorch.org/whl/cu124 \
        torch==2.6.0 torchvision torchaudio \
 && python3 -c "import torch; print('torch', torch.__version__, 'cuda', torch.version.cuda)"

# Everything else from PyPI. torch is already satisfied above, so it is not
# re-resolved here.
COPY requirements.txt /requirements.txt
RUN grep -vE '^(torch|torchvision|torchaudio)([=<>]|$)' /requirements.txt > /req-rest.txt \
 && pip3 install --no-cache-dir -r /req-rest.txt \
 && python3 -c "import torch; v=torch.__version__; assert v.startswith('2.6.0'), 'torch replaced: '+v; print('torch pin intact:', v)"

# ── flash-attn ───────────────────────────────────────────────────────────────
#
# ⚠ REQUIRED FOR USABLE SPEED, and it must come AFTER torch is installed —
# the check below imports flash_attn, which imports torch, so ordering this
# before the pip install above fails with ModuleNotFoundError: No module named
# 'torch'.
#
# Earlier builds omitted flash-attn on the grounds that it "compiles CUDA kernels,
# takes hours, and fails often". True of `pip install flash-attn`, which builds
# from source — and it wrongly ruled out the prebuilt wheels, which install in
# seconds.
#
# The cost of omitting it was measured, not guessed: with the SDPA fallback a
# 4.74s clip took 1471.8s (310x realtime). The same model at the same resolution
# on a hosted endpoint with flash-attn took 65–76s. Attention dominates video
# diffusion — sequences are frames x patches — so losing the fused varlen kernel
# costs roughly 20x.
#
# The import check is the point: the wrong wheel installs silently and would
# otherwise surface at runtime, after a worker cold start and a 45 GB model load.
#
# The SDPA fallback stays in Beenga/Wan2.2 regardless — it costs nothing when
# flash-attn is present and keeps the code runnable where it is not.
# ⚠ WHICH WHEEL WORKS IS FOUND BY SEARCH, NOT BY RULE.
#
# The script searches a matrix of flash-attn releases x ABI variants and keeps the
# first that imports. See install_flash_attn.sh for why: both ABI variants of one
# release failed on the SAME symbol, so the variable is which torch build the wheel
# was compiled against, not the ABI. It also asserts the torch pin survives --
# installing a wheel without --no-deps silently replaced torch 2.6.0 with 2.13.0.
COPY install_flash_attn.sh /install_flash_attn.sh
RUN bash /install_flash_attn.sh

# Beenga's fork of the inference code, not upstream's.
ARG WAN_SHA
RUN echo "wan=$WAN_SHA" && git clone --depth 1 https://github.com/Beenga/Wan2.2.git /app/Wan2.2 && \
    git -C /app/Wan2.2 rev-parse --short HEAD > /app/wan-sha.txt

COPY rp_handler.py /

CMD ["python3", "-u", "rp_handler.py"]
