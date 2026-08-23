#!/usr/bin/env python3
"""Generate the per-shot stills for a music video from shots.json.

⚠ WHY STILLS FIRST, THEN VIDEO.

Video models drift. Faces, clothing and locations wander between clips, and there
is no way to correct that after the fact. So the character is locked as a still
first, and every shot is generated with those stills fed in as reference. The
video stage then only has to animate a frame that is already correct.

⚠ SEED COUNT IS NOT UNIFORM, AND THAT IS DELIBERATE.

The shot-7 test showed the model loses *whose* ear a flower goes behind — two of
three seeds put it on the man. The flower recurs in the memory (0:39) and pays off
in the reunion (1:42), so those shots carry plot weight and get more seeds to
select from. Shots with one person and no prop are reliable at three.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ROOT = "/Users/hanumanji/demo/beenga-video-os"
SHOTS = f"{ROOT}/out/chhupke/shots.json"
OUTDIR = f"{ROOT}/out/chhupke/shots"

# Replicate throttles to 6 predictions/minute when account credit is low, and a
# 429 there costs a retry cycle. 11s between submissions stays under it.
SUBMIT_GAP = 11

PALETTE = {
    "present": "cool blue-grey tones, soft overcast evening light, restrained and quiet",
    "memory":  "warm golden hour light, subtle film grain, soft halation, nostalgic",
    "reunion": "rain-washed, warm light beginning to break through cloud, hopeful",
}
STYLE = ("cinematic 16:9 frame, shallow depth of field, photorealistic, natural "
         "emotional expression, no exaggerated posing, no text, no watermark")

# Shots whose prop or action the model gets wrong often enough to need selection.
HARD = {"s07", "s16"}


def token():
    for p in (f"{os.path.expanduser('~')}/demo/beenga-image/.env",):
        if os.path.exists(p):
            m = re.search(r"r8_[A-Za-z0-9]{20,}", open(p).read())
            if m:
                return m.group(0)
    sys.exit("no replicate token")


def api(path, tok, data=None):
    req = urllib.request.Request(
        f"https://api.replicate.com/v1/{path}",
        data=json.dumps(data).encode() if data else None,
        # ⚠ User-Agent is REQUIRED. Replicate 403s urllib's default
        # "Python-urllib/3.x" while accepting the identical request from curl —
        # same token, same Authorization header. Without this the script dies on
        # its first call with a Forbidden that looks like an auth problem.
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
                 "User-Agent": "beenga-video-os/1.0"},
        method="POST" if data else "GET")
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def build_prompt(shot, cont):
    # ⚠ An override describes the END STATE rather than the action. The model
    # renders a still, so a verb like "places a flower behind her ear" is
    # ambiguous about the object and lands on the man roughly two thirds of the
    # time. Describing the result — flower already in her hair, his ears bare —
    # removes the ambiguity instead of rolling more seeds at it.
    desc = shot.get("prompt_override") or shot["desc"]
    who = shot["who"]
    people = []
    if "woman" in who:
        people.append(cont["woman"])
    if "man" in who:
        people.append(cont["man"])
    return (f"{desc} {' '.join(people)}. "
            f"{PALETTE[shot['mode']]}. {STYLE}.")


def main():
    tok = token()
    d = json.load(open(SHOTS))
    cont = d["continuity"]
    refs = json.load(open("/tmp/ref_urls.json"))
    ver = api("models/beenga/beenga-image-1", tok)["latest_version"]["id"]
    os.makedirs(OUTDIR, exist_ok=True)

    jobs = []
    for shot in d["shots"]:
        sid = shot["id"]
        seeds = [7, 17, 27, 37, 47, 57][:6] if sid in HARD else [3, 13, 23]
        images = [refs["woman"]] if shot["who"] == ["woman"] else [refs["woman"], refs["man"]]
        prompt = build_prompt(shot, cont)
        for seed in seeds:
            out = f"{OUTDIR}/{sid}-{seed}.png"
            if os.path.exists(out):
                continue
            body = {"version": ver, "input": {
                "prompt": prompt, "images": images, "aspect_ratio": "16:9",
                "seed": seed, "num_inference_steps": 4, "guidance_scale": 3.5}}
            try:
                r = api("predictions", tok, body)
                jobs.append((sid, seed, r.get("id"), out))
                print(f"  submit {sid} seed={seed} -> {r.get('id')}", flush=True)
            except Exception as e:
                print(f"  SUBMIT FAIL {sid} seed={seed}: {str(e)[:100]}", flush=True)
            time.sleep(SUBMIT_GAP)

    print(f"\nsubmitted {len(jobs)}; collecting\n", flush=True)
    pending = list(jobs)
    while pending:
        still = []
        for sid, seed, jid, out in pending:
            if os.path.exists(out):
                continue
            try:
                r = api(f"predictions/{jid}", tok)
            except Exception:
                still.append((sid, seed, jid, out)); continue
            st = r.get("status")
            if st == "succeeded":
                u = r.get("output")
                u = u if isinstance(u, str) else (u[0] if u else None)
                if u:
                    urllib.request.urlretrieve(u, out)
                    print(f"  ok {os.path.basename(out)}", flush=True)
            elif st in ("failed", "canceled"):
                print(f"  FAILED {sid} seed={seed}: {str(r.get('error'))[:120]}", flush=True)
            else:
                still.append((sid, seed, jid, out))
        pending = still
        if pending:
            time.sleep(10)
    print(f"\ndone. {len(os.listdir(OUTDIR))} files in {OUTDIR}")


if __name__ == "__main__":
    main()
