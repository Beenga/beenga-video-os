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
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt \
 && python3 -c "import torch; print('torch', torch.__version__, 'cuda', torch.version.cuda)"

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
# ⚠ TRY BOTH ABI VARIANTS AND KEEP WHICHEVER IMPORTS.
#
# torch._C._GLIBCXX_USE_CXX11_ABI reported FALSE while the FALSE wheel failed with
#   undefined symbol: _ZN3c105ErrorC2ENS_14SourceLocationENSt7__cxx1112basic_string...
# i.e. it wanted __cxx11 strings. The flag does not reliably describe how libtorch
# was actually compiled in recent builds, so selecting from it is guesswork
# dressed up as detection. Both variants are ~190 MB and install in seconds; an
# import is the only thing that actually proves compatibility, so that is the test.
COPY install_flash_attn.sh /install_flash_attn.sh
RUN bash /install_flash_attn.sh \
 && python3 -c "import torch,flash_attn; v=torch.__version__; \
assert v.startswith('2.6.0'), 'torch was replaced: '+v; \
print('verified torch',v,'flash_attn',flash_attn.__version__)"

# Beenga's fork of the inference code, not upstream's.
ARG WAN_SHA
RUN echo "wan=$WAN_SHA" && git clone --depth 1 https://github.com/Beenga/Wan2.2.git /app/Wan2.2 && \
    git -C /app/Wan2.2 rev-parse --short HEAD > /app/wan-sha.txt

COPY rp_handler.py /

CMD ["python3", "-u", "rp_handler.py"]
