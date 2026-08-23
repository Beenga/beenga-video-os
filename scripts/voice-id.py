#!/usr/bin/env python3
"""Identify which singer holds each moment of a vocal stem.

⚠ WHY THE FIRST ATTEMPT FAILED.

voice-map.py used plain autocorrelation, which suffers OCTAVE ERRORS: it happily
locks onto half the true fundamental. Its "male" frames came back at 146/164/168 Hz
while its "female" frames sat at 296/327/336 Hz — almost exactly double. So an
unknown share of the male detections were her, measured an octave low. Worse, the
answer changed with window size, which is the signature of an unstable estimator
rather than a real signal.

This version does three things differently:

1. Harmonic Product Spectrum instead of autocorrelation. Multiplying downsampled
   copies of the spectrum reinforces the true fundamental and suppresses the
   half-frequency peak that fools autocorrelation.
2. Explicit octave check. If a candidate f0 has strong energy at 2*f0, the higher
   one wins — the specific failure above.
3. Hysteresis and median smoothing over time. A singer does not change sex for
   250ms; isolated flips are estimator noise and get voted out by their neighbours.

Output is per-frame (time, f0, label) plus merged runs, so shot windows can be
chosen around who is actually singing.
"""
import json
import subprocess
import sys
import wave

import numpy as np

SR = 16000
FRAME = 0.25          # analysis frame
HOP = 0.125           # 50% overlap so short phrases are not missed
SILENCE_RMS = 0.006
MEDIAN_W = 5          # frames; smooths estimator noise without erasing 0.6s phrases

# Sung ranges overlap in the 165-200 Hz region, so that band is left ambiguous
# rather than forced into a decision.
MALE_MAX = 165.0
FEMALE_MIN = 200.0


def load(path):
    with wave.open(path, "rb") as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return x.astype(np.float32) / 32768.0


def hps_f0(frame, sr=SR, fmin=70.0, fmax=500.0, harmonics=5):
    """Harmonic Product Spectrum with an explicit octave-doubling check."""
    if np.sqrt((frame ** 2).mean()) < SILENCE_RMS:
        return 0.0
    w = frame * np.hanning(len(frame))
    n = 1 << (len(w) - 1).bit_length() << 2      # zero-pad for finer bin spacing
    spec = np.abs(np.fft.rfft(w, n))
    if spec.max() <= 0:
        return 0.0
    spec /= spec.max()

    hps = spec.copy()
    for h in range(2, harmonics + 1):
        dec = spec[::h]
        hps[:len(dec)] *= dec

    freqs = np.fft.rfftfreq(n, 1 / sr)
    lo = np.searchsorted(freqs, fmin)
    hi = np.searchsorted(freqs, fmax)
    if hi <= lo:
        return 0.0
    idx = lo + int(np.argmax(hps[lo:hi]))
    f0 = float(freqs[idx])

    # ⚠ THE OCTAVE CHECK. If there is comparable energy an octave up, the estimate
    # is the half-frequency artefact that made voice-map.py call her him.
    up = 2 * f0
    if up <= fmax:
        j = int(np.argmin(np.abs(freqs - up)))
        band = slice(max(0, j - 3), j + 4)
        if spec[band].max() > 0.6 * spec[max(0, idx - 3):idx + 4].max():
            f0 = up
    return f0


def label(f):
    if f == 0.0:
        return "-"
    if f <= MALE_MAX:
        return "M"
    if f >= FEMALE_MIN:
        return "F"
    return "?"


def main(path, out_json):
    x = load(path)
    fl, hp = int(SR * FRAME), int(SR * HOP)
    times, f0s = [], []
    for i in range(0, len(x) - fl, hp):
        times.append(i / SR)
        f0s.append(hps_f0(x[i:i + fl]))

    labs = [label(f) for f in f0s]

    # Median vote over neighbours: a singer does not change sex for one frame.
    smooth = []
    for i in range(len(labs)):
        win = labs[max(0, i - MEDIAN_W // 2): i + MEDIAN_W // 2 + 1]
        voiced = [v for v in win if v in ("M", "F")]
        if not voiced:
            smooth.append("-")
        else:
            smooth.append(max(set(voiced), key=voiced.count))

    runs, cur, st = [], smooth[0], times[0]
    for t, l in list(zip(times[1:], smooth[1:])) + [(len(x) / SR, None)]:
        if l != cur:
            runs.append({"start": round(st, 2), "end": round(t, 2), "voice": cur})
            cur, st = l, t

    json.dump({"frames": [{"t": round(t, 3), "f0": round(f, 1), "voice": v}
                          for t, f, v in zip(times, f0s, smooth)],
               "runs": runs}, open(out_json, "w"), indent=2)

    tot = {}
    for r in runs:
        tot[r["voice"]] = tot.get(r["voice"], 0) + (r["end"] - r["start"])
    print("totals:", {k: round(v, 1) for k, v in tot.items()})
    print("\nruns of 1.5s or more:")
    for r in runs:
        d = r["end"] - r["start"]
        if d >= 1.5:
            print("  %6.2f - %6.2f  %s  (%.1fs)" % (r["start"], r["end"], r["voice"], d))
    print("\nwrote", out_json)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
