#!/usr/bin/env bash
# Install flash-attn from a prebuilt wheel, proving it works by importing it.
#
# ⚠ WHY THIS IS A SCRIPT AND NOT A ONE-LINER IN THE DOCKERFILE.
#
# Selecting the wheel is not as simple as reading torch's ABI flag.
# torch._C._GLIBCXX_USE_CXX11_ABI reported FALSE, and the FALSE wheel then failed
# with `undefined symbol: _ZN3c105ErrorC2ENS_14SourceLocation NSt7__cxx1112basic_string...`
# -- a request for __cxx11 strings, i.e. the opposite of what the flag claimed.
# The flag does not reliably describe how libtorch was actually compiled.
#
# So: try each variant, and let an import decide. If none work, print enough to
# diagnose it rather than failing with "neither variant imports", which is what
# an earlier version did after swallowing both errors into /dev/null.
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
    if ! pip3 install --no-cache-dir --force-reinstall "$url" >/tmp/pip.log 2>&1; then
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
