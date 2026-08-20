#!/usr/bin/env bash
# Install flash-attn from a prebuilt wheel, proving it works by importing it.
#
# ⚠ WHY THIS IS A SCRIPT AND NOT A ONE-LINER IN THE DOCKERFILE.
#
# The failure that cost several builds was NOT an ABI mismatch, despite looking
# exactly like one. Installing the wheel pulled its declared `torch` dependency,
# which has no upper bound, and pip quietly replaced the pinned torch 2.6.0+cu124
# with 2.13.0+cu130 -- so a wheel built for torch 2.6 could not resolve symbols in
# torch 2.13. Hence --no-deps below.
#
# The ABI loop stays because the correct variant still has to be chosen and torch's
# own _GLIBCXX_USE_CXX11_ABI flag cannot be trusted to pick it. An import is the
# only real proof, and on total failure this prints why rather than just "neither
# variant imports" -- an earlier version swallowed both errors into /dev/null and
# hid the torch version that turned out to be the actual bug.
#
# ⚠ flash-attn is not optional for speed. Measured on this exact model: with the
# SDPA fallback a 4.74s clip took 1471.8s (310x realtime); a hosted endpoint with
# flash-attn does the same work in 65-76s. Shipping without it silently produces
# an image that is ~20x too slow to use, which is why this script fails the build
# instead of warning.
set -u

VER="${FLASH_ATTN_VERSION:-2.8.3.post1}"
BASE="https://github.com/Dao-AILab/flash-attention/releases/download/v${VER}"

try_wheel() {
    local url="$1" label="$2"
    echo "===== trying ${label}"
    # ⚠ --no-deps IS LOAD-BEARING. The wheel declares `torch` with no upper bound,
    # so a plain install silently UPGRADED torch 2.6.0+cu124 -> 2.13.0+cu130, and a
    # wheel built for torch 2.6 then could not resolve symbols in torch 2.13. Every
    # "ABI mismatch" seen while debugging this was actually that: pip quietly
    # replacing the pinned torch underneath us. --force-reinstall made it worse.
    if ! pip3 install --no-cache-dir --no-deps "$url" >/tmp/pip.log 2>&1; then
        echo "----- pip install failed for ${label}:"
        tail -n 12 /tmp/pip.log
        return 1
    fi
    if python3 -c "import flash_attn; print('import ok, flash_attn', flash_attn.__version__)"; then
        echo "===== SUCCESS with ${label}"
        return 0
    fi
    echo "----- import failed for ${label} (traceback above)"
    return 1
}

for ABI in TRUE FALSE; do
    if try_wheel "${BASE}/flash_attn-${VER}+cu12torch2.6cxx11abi${ABI}-cp311-cp311-linux_x86_64.whl" \
                 "cxx11abi=${ABI}"; then
        exit 0
    fi
done

echo "===== no prebuilt wheel imported. diagnostics:"
python3 - <<'PY'
import os, torch
print("torch          :", torch.__version__)
print("torch.cuda     :", torch.version.cuda)
print("ABI flag says  :", torch._C._GLIBCXX_USE_CXX11_ABI)
lib = os.path.join(os.path.dirname(torch.__file__), "lib")
for so in ("libc10.so", "libtorch_cpu.so"):
    p = os.path.join(lib, so)
    if os.path.exists(p):
        # Ground truth: a cxx11-ABI build embeds the __cxx11 namespace marker.
        with open(p, "rb") as fh:
            print(f"{so:<16}: __cxx11 present ->", b"__cxx11" in fh.read())
PY
exit 1
