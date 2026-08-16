#!/usr/bin/env python3
"""Measure what can be measured in a benchmark run, instead of eyeballing it.

    python3 scripts/score-clips.py out/base-5b
    python3 scripts/score-clips.py out/base-5b --metric luma

Three instruments, in descending order of how much I trust them:

  LUMA TREND      does a requested complexion drift lighter across the clip?
                  Needs only ffmpeg and Pillow. Runs today.

  CSIM            does the face stay the same person — within a clip, and across
                  separately generated clips? Needs a face embedding model.
                  Degrades to a clear "not installed" rather than a wrong number.

  LSE-C / LSE-D   lip-sync accuracy. Needs a SyncNet checkout and checkpoint;
                  see the note at the bottom. Deliberately NOT reimplemented here.

WHY THIS FILE EXISTS AT ALL. The central claim of this project is a measurement, so
the scoring should be one too. beenga-image scored complexion by median Rec.709 luma
rather than by eye, and that instrument is what overturned a wrong conclusion about
whether complexion was a weights problem. The same logic applies here, with one
difference that matters: video adds a time axis, so the useful question is rarely
"what is the value" and almost always "does the value drift".

WHAT THESE NUMBERS ARE NOT. None of them are calibrated against any external scale.
Do not quote them as absolutes. What is meaningful is:

  * the ORDERING between arms or models on the same case, and
  * the TREND across frames within one clip.

Two caveats to keep in view, both of which limit what can honestly be claimed:

  * Luma reads a fixed crop of the frame. It assumes a roughly centred subject on a
    plain-ish background. On a wide shot or a moving subject it is measuring the
    background as much as the face, and the number is noise. Check the extracted
    frames before trusting a luma result on anything but a portrait framing.

  * SyncNet, when wired up, is itself trained on LRS2 — which is English. LSE-C on
    Hindi singing is a biased instrument measuring the exact thing whose bias is
    under test. Use it to order arms A/B/C against each other; never quote it as an
    absolute, and validate against human scoring on a sample.
"""
import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile

try:
    from PIL import Image
except ImportError:
    sys.exit("needs Pillow:  pip install Pillow")


# ── frame extraction ─────────────────────────────────────────────────────────

def extract_frames(clip, every_n=6, limit=40):
    """Decode a clip to PNG frames in a temp dir. Every 6th frame at 16fps is
    ~2.7 samples/second, which is enough to see a trend without decoding 80 frames
    of a 5-second clip."""
    if not shutil.which("ffmpeg"):
        sys.exit("needs ffmpeg on PATH")
    d = tempfile.mkdtemp(prefix="beenga-frames-")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", clip,
         "-vf", f"select=not(mod(n\\,{every_n}))", "-vsync", "vfr",
         "-frames:v", str(limit), os.path.join(d, "f%03d.png")],
        check=True,
    )
    return d, sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".png"))


# ── instrument 1: luma trend ─────────────────────────────────────────────────

def _median_luma(im):
    lum = sorted(0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in im.getdata())
    return lum[len(lum) // 2]


def skin_luma(path):
    """Median Rec.709 luma of the upper-centre crop, AND of the whole frame.

    Median rather than mean so hair, background and specular highlights cannot drag
    the figure around. Same crop box as beenga-image/scripts/score-complexion.py so
    values are loosely comparable between the two suites.

    THE SECOND VALUE IS WHY THIS FUNCTION CHANGED. The first version returned skin
    luma alone, and on the first real run all three complexion cases drifted darker
    by an amount that scaled with their brightness — the signature of the whole shot
    dimming, not of complexion drifting. Raw skin luma cannot tell those apart. The
    frame median is a proxy for scene exposure, so the RATIO of the two isolates the
    subject from the lighting. Still not a calibrated skin-tone measure; it is a
    drift detector that no longer fires on a fade to dusk."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    face = im.crop((int(w * 0.38), int(h * 0.18), int(w * 0.62), int(h * 0.42)))
    # Downsample the full frame before taking its median — this runs per frame and
    # the median of ~800k pixels is the slowest thing in the script.
    return _median_luma(face), _median_luma(im.resize((w // 6, h // 6)))


def luma_trend(frames):
    """Per-frame luma plus a first-half/second-half delta.

    A positive delta means the subject got LIGHTER over the clip, which for a case
    that requested a deep complexion is the failure we are looking for. Reported
    alongside the spread, because a delta smaller than the frame-to-frame noise is
    not a finding."""
    pairs = [skin_luma(f) for f in frames]
    if len(pairs) < 4:
        return {"n": len(pairs), "note": "too few frames to trend"}

    raw = [s for s, _ in pairs]
    # Normalised: skin relative to scene exposure. This is the number to trend.
    norm = [s / g if g > 1 else 0.0 for s, g in pairs]

    half = len(pairs) // 2
    d_raw = statistics.median(raw[half:]) - statistics.median(raw[:half])
    d_norm = statistics.median(norm[half:]) - statistics.median(norm[:half])
    spread_norm = statistics.pstdev(norm)

    return {
        "n": len(pairs),
        "skin_median": round(statistics.median(raw), 1),
        "scene_median": round(statistics.median([g for _, g in pairs]), 1),
        "raw_delta": round(d_raw, 1),
        # ratio of skin luma to scene luma — drift here is drift in the SUBJECT
        "norm_first": round(statistics.median(norm[:half]), 3),
        "norm_second": round(statistics.median(norm[half:]), 3),
        "norm_delta": round(d_norm, 3),
        "norm_spread": round(spread_norm, 3),
        # A delta inside the noise floor is not evidence of drift in either direction.
        "significant": abs(d_norm) > spread_norm,
    }


# ── instrument 2: CSIM ───────────────────────────────────────────────────────

def load_face_model():
    """InsightFace if present. Returns None rather than guessing.

    A wrong identity number is worse than no identity number: it would be quoted."""
    try:
        from insightface.app import FaceAnalysis
    except ImportError:
        return None
    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(640, 640))
    return app


def embed(app, path):
    """Embed the LARGEST face in the frame, and report how many were found.

    The first version picked the highest det_score face. On VID-MOT-005 — four
    people dancing — that silently switched subject between frames, so the
    "identity drift" number was measuring which face the detector liked best that
    frame, not whether one person stayed one person. Largest-by-area is stable for
    a foreground subject; the face count is returned so multi-person clips can be
    excluded rather than quietly mis-scored."""
    import numpy as np
    faces = app.get(np.asarray(Image.open(path).convert("RGB"))[:, :, ::-1])
    if not faces:
        return None, 0
    def area(f):
        x1, y1, x2, y2 = f.bbox
        return (x2 - x1) * (y2 - y1)
    return max(faces, key=area).normed_embedding, len(faces)


def csim_intra(app, frames):
    """Identity stability WITHIN one clip: every frame against the first.

    Returns `interpretable: False` when the clip cannot support an identity claim.
    A raw cosine number here is easy to over-read: a low value can mean genuine
    drift, but it can equally mean the subject turned away, the shot is wide enough
    that the face is a few dozen pixels, or more than one person is in frame. Those
    are flagged rather than averaged away, because the failure mode this project
    keeps hitting is a number that looks authoritative and means something else."""
    import numpy as np
    got = [embed(app, f) for f in frames]
    embs = [e for e, _ in got if e is not None]
    counts = [n for _, n in got]
    multi = sum(1 for n in counts if n > 1)

    # ⚠ NO FACE IS A FINDING, NOT A GAP.
    #
    # out/dance-s77/VID-DANCE-001.mp4 renders a seated figure framed at the
    # collarbone: torso, arms, crossed legs, no head, for the whole clip. The first
    # version of this function returned "cannot score" for it, so a MODEL failure
    # was filed as a MEASUREMENT failure and dropped out of the results entirely.
    # Biren caught it by eye; the scorer had looked straight past it.
    #
    # A clip that asked for a person and contains no detectable face is a headless
    # or out-of-frame render. For a music video that is unusable regardless of
    # anything else, so it is escalated rather than skipped.
    if len(embs) == 0:
        return {"interpretable": False, "FINDING": "NO_FACE_IN_CLIP",
                "note": f"no face detected in any of {len(frames)} sampled frames — "
                        f"headless or out-of-frame render, not a scoring gap"}
    if len(embs) < 2:
        return {"interpretable": False, "FINDING": "FACE_MOSTLY_ABSENT",
                "note": f"face found in only {len(embs)}/{len(frames)} frames"}

    ref = embs[0]
    sims = [float(np.dot(ref, e)) for e in embs[1:]]
    detected_ratio = len(embs) / len(frames)

    caveats = []
    if multi > len(frames) * 0.25:
        caveats.append(f"multiple faces in {multi}/{len(frames)} frames — subject may switch")
    if detected_ratio < 0.8:
        caveats.append(f"face detected in only {len(embs)}/{len(frames)} frames")

    return {
        "interpretable": not caveats,
        "caveats": caveats,
        "n": len(embs),
        "mean": round(statistics.mean(sims), 3),
        "min": round(min(sims), 3),
        "detected_in": f"{len(embs)}/{len(frames)}",
        "max_faces": max(counts) if counts else 0,
    }


def mouth_activity(app, frames):
    """Is the mouth moving, and does it stop when the audio does?

    Added after Biren watched the first arm C reel: "when simply music was in the
    end, still mouth movement was there." S2V appears to drive articulation from
    audio ENERGY rather than from vocal content, which is fatal for a music video —
    every song has an intro, a break and an outro with no vocal in them.

    Measured as frame-to-frame change in the mouth region, NORMALISED by change in
    the whole face crop. The normalisation is the important part: a turning head
    moves every pixel in the mouth region without the mouth doing anything, and an
    un-normalised number would read that as speech. The ratio isolates articulation
    from pose, the same way the luma instrument divides skin by scene exposure.

    Reports first half against second half, because the probes are built as
    "vocal, then not vocal". A clip that stops articulating gives second_half well
    below first_half. A clip that mouths through silence gives a ratio near 1.
    """
    import numpy as np
    mouths, faces = [], []
    for f in frames:
        im = Image.open(f).convert("L")
        arr = np.asarray(im)
        det = app.get(np.asarray(Image.open(f).convert("RGB"))[:, :, ::-1])
        if not det:
            mouths.append(None); faces.append(None); continue
        b = max(det, key=lambda d: (d.bbox[2] - d.bbox[0]) * (d.bbox[3] - d.bbox[1])).bbox
        x1, y1, x2, y2 = [int(v) for v in b]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(arr.shape[1], x2), min(arr.shape[0], y2)
        if x2 - x1 < 20 or y2 - y1 < 20:
            mouths.append(None); faces.append(None); continue
        h = y2 - y1
        # Lower third of the face box, middle 60% horizontally — the mouth.
        my1, my2 = y1 + int(h * 0.62), y1 + int(h * 0.95)
        mx1 = x1 + int((x2 - x1) * 0.20); mx2 = x1 + int((x2 - x1) * 0.80)
        m = np.asarray(Image.fromarray(arr[my1:my2, mx1:mx2]).resize((64, 32)), dtype=float)
        fc = np.asarray(Image.fromarray(arr[y1:y2, x1:x2]).resize((64, 64)), dtype=float)
        mouths.append(m); faces.append(fc)

    def diffs(seq):
        out = []
        for a, b in zip(seq, seq[1:]):
            out.append(float(np.mean(np.abs(a - b))) if a is not None and b is not None else None)
        return out

    md, fd = diffs(mouths), diffs(faces)
    ratio = [m / f if (m is not None and f is not None and f > 1e-6) else None
             for m, f in zip(md, fd)]
    ratio = [r for r in ratio if r is not None]
    if len(ratio) < 6:
        return {"interpretable": False, "note": f"only {len(ratio)} usable frame pairs"}

    half = len(ratio) // 2
    first, second = statistics.median(ratio[:half]), statistics.median(ratio[half:])
    return {
        "interpretable": True,
        "n": len(ratio),
        "first_half": round(first, 3),
        "second_half": round(second, 3),
        "overall": round(statistics.median(ratio), 3),
        # Raw ratio is reported but must NOT be read on its own — see calibrate().
        "drop_ratio_raw": round(second / first, 3) if first > 1e-6 else None,
    }


def calibrate(rows, floor):
    """Re-express mouth activity as EXCESS OVER A MEASURED FLOOR.

    ⚠ THIS FUNCTION EXISTS BECAUSE THE RAW RATIO IS MISLEADING, and it was read
    that way once before it was caught. The metric never reaches zero: a generated
    face blinks, breathes and shifts, so the mouth region always changes. Measured
    on VID-SING-012 — five seconds of total digital silence, neutral prompt — the
    floor is about 1.2, not 0.

    Against that floor a raw second-half value of 1.40 is not "still articulating",
    it is 0.17 above a floor of 1.23 when the vocal half sat 0.65 above it. The raw
    ratio said 0.75 and read as "barely dropped"; the calibrated one says 0.26 and
    reads as "largely stopped". Opposite conclusions from the same numbers.

    So: never quote drop_ratio_raw. Quote excess_ratio, and only when a floor clip
    was generated in the same run on the same model."""
    out = {}
    for r in rows:
        m = r.get("mouth")
        if not m or not m.get("interpretable"):
            continue
        e1 = max(0.0, m["first_half"] - floor)
        e2 = max(0.0, m["second_half"] - floor)
        out[r["id"]] = {
            "excess_first": round(e1, 3),
            "excess_second": round(e2, 3),
            "excess_ratio": round(e2 / e1, 3) if e1 > 1e-3 else None,
            # Below 0.5 of its own first half = articulation clearly fell away.
            "largely_stopped": bool(e1 > 1e-3 and (e2 / e1) < 0.5),
        }
    return out


def csim_inter(app, clips):
    """Identity stability ACROSS separately generated clips.

    This is the one that matters for a music video and the one nobody reports.
    Drift within a clip is usually fine; drift between the clips you stitch into a
    song is what makes it obviously synthetic. Compares each clip's middle frame."""
    import numpy as np
    refs = []
    for c in clips:
        d, frames = extract_frames(c, every_n=12, limit=8)
        try:
            mid = frames[len(frames) // 2] if frames else None
            e = embed(app, mid)[0] if mid else None
            if e is not None:
                refs.append((os.path.basename(c), e))
        finally:
            shutil.rmtree(d, ignore_errors=True)
    if len(refs) < 2:
        return {"note": f"usable faces in {len(refs)} clips — cannot compare"}
    sims = []
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            sims.append(float(np.dot(refs[i][1], refs[j][1])))
    return {
        "clips": [r[0] for r in refs],
        "pairs": len(sims),
        "mean": round(statistics.mean(sims), 3),
        "min": round(min(sims), 3),
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("directory", help="an out/<tag> directory containing runs.json and .mp4 files")
    p.add_argument("--metric", choices=["all", "luma", "csim"], default="all")
    p.add_argument("--every-n", type=int, default=6, help="sample every Nth frame")
    args = p.parse_args()

    runs_path = os.path.join(args.directory, "runs.json")
    if not os.path.exists(runs_path):
        sys.exit(f"no runs.json in {args.directory} — run scripts/run-benchmark.mjs first")
    record = json.load(open(runs_path))

    app = None
    if args.metric in ("all", "csim"):
        app = load_face_model()
        if app is None:
            print("note: insightface not installed — skipping CSIM.")
            print("      pip install insightface onnxruntime\n")

    results, groups = [], {}
    for run in record["runs"]:
        if run.get("status") != "generated" or not run.get("file"):
            continue
        clip = os.path.join(args.directory, run["file"])
        if not os.path.exists(clip):
            continue

        # Cases with repeat>1 exist to be compared against each other, not scored alone.
        if (run.get("repeat") or 1) > 1:
            groups.setdefault(run["id"], []).append(clip)

        row = {"id": run["id"], "label": run.get("label", run["id"]), "concept": run["concept"]}
        want = run.get("instrument")

        d, frames = extract_frames(clip, every_n=args.every_n)
        try:
            if args.metric in ("all", "luma") and (want == "luma_trend" or args.metric == "luma"):
                row["luma"] = luma_trend(frames)
            if app is not None and want == "mouth_activity":
                row["mouth"] = mouth_activity(app, frames)
            elif app is not None and args.metric in ("all", "csim") and want != "luma_trend":
                row["csim_intra"] = csim_intra(app, frames)
        finally:
            shutil.rmtree(d, ignore_errors=True)

        results.append(row)
        bits = []
        if "luma" in row:
            l = row["luma"]
            flag = "DRIFT" if l.get("significant") else "ok"
            bits.append(f"skin/scene {l.get('norm_first')}→{l.get('norm_second')} "
                        f"(Δ{l.get('norm_delta')}) {flag}  [raw Δ{l.get('raw_delta')}]")
        if "mouth" in row:
            m = row["mouth"]
            if not m.get("interpretable"):
                bits.append(m.get("note", "not interpretable"))
            else:
                # Raw only. The verdict comes from calibrate() against the floor clip,
                # printed after all rows — a raw ratio here would be read as a result.
                bits.append(f"mouth {m['first_half']}→{m['second_half']} (raw, uncalibrated)")
        if "csim_intra" in row:
            c = row["csim_intra"]
            if "mean" not in c:
                bits.append(c["note"])
            else:
                mark = "" if c.get("interpretable") else "  ⚠ " + "; ".join(c["caveats"])
                bits.append(f"csim {c['mean']} min {c['min']}{mark}")
        print(f"{row['label']:<18} {row['concept']:<32} {'  '.join(bits)}")

    inter = {}
    if app is not None:
        for case_id, clips in groups.items():
            if len(clips) > 1:
                inter[case_id] = csim_inter(app, clips)
                print(f"\n{case_id} cross-clip: {inter[case_id]}")

    # Floor-calibrate any mouth-activity rows, using the control clip if it ran.
    calibrated, floor = {}, None
    ctrl = next((r for r in results if r.get("concept") == "still_face_floor"), None)
    if ctrl and ctrl.get("mouth", {}).get("interpretable"):
        floor = ctrl["mouth"]["overall"]
        calibrated = calibrate([r for r in results if r is not ctrl], floor)
        print(f"\nfloor = {floor} (VID-SING-012, total silence)")
        for cid, c in calibrated.items():
            verdict = "largely stopped" if c["largely_stopped"] else "DID NOT STOP"
            print(f"  {cid:<18} excess {c['excess_first']}→{c['excess_second']}  "
                  f"(x{c['excess_ratio']})  {verdict}")
    elif any("mouth" in r for r in results):
        print("\nno floor clip in this run — mouth numbers are UNCALIBRATED, do not quote them.")

    # Surface escalated findings loudly. A model failure that reads as a scoring gap
    # is how a defect leaves the results without anyone deciding it should.
    findings = [(r["label"], r[k]["FINDING"], r[k]["note"])
                for r in results for k in ("csim_intra", "mouth")
                if isinstance(r.get(k), dict) and "FINDING" in r[k]]
    if findings:
        print(f"\n⚠ {len(findings)} FINDING(S) — not measurement gaps:")
        for label, code, note in findings:
            print(f"  {label:<18} {code}\n    {note}")

    out = os.path.join(args.directory, "scores.json")
    json.dump({"tag": record.get("tag"), "model": record.get("model"), "floor": floor,
               "per_clip": results, "calibrated": calibrated, "cross_clip": inter}, open(out, "w"), indent=2)
    print(f"\n→ {out}")

    if app is None:
        print("\nCSIM was skipped. Any identity claim from this run is unmeasured — say so.")

    print("""
LSE-C / LSE-D are not implemented here on purpose. Reimplementing SyncNet from
scratch would produce a number that looks authoritative and is unvalidated. Wire up
the reference implementation instead, pin its commit in PROVENANCE.md, and remember
it is English-trained: use it to ORDER arms A/B/C, not to grade Hindi sync.""")


if __name__ == "__main__":
    main()
