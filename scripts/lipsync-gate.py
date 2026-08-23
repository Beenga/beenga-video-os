#!/usr/bin/env python3
"""Decide automatically whether a song can be lip-synced by ONE on-screen singer.

⚠ THIS ANSWERS A DIFFERENT QUESTION THAN THE ONE THAT FAILED.

Three attempts were made to label each moment as male or female so shots could be
cut to whoever was singing. All three failed, and one came out anti-correlated
with what a listener actually heard. The reason turned out to be structural: in a
harmony duet BOTH singers are present in almost every frame, so "which singer is
this?" has no answer to find.

The product does not need that answer. It needs to know whether a single animated
face can carry the track at all. That is a song-level decision, it is stable, and
it is measurable: count frames containing two independent simultaneous pitches.

  mostly one pitch  -> solo vocal      -> lip sync is safe
  many two-pitch    -> harmony duet    -> a single face would mouth a blend of two
                                          voices; skip lip sync, animate instead
  little pitch      -> instrumental    -> nothing to sync to

⚠ KNOWN LIMITATION, STATED RATHER THAN HIDDEN.

Stem separators leak instruments into the vocal track, and a sustained guitar or
synth note under a voice looks like a second singer. So `duet_ratio` is an upper
bound. It is used only to gate an all-or-nothing decision with a wide margin,
which is exactly the kind of call that tolerates a noisy input — unlike per-frame
labelling, which does not.
"""
import json
import subprocess
import sys
import tempfile
import wave

import numpy as np

SR = 16000
FRAME = 0.40
HOP = 0.20
SILENCE_RMS = 0.006
PEAK_MIN = 0.18          # harmonic-series strength to count as a pitch at all
SECOND_REL = 0.60        # second pitch must be this strong relative to the first
DUET_THRESHOLD = 0.35    # fraction of voiced frames with two pitches
VOICED_MIN = 0.15        # below this the track is effectively instrumental


def to_wav(path):
    tmp = tempfile.mktemp(suffix=".wav")
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-i", path,
                    "-ar", str(SR), "-ac", "1", "-y", tmp], check=True)
    return tmp


def load(path):
    with wave.open(path, "rb") as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return x.astype(np.float32) / 32768.0


def pitches(seg):
    """Up to two independent fundamentals, ignoring harmonic relatives of each other."""
    win = seg * np.hanning(len(seg))
    n = 1 << (len(win) - 1).bit_length() << 2
    sp = np.abs(np.fft.rfft(win, n))
    if sp.max() <= 0:
        return []
    sp = sp / sp.max()
    fq = np.fft.rfftfreq(n, 1 / SR)

    def strength(f0):
        s = 0.0
        for h in range(1, 7):
            f = f0 * h
            if f > 4000:
                break
            j = int(np.argmin(np.abs(fq - f)))
            s += sp[max(0, j - 2):j + 3].max()
        return s / 6

    cand = np.arange(80, 420, 2.0)
    sc = np.array([strength(f) for f in cand])
    out = []
    for i in range(2, len(sc) - 2):
        if sc[i] == max(sc[i - 2:i + 3]) and sc[i] > PEAK_MIN:
            # reject anything that is a near-integer multiple/divisor of a kept peak
            if all(abs(cand[i] / p - round(cand[i] / p)) > 0.06 and
                   abs(p / cand[i] - round(p / cand[i])) > 0.06 for p, _ in out):
                out.append((cand[i], sc[i]))
    out.sort(key=lambda t: -t[1])
    return out[:2]


def analyse(path):
    x = load(to_wav(path))
    fl, hp = int(SR * FRAME), int(SR * HOP)
    voiced = duet = total = 0
    for i in range(0, len(x) - fl, hp):
        total += 1
        seg = x[i:i + fl]
        if np.sqrt((seg ** 2).mean()) < SILENCE_RMS:
            continue
        p = pitches(seg)
        if not p:
            continue
        voiced += 1
        if len(p) == 2 and p[1][1] > SECOND_REL * p[0][1]:
            duet += 1

    voiced_ratio = voiced / max(total, 1)
    duet_ratio = duet / max(voiced, 1)

    if voiced_ratio < VOICED_MIN:
        verdict, reason = "instrumental", "little sustained pitch — nothing to lip-sync to"
    elif duet_ratio >= DUET_THRESHOLD:
        verdict, reason = ("duet",
                           f"{duet_ratio:.0%} of voiced frames contain two simultaneous "
                           "pitches — one face would mouth a blend of two voices")
    else:
        verdict, reason = "solo", f"only {duet_ratio:.0%} two-pitch frames — a single singer carries it"

    return {"file": path, "verdict": verdict, "reason": reason,
            "voiced_ratio": round(voiced_ratio, 3), "duet_ratio": round(duet_ratio, 3),
            "lipsync_ok": verdict == "solo"}


if __name__ == "__main__":
    res = [analyse(p) for p in sys.argv[1:]]
    for r in res:
        print("%-46s %-12s lipsync=%-5s  (voiced %.2f, duet %.2f)"
              % (r["file"].split("/")[-1], r["verdict"], r["lipsync_ok"],
                 r["voiced_ratio"], r["duet_ratio"]))
        print("    %s" % r["reason"])
    print(json.dumps(res, indent=2)[:0])
