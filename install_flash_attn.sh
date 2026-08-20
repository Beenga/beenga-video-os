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

# ⚠ TRY A MATRIX, NOT A GUESS.
#
# Both ABI variants of 2.8.3.post1 failed on the SAME missing symbol --
#   c10::Error::Error(SourceLocation, std::__cxx11::string)
# -- so the variable is not the ABI, it is which torch build the wheel was
# compiled against. flash-attn publishes one "torch2.6" wheel per release, and
# those releases span months of torch patch releases, so the right one has to be
# found empirically. Each wheel is ~190MB and an import test takes seconds;
# testing the matrix in one build beats one guess per build.
VERSIONS="${FLASH_ATTN_VERSIONS:-2.7.4.post1 2.7.3 2.8.0.post2 2.8.1 2.8.2 2.8.3.post1}"

try_wheel() {
    local url="$1" label="$2"
    # ⚠ --no-deps IS LOAD-BEARING. The wheel declares `torch` with no upper bound,
    # so a plain install silently UPGRADED torch 2.6.0+cu124 -> 2.13.0+cu130, and a
    # wheel built for torch 2.6 then could not resolve symbols in torch 2.13. Every
    # "ABI mismatch" seen while debugging this was actually that.
    # ⚠ BOTH FLAGS ARE REQUIRED, FOR OPPOSITE REASONS.
    #   --force-reinstall : without it, pip sees flash_attn already installed at
    #                       this version and reports "already satisfied", so the
    #                       second ABI variant is never actually installed and
    #                       silently re-tests the first one.
    #   --no-deps         : without it, the wheel's unbounded `torch` dependency
    #                       upgrades torch 2.6.0 -> 2.13.0 underneath us.
    # Dropping either produces a confident-looking result that means nothing.
    pip3 uninstall -y flash_attn >/dev/null 2>&1 || true
    if ! pip3 install --no-cache-dir --no-deps --force-reinstall "$url" >/tmp/pip.log 2>&1; then
        echo "  ${label}: download/install failed"
        return 1
    fi
    if python3 -c "import flash_attn, flash_attn_2_cuda; print(flash_attn.__file__)" >/tmp/imp.log 2>&1; then
        echo "  ${label}: IMPORTS ($(head -1 /tmp/imp.log))"
        return 0
    fi
    echo "  ${label}: $(grep -oE 'undefined symbol: [_A-Za-z0-9]+' /tmp/imp.log | head -1 | cut -c1-70)"
    return 1
}

for VER in $VERSIONS; do
    BASE="https://github.com/Dao-AILab/flash-attention/releases/download/v${VER}"
    for ABI in TRUE FALSE; do
        URL="${BASE}/flash_attn-${VER}+cu12torch2.6cxx11abi${ABI}-cp311-cp311-linux_x86_64.whl"
        if try_wheel "$URL" "v${VER} abi=${ABI}"; then
            python3 -c "import flash_attn, torch; print('SELECTED flash_attn', flash_attn.__version__, 'against torch', torch.__version__)"
            exit 0
        fi
    done
done

echo "===== no prebuilt wheel imported against this torch. diagnostics:"
python3 - <<'PYEOF'
import os, torch
print("torch          :", torch.__version__)
print("torch.cuda     :", torch.version.cuda)
print("ABI flag says  :", torch._C._GLIBCXX_USE_CXX11_ABI)
lib = os.path.join(os.path.dirname(torch.__file__), "lib")
for so in ("libc10.so", "libtorch_cpu.so"):
    p = os.path.join(lib, so)
    if os.path.exists(p):
        with open(p, "rb") as fh:
            print(f"{so:<16}: __cxx11 present ->", b"__cxx11" in fh.read())
PYEOF
exit 1
