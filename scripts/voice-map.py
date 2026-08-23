#!/usr/bin/env python3
"""Map which singer holds each moment of a vocal stem.

⚠ WHY THIS EXISTS.

Stem separators split by ROLE, not by SINGER. A "Lead Vocals" stem from a duet
contains both voices in one file. Driving a lip-sync model with it makes whoever
is on screen mouth the other singer's lines — which is exactly what happened on
shot 14: the woman's lips moved through a male phrase at the top and tail of the
slice.

So before any lip-sync render, the stem is segmented by fundamental frequency.
Typical sung F0: male ~85-180 Hz, female ~165-400 Hz. The overlap around
165-180 Hz is real, so the band is treated as ambiguous rather than forced.

Output is a JSON map of [start, end, voice] that shot slicing can be checked
against, so a shot is only lip-synced where the on-screen singer is the one
actually singing.
"""
import json
import subprocess
import sys
import wave

import numpy as np

SR = 16000
WIN = 0.10          # 100 ms analysis window
MIN_SEG = 0.40      # ignore flickers shorter than this
SILENCE_RMS = 0.006  # below this, nobody is singing

# F0 bands. The 165-180 Hz overlap is left ambiguous on purpose.
MALE_MAX = 165.0
FEMALE_MIN = 180.0


def load(path):
    with wave.open(path, "rb") as w:
        n = w.getnframes()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return x


def f0_autocorr(frame, sr=SR, fmin=70, fmax=450):
    """Autocorrelation pitch estimate. Crude but adequate for male/female split."""
    frame = frame - frame.mean()
    if np.sqrt((frame ** 2).mean()) < SILENCE_RMS:
        return 0.0
    w = frame * np.hanning(len(frame))
    corr = np.correlate(w, w, mode="full")[len(w) - 1:]
    lo, hi = int(sr / fmax), int(sr / fmin)
    if hi >= len(corr):
        return 0.0
    seg = corr[lo:hi]
    if not len(seg) or corr[0] <= 0:
        return 0.0
    lag = int(np.argmax(seg)) + lo
    # Reject weak periodicity — unvoiced or noise.
    if corr[lag] / corr[0] < 0.30:
        return 0.0
    return sr / lag


def classify(f):
    if f == 0.0:
        return "silence"
    if f <= MALE_MAX:
        return "male"
    if f >= FEMALE_MIN:
        return "female"
    return "ambiguous"


def main(path, out):
    x = load(path)
    step = int(SR * WIN)
    labels = []
    for i in range(0, len(x) - step, step):
        labels.append((i / SR, classify(f0_autocorr(x[i:i + step]))))

    # Collapse into runs, dropping segments too short to matter.
    segs = []
    cur_lab, cur_start = labels[0][1], 0.0
    for t, lab in labels[1:] + [(len(x) / SR, None)]:
        if lab != cur_lab:
            if t - cur_start >= MIN_SEG:
                segs.append({"start": round(cur_start, 2), "end": round(t, 2),
                             "voice": cur_lab})
            elif segs:
                segs[-1]["end"] = round(t, 2)   # absorb the flicker
            cur_lab, cur_start = lab, t
    json.dump(segs, open(out, "w"), indent=2)

    tot = {}
    for s in segs:
        tot[s["voice"]] = tot.get(s["voice"], 0) + (s["end"] - s["start"])
    print("segments:", len(segs))
    for k in ("female", "male", "ambiguous", "silence"):
        if k in tot:
            print("  %-10s %6.1fs" % (k, tot[k]))
    print("\nfemale-only windows of 4s or more (usable for her lip sync):")
    for s in segs:
        if s["voice"] == "female" and s["end"] - s["start"] >= 4.0:
            print("  %6.2f - %6.2f  (%.1fs)" % (s["start"], s["end"], s["end"] - s["start"]))
    print("\nwrote", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
