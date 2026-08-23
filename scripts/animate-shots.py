#!/usr/bin/env python3
"""Animate the selected stills into clips, one per shot.

⚠ CAMERA MOTION IS NOT UNIFORM, AND THAT IS THE POINT.

Model-driven camera moves look filmic but drift, and drift is most visible on a
face. So the wides carry the moves the treatment asks for — push in, track back,
circle, pull out — and the close-ups get almost none, with the movement added in
the edit instead. A soft, wandering face ruins a shot; a static wide does not.

⚠ interpolate_output MUST be on.

These models write 16fps and it reads as judder. A previous project shipped with
it off because a benchmark setting leaked into the product, and every clip
juddered. 16fps is a sampling choice, not a look.
"""
import json
import os
import re
import sys
import time
import urllib.request

ROOT = "/Users/hanumanji/demo/beenga-video-os"
BASE = f"{ROOT}/out/chhupke"
OUTDIR = f"{BASE}/clips"
MODEL = "wan-video/wan-2.2-i2v-fast"
SUBMIT_GAP = 12

# Motion per shot, taken from the treatment. Empty string = hold, move in the edit.
MOTION = {
    "s01": "slow steady push in toward the woman by the window, curtains drifting in the breeze",
    "s02": "almost still, only her hair and the curtain moving faintly",
    "s03": "very slight drift closer, her fingers moving slowly across the paper",
    "s04": "gentle handheld follow as the couple walk together, leaves moving",
    "s05": "camera tracks slowly backward as she walks toward it through the garden",
    "s06": "her sari and long hair lift and settle in the breeze, blossoms stirring",
    "s07": "small tender movement, his hand lowering, her eyes closing briefly",
    "s08": "camera slowly circles her against the sunset sky, clouds drifting",
    "s09": "minimal motion, a slow blink, breath, the letter shifting slightly",
    "s10": "light rain falling, she tilts her face upward, droplets on her skin",
    "s11": "the couple move through the rain together, water splashing, cloth swinging",
    "s12": "she turns slowly and her hand lowers, rain continuing around her",
    "s13": "rain falls between them, the distant figure slowly becoming clearer",
    "s14": "held close, only rain and a faint movement of her eyes",
    "s15": "she takes slow steps forward, rain falling, shallow focus holding on her",
    "s16": "small intimate movement, his hand lowering from her hair, her eyes filling",
    "s17": "camera pulls slowly back as they stay close, rain falling, light warming",
    "s18": "their joined hands move very slightly, rain dripping past",
}


def token():
    m = re.search(r"r8_[A-Za-z0-9]{20,}",
                  open(os.path.expanduser("~/demo/beenga-image/.env")).read())
    return m.group(0) if m else sys.exit("no token")


def api(path, tok, data=None, raw=None, ctype=None):
    headers = {"Authorization": f"Bearer {tok}",
               # ⚠ Replicate 403s urllib's default User-Agent.
               "User-Agent": "beenga-video-os/1.0"}
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    else:
        body = raw
        if ctype:
            headers["Content-Type"] = ctype
    req = urllib.request.Request(f"https://api.replicate.com/v1/{path}", data=body,
                                 headers=headers,
                                 method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def upload(path, tok):
    """Replicate's files API, multipart by hand to avoid a requests dependency."""
    boundary = "----beenga" + os.urandom(8).hex()
    name = os.path.basename(path)
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"content\"; "
            f"filename=\"{name}\"\r\nContent-Type: image/png\r\n\r\n").encode()
    body += open(path, "rb").read()
    body += f"\r\n--{boundary}--\r\n".encode()
    r = api("files", tok, raw=body, ctype=f"multipart/form-data; boundary={boundary}")
    return r["urls"]["get"]


def main():
    tok = token()
    d = json.load(open(f"{BASE}/shots.json"))
    ver = api(f"models/{MODEL}", tok)["latest_version"]["id"]
    os.makedirs(OUTDIR, exist_ok=True)

    jobs = []
    for shot in d["shots"]:
        sid = shot["id"]
        still = f"{BASE}/final/{sid}.png"
        out = f"{OUTDIR}/{sid}.mp4"
        if os.path.exists(out) or not os.path.exists(still):
            continue
        url = upload(still, tok)
        motion = MOTION.get(sid, "")
        prompt = f"{shot['desc']} {motion}." if motion else shot["desc"]
        body = {"version": ver, "input": {
            "prompt": prompt,
            "image": url,
            "num_frames": 81,            # 81 @ 16fps ~= 5s, trimmed later
            "resolution": "480p",
            "frames_per_second": 16,
            "interpolate_output": True,  # see module docstring
            "go_fast": True,
            "seed": 42,
            "disable_safety_checker": False,  # never enabled; see CONTENT-POLICY.md
        }}
        r = api("predictions", tok, body)
        jobs.append((sid, r.get("id"), out))
        print(f"  submit {sid} -> {r.get('id')}", flush=True)
        time.sleep(SUBMIT_GAP)

    print(f"\nsubmitted {len(jobs)}; collecting\n", flush=True)
    pending = list(jobs)
    while pending:
        still_p = []
        for sid, jid, out in pending:
            try:
                r = api(f"predictions/{jid}", tok)
            except Exception:
                still_p.append((sid, jid, out)); continue
            st = r.get("status")
            if st == "succeeded":
                u = r.get("output")
                u = u if isinstance(u, str) else (u[0] if u else None)
                if u:
                    urllib.request.urlretrieve(u, out)
                    print(f"  ok {sid}  ({r.get('metrics',{}).get('predict_time',0):.0f}s)", flush=True)
            elif st in ("failed", "canceled"):
                print(f"  FAILED {sid}: {str(r.get('error'))[:140]}", flush=True)
            else:
                still_p.append((sid, jid, out))
        pending = still_p
        if pending:
            time.sleep(15)
    print(f"\ndone: {len(os.listdir(OUTDIR))} clips in {OUTDIR}")


if __name__ == "__main__":
    main()
