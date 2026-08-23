#!/usr/bin/env python3
"""Render the lip-sync shots on Beenga's own RunPod endpoint.

⚠ TRIM BEFORE RENDERING, NOT AFTER.

Every constraint here is known before a GPU second is spent: which shots contain
the other singer, how long each male-free window is, and how long the shot needs
to be. An earlier pass rendered full 7s slices and then discovered his voice in
the tail — paying to generate frames that were then discarded, and once paying
again to re-render what ffmpeg could have trimmed for free.

So each shot renders exactly its largest male-free window, from a driving track
with his phrases already silenced. Shots whose window is too short to be worth it
fall back to an animated still.

⚠ auto_voiced IS OFF ON PURPOSE.

The handler's voiced-region finder exists so a caller who passes a whole song does
not drive lip sync with a silent intro. Here the offset is chosen deliberately per
shot so her mouth matches the real timestamp in the final edit; letting the
handler hunt for the loudest passage would desync every shot.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ROOT = "/Users/hanumanji/demo/beenga-video-os"
BASE = f"{ROOT}/out/chhupke"
VOCAL = "/Users/hanumanji/demo/gs/songs/chupke/vocal-her-only.wav"
OUT = f"{BASE}/clips-runpod"
ENDPOINT = "xve5vdibg3kcu8"
STEPS = 20  # measured: 217s vs 406s at 40, no visible loss at this resolution


def env(pat, path="~/demo/beenga-image/.env"):
    m = re.search(pat, open(os.path.expanduser(path)).read())
    return m.group(0) if m else sys.exit(f"missing {pat}")


def fal_upload(path, key, ctype):
    r = json.loads(subprocess.run(
        ["curl", "-s", "-X", "POST", "https://rest.alpha.fal.ai/storage/upload/initiate",
         "-H", f"Authorization: Key {key}", "-H", "Content-Type: application/json",
         "-d", json.dumps({"file_name": os.path.basename(path), "content_type": ctype})],
        capture_output=True, text=True).stdout)
    subprocess.run(["curl", "-s", "-X", "PUT", r["upload_url"], "-H", f"Content-Type: {ctype}",
                    "--data-binary", f"@{path}"], capture_output=True)
    return r["file_url"]


def rp(path, tok, data=None):
    req = urllib.request.Request(
        f"https://api.runpod.ai/v2/{ENDPOINT}/{path}",
        data=json.dumps(data).encode() if data else None,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        method="POST" if data else "GET")
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def main():
    tok = env(r"(?<=RUNPOD_API_KEY=)[^\s]+")
    fal = env(r"(?<=FAL_KEY=)[^\s]+", f"{ROOT}/.env")
    plan = json.load(open(f"{BASE}/lipsync-plan.json"))
    shots = {s["id"]: s for s in json.load(open(f"{BASE}/shots.json"))["shots"]}
    cont = json.load(open(f"{BASE}/shots.json"))["continuity"]
    os.makedirs(OUT, exist_ok=True)

    jobs = []
    for sid, p in sorted(plan.items()):
        if not p["lipsync"] or os.path.exists(f"{OUT}/{sid}.mp4"):
            continue
        if sid == "s14":            # already rendered; trimmed separately
            continue
        a, b = p["window"]
        wav = f"/tmp/{sid}_vox.wav"
        subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-ss", str(a),
                        "-t", str(round(b - a, 2)), "-i", VOCAL,
                        "-ar", "16000", "-ac", "1", "-y", wav], check=True)
        img_url = fal_upload(f"{BASE}/final/{sid}.png", fal, "image/png")
        aud_url = fal_upload(wav, fal, "audio/wav")
        prompt = f"{shots[sid]['desc']} {cont['woman']}. cinematic, photorealistic."
        body = {"input": {"prompt": prompt, "image": img_url, "audio": aud_url,
                          "max_seconds": round(b - a, 2), "resolution": "480p",
                          "sampling_steps": STEPS, "seed": 42,
                          "interpolate": True, "auto_voiced": False}}
        # The endpoint 409s for ~40s after any workersMax change; retry rather than
        # treating a missing id as a failure, which once cost 9 minutes of polling
        # an empty job id.
        jid = None
        for _ in range(6):
            r = rp("run", tok, body)
            jid = r.get("id")
            if jid:
                break
            time.sleep(15)
        if not jid:
            print(f"  SUBMIT FAILED {sid}", flush=True)
            continue
        jobs.append((sid, jid))
        print(f"  submit {sid}  {a:.1f}-{b:.1f}s ({b-a:.1f}s) -> {jid}", flush=True)
        time.sleep(5)

    print(f"\nrendering {len(jobs)} clips\n", flush=True)
    pending = list(jobs)
    while pending:
        nxt = []
        for sid, jid in pending:
            try:
                r = rp(f"status/{jid}", tok)
            except Exception:
                nxt.append((sid, jid)); continue
            st = r.get("status")
            if st == "COMPLETED":
                o = r.get("output") or {}
                if o.get("video_base64"):
                    import base64
                    open(f"{OUT}/{sid}.mp4", "wb").write(base64.b64decode(o["video_base64"]))
                    t = (o.get("meta") or {}).get("timing", {})
                    print(f"  ok {sid}  generate {t.get('generate_s')}s", flush=True)
                else:
                    print(f"  {sid} completed but no video: {str(o.get('error'))[:120]}", flush=True)
            elif st in ("FAILED", "CANCELLED", "TIMED_OUT"):
                print(f"  FAILED {sid}: {str(r.get('error'))[:140]}", flush=True)
            else:
                nxt.append((sid, jid))
        pending = nxt
        if pending:
            time.sleep(20)
    print("\ndone")


if __name__ == "__main__":
    main()
