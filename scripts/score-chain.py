#!/usr/bin/env python3
"""Score a chained generation: do the clips JOIN, and does the singer stay one person?

    ./.venv/bin/python scripts/score-chain.py out/chain6
    ./.venv/bin/python scripts/score-chain.py out/chain6 out/anchor6      # compare

Two numbers, because the two strategies fail in opposite ways and a single score
would hide that.

  JOIN COST     How big a visual step the seam is, expressed as a MULTIPLE of the
                clip's own natural frame-to-frame step. A join of 1.0 is
                indistinguishable from an ordinary frame advance. A join of 8.0 is
                a cut. Reported as a multiple rather than raw pixels because clips
                differ in how much they move, and a fast clip has a bigger natural
                step through no fault of the seam.

  IDENTITY DRIFT  CSIM of each clip against the ORIGINAL still, not against the
                previous clip. Comparing neighbours would report every step as
                small while the chain walked away from the starting face — the
                classic way compounding drift hides from a per-step metric.

Expected shapes, worth writing down before looking so the result can contradict them:

  anchor   join cost HIGH (every clip restarts from the same pose), drift FLAT
  chain    join cost LOW (the seam is the conditioning image), drift RISING

If chain's drift stays flat, chaining wins outright. If anchor's join cost is not
actually high, anchoring wins outright and the whole question was cheap to settle.
"""
import json
import os
import statistics
import sys

try:
    from PIL import Image
    import numpy as np
except ImportError:
    sys.exit("needs Pillow and numpy:  pip install Pillow numpy")


def gray(path, size=(160, 96)):
    return np.asarray(Image.open(path).convert("L").resize(size), dtype=float)


def step(a, b):
    return float(np.mean(np.abs(a - b)))


def natural_step(clip_dir, rec, n_samples=6):
    """Typical frame-to-frame change inside a clip, from its own frames.

    Uses ffmpeg to pull a handful of consecutive frames rather than trusting the
    first/last pair already on disk — the seam is what we are measuring against,
    so the baseline must come from somewhere other than the seam."""
    import subprocess, tempfile, glob, shutil
    d = tempfile.mkdtemp(prefix="chainstep-")
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-i", os.path.join(clip_dir, rec["file"]),
                        "-frames:v", str(n_samples + 1), os.path.join(d, "f%02d.png")], check=True)
        fs = sorted(glob.glob(os.path.join(d, "*.png")))
        if len(fs) < 2:
            return None
        gs = [gray(f) for f in fs]
        return statistics.median(step(a, b) for a, b in zip(gs, gs[1:]))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def load_face_model():
    try:
        from insightface.app import FaceAnalysis
    except ImportError:
        return None
    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(640, 640))
    return app


def embed(app, path):
    faces = app.get(np.asarray(Image.open(path).convert("RGB"))[:, :, ::-1])
    if not faces:
        return None
    def area(f):
        x1, y1, x2, y2 = f.bbox
        return (x2 - x1) * (y2 - y1)
    return max(faces, key=area).normed_embedding


def score(directory, app):
    rec = json.load(open(os.path.join(directory, "chain.json")))
    clips = rec["clips"]
    root = os.path.dirname(os.path.abspath(directory.rstrip("/")))
    still = os.path.join(os.path.dirname(root), rec["still"]) if False else \
            os.path.join(os.path.abspath(os.path.join(directory, "..", "..")), rec["still"])

    # ── joins ────────────────────────────────────────────────────────────────
    joins = []
    for a, b in zip(clips, clips[1:]):
        last = gray(os.path.join(directory, a["last"]))
        first = gray(os.path.join(directory, b["first"]))
        raw = step(last, first)
        base = natural_step(directory, a)
        joins.append({
            "from": a["i"], "to": b["i"],
            "raw": round(raw, 2),
            "natural": round(base, 2) if base else None,
            "cost": round(raw / base, 2) if base and base > 1e-6 else None,
        })

    # ── identity drift against the ORIGINAL still ────────────────────────────
    drift = []
    if app is not None and os.path.exists(still):
        ref = embed(app, still)
        if ref is not None:
            for c in clips:
                e = embed(app, os.path.join(directory, c["last"]))
                drift.append({"clip": c["i"],
                              "csim_vs_still": round(float(np.dot(ref, e)), 3) if e is not None else None})

    return rec, joins, drift


def report(directory, rec, joins, drift):
    print(f"\n=== {directory}  (mode={rec['mode']}, {len(rec['clips'])} clips) ===")
    costs = [j["cost"] for j in joins if j["cost"] is not None]
    print("joins (seam step as a multiple of the clip's own natural frame step):")
    for j in joins:
        flag = "" if j["cost"] is None else ("  smooth" if j["cost"] < 2 else
               "  visible" if j["cost"] < 5 else "  HARD CUT")
        print(f"  {j['from']}→{j['to']}   raw {j['raw']:>6}   natural {str(j['natural']):>6}   "
              f"cost x{j['cost']}{flag}")
    if costs:
        print(f"  median join cost  x{statistics.median(costs):.2f}")

    if drift:
        vals = [d["csim_vs_still"] for d in drift if d["csim_vs_still"] is not None]
        print("identity vs the ORIGINAL still:")
        print("  " + "  ".join(f"c{d['clip']}={d['csim_vs_still']}" for d in drift))
        # ⚠ NEVER report first-vs-last on a re-anchored run. Its identity series is a
        # sawtooth — anchored clips high, chained clips low — so c0 against cN
        # compares an anchored clip to a chained one and prints a decline for a
        # series that is stable. Group by conditioning source instead: if each
        # group is flat, drift is bounded, which is the property that matters.
        anchored, chained = [], []
        for c, dd in zip(rec["clips"], drift):
            if dd["csim_vs_still"] is None:
                continue
            (anchored if c["conditioning"] == os.path.basename(rec["still"]) else chained
             ).append(dd["csim_vs_still"])
        # ⚠ TREND IS FIRST-THIRD MEAN vs LAST-THIRD MEAN, not first value vs last.
        # This is the second time a naive endpoint difference misled on this data.
        # On the 36-clip run the anchored series oscillates between 0.745 and 0.901
        # with no slope, and first-minus-last happened to land on -0.114 — which
        # reads as steady decline for a series whose two halves have identical
        # means. Endpoints are single samples; on a noisy series they measure noise.
        for name, grp in (("from still", anchored), ("from prev clip", chained)):
            if not grp:
                continue
            if len(grp) >= 6:
                k = max(2, len(grp) // 3)
                head, tail = statistics.mean(grp[:k]), statistics.mean(grp[-k:])
                trend = f"{tail - head:+.3f}  (first {k} mean {head:.3f} → last {k} mean {tail:.3f})"
            else:
                trend = "— too few clips to trend"
            print(f"  {name:<15} n={len(grp)}  min {min(grp):.3f}  max {max(grp):.3f}   trend {trend}")
        if chained:
            print(f"  worst clip {min(chained + anchored):.3f} "
                  f"({'above' if min(chained + anchored) > 0.6 else 'BELOW'} the ~0.6 same-person line)")
    else:
        print("identity: not scored (insightface missing or no face found)")


def main(dirs):
    app = load_face_model()
    if app is None:
        print("note: insightface not installed — joins only, no identity drift.\n")
    out = {}
    for d in dirs:
        rec, joins, drift = score(d, app)
        report(d, rec, joins, drift)
        out[d] = {"mode": rec["mode"], "joins": joins, "drift": drift}
        json.dump(out[d], open(os.path.join(d, "chain-scores.json"), "w"), indent=2)
    if len(dirs) == 2:
        print("\nthe trade-off, side by side:")
        for d in dirs:
            cs = [j["cost"] for j in out[d]["joins"] if j["cost"] is not None]
            ds = [x["csim_vs_still"] for x in out[d]["drift"] if x["csim_vs_still"] is not None]
            med = f"x{statistics.median(cs):.2f}" if cs else "—"
            dd = f"{ds[-1] - ds[0]:+.3f}" if len(ds) >= 2 else "—"
            print(f"  {out[d]['mode']:<7} median join {med:>7}   identity change over chain {dd}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip().split("\n")[0])
    main(sys.argv[1:])
