"""Beenga Video 1 — a song in, a lip-synced music video out.

Port of scripts/make-music-video.mjs. Every rule here is a measured result from
the benchmark in this repo, and each one names the case that produced it. See
README.md, WAVE0.md and LONGFORM.md.

⚠ THIS MODEL RUNS NO WEIGHTS. It orchestrates Replicate's hosted Wan 2.2
endpoints and assembles the result with ffmpeg. The value is the routing, not
the maths — so it is a small CPU container rather than a 70GB GPU image.

⚠ COST SAFETY. Each rendered second costs real money in downstream predictions,
so `seconds` is capped and defaults low. A caller who wants a full three-minute
render supplies their own token via `replicate_token` and pays for it themselves.
Without that, the render is short and Beenga is paying — which is a demo, not a
service.
"""
import base64
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import requests
from cog import BasePredictor, Input, Path as CogPath, Secret

API = "https://api.replicate.com/v1"

S2V = "wan-video/wan-2.2-s2v"
I2V = "wan-video/wan-2.2-i2v-fast"
DEMUCS = "ryan5453/demucs"

# Measured from the files, not read off the schema. wan-2.2-5b-fast advertises
# 121 frames and writes 81; these two were verified against real output.
CLIP = {"s2v": 4.81, "i2v": 5.06}

# Beenga pays for anything the caller does not. Keep the free path short.
FREE_MAX_SECONDS = 45


def ff(args, capture=True):
    """ffmpeg without -v error.

    ⚠ silencedetect and volumedetect log at INFO. Running them under -v error
    suppresses the output a parser then reads as "no silences found" — a
    confident measurement of nothing. This bit this project twice.
    """
    return subprocess.run(["ffmpeg", "-hide_banner", *args],
                          capture_output=capture, text=True)


def probe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


class Predictor(BasePredictor):
    def setup(self):
        self.session = requests.Session()

    # ── Replicate plumbing ───────────────────────────────────────────────────

    def _headers(self, token):
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _version(self, model, token):
        r = self.session.get(f"{API}/models/{model}", headers=self._headers(token), timeout=60)
        r.raise_for_status()
        return r.json()["latest_version"]["id"]

    def _predict(self, version, payload, token, tries=8):
        """Create a prediction and wait.

        429 is retried with backoff: Replicate throttles prediction creation
        hard when an account is below $5 credit — 6/minute with a burst of 1 —
        and that reads as a concurrency limit if you do not know to look.
        """
        body = {"version": version, "input": payload}
        j = None
        for n in range(tries):
            r = self.session.post(f"{API}/predictions", headers=self._headers(token),
                                  data=json.dumps(body), timeout=120)
            if r.ok:
                j = r.json()
                break
            if r.status_code != 429:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            time.sleep(min(60, int(r.headers.get("retry-after") or 0) or 4 * 2 ** n))
        if j is None:
            raise RuntimeError("rate limited creating prediction")

        while j["status"] not in ("succeeded", "failed", "canceled"):
            time.sleep(3)
            g = self.session.get(f"{API}/predictions/{j['id']}",
                                 headers=self._headers(token), timeout=60)
            if g.status_code == 429:
                continue
            j = g.json()
        if j["status"] != "succeeded":
            raise RuntimeError(f"{j['status']}: {str(j.get('error'))[:200]}")
        out = j["output"]
        return out[0] if isinstance(out, list) else out

    def _fetch(self, url, dest):
        with self.session.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
        return dest

    @staticmethod
    def _data_uri(path, mime):
        return f"data:{mime};base64,{base64.b64encode(Path(path).read_bytes()).decode()}"

    # ── the measured rules ───────────────────────────────────────────────────

    @staticmethod
    def _vocal_gaps(stem):
        """Where the singer is NOT singing. Drives shot routing."""
        out = ff(["-i", str(stem), "-af", "silencedetect=noise=-28dB:d=0.8",
                  "-f", "null", "-"]).stderr or ""
        starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", out)]
        ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
        return [(s, e) for s, e in zip(starts, ends)]

    @staticmethod
    def _last_frame(clip, dest):
        """⚠ NOT -sseof. It works on i2v output and silently writes nothing on
        s2v output — 73 frames of picture inside a 4.81s container, so the seek
        lands past the final frame and ffmpeg still exits 0. Decode through."""
        ff(["-v", "error", "-i", str(clip), "-update", "1", "-q:v", "2", "-y", str(dest)])
        p = Path(dest)
        return dest if p.exists() and p.stat().st_size > 0 else None

    # ── predict ──────────────────────────────────────────────────────────────

    def predict(
        self,
        song: CogPath = Input(description="The finished song (mp3/wav). The full mix."),
        reference_image: CogPath = Input(
            description="A still of the performer. This fixes who appears in every shot — "
                        "identity is anchored to it, so use the face you want."),
        seconds: float = Input(
            description="How much of the song to render. Capped at 45s unless you supply "
                        "your own replicate_token.", default=30, ge=5, le=180),
        prompt: str = Input(
            description="What the non-singing shots show.",
            default="A young Indian woman in a modern Indian setting, natural movement, realistic video."),
        vocal_stem: Optional[CogPath] = Input(
            description="Optional isolated vocal. If omitted it is separated automatically. "
                        "Supplying one skips a step and a cost.", default=None),
        reanchor: int = Input(
            description="Reset to the reference image every N shots. 2 is the measured "
                        "optimum: 0 loses the performer's identity within ~20s, 1 makes "
                        "every seam a visible cut.", default=2, ge=0, le=8),
        lora_weights_high: Optional[str] = Input(
            description="URL of a Wan 2.2 high-noise LoRA for the non-singing shots.", default=None),
        lora_weights_low: Optional[str] = Input(
            description="URL of the matching low-noise LoRA. A14B is mixture-of-experts, "
                        "so an adapter is two files.", default=None),
        seed: int = Input(default=1000),
        replicate_token: Secret = Input(
            description="Your Replicate API token. Supply it to render past 45s and to be "
                        "billed for the underlying generations yourself.", default=None),
    ) -> CogPath:

        caller_token = replicate_token.get_secret_value() if replicate_token else None
        token = caller_token or os.environ.get("REPLICATE_API_TOKEN")
        if not token:
            raise RuntimeError(
                "No Replicate token available. Supply `replicate_token` — this model "
                "orchestrates other Replicate predictions and cannot run without one.")

        if not caller_token and seconds > FREE_MAX_SECONDS:
            seconds = FREE_MAX_SECONDS
            print(f"capped to {FREE_MAX_SECONDS}s — supply replicate_token to render longer")

        work = Path(tempfile.mkdtemp(prefix="beenga-"))
        master = work / "master.mp3"
        self._fetch_local(song, master)

        # ── the vocal stem ───────────────────────────────────────────────────
        # ⚠ S2V CANNOT TELL MUSIC FROM VOICE. Fed an instrumental passage it
        # articulates at 95% of the vocal rate (VID-SING-010), so a master track
        # makes the performer mouth through the intro, the break and the outro.
        # Fed the isolated stem, the mouth stops when the singing does
        # (VID-SING-013). So the stem drives S2V and the master is muxed back
        # over the finished video at the end, where it belongs.
        stem = work / "vocal.mp3"
        if vocal_stem is not None:
            self._fetch_local(vocal_stem, stem)
        else:
            print("separating vocal…")
            v = self._version(DEMUCS, token)
            url = self._predict(v, {"audio": self._data_uri(master, "audio/mpeg"),
                                    "stem": "vocals"}, token)
            self._fetch(url, stem)

        duration = probe_duration(master)
        target = min(seconds, duration)
        gaps = self._vocal_gaps(stem)
        in_silence = lambda t: any(s <= t < e for s, e in gaps)

        # ── plan the shots ───────────────────────────────────────────────────
        shots, t, i = [], 0.0, 0
        while t < target - 0.5:
            kind = "i2v" if in_silence(t + 0.4) else "s2v"
            shots.append({"i": i, "at": round(t, 2), "kind": kind,
                          "reset": reanchor > 0 and i % reanchor == 0})
            t += CLIP[kind]
            i += 1

        n_s2v = sum(1 for s in shots if s["kind"] == "s2v")
        print(f"{len(shots)} shots — {n_s2v} sung (s2v), {len(shots) - n_s2v} instrumental (i2v)")

        V = {"s2v": self._version(S2V, token), "i2v": self._version(I2V, token)}
        still = work / "still.png"
        self._fetch_local(reference_image, still)
        conditioning, made = still, []

        for s in shots:
            clip = work / f"s{s['i']:02d}.mp4"
            if s["kind"] == "s2v":
                seg = work / f"a{s['i']:02d}.wav"
                ff(["-v", "error", "-ss", str(s["at"]), "-t", str(CLIP["s2v"]),
                    "-i", str(stem), "-ar", "16000", "-ac", "1", "-y", str(seg)])
                payload = {"prompt": "A person singing, realistic video.",
                           "image": self._data_uri(conditioning, "image/png"),
                           "audio": self._data_uri(seg, "audio/wav"),
                           "seed": seed + s["i"]}
            else:
                payload = {"prompt": prompt,
                           "image": self._data_uri(conditioning, "image/png"),
                           "seed": seed + s["i"], "resolution": "480p",
                           # ⚠ Off deliberately. It defaults ON for one model and
                           # OFF for another, which alone makes their outputs
                           # incomparable, and it synthesises in-between frames.
                           "interpolate_output": False}
                if lora_weights_high:
                    payload["lora_weights_transformer"] = lora_weights_high
                    payload["lora_scale_transformer"] = 1
                if lora_weights_low:
                    payload["lora_weights_transformer_2"] = lora_weights_low
                    payload["lora_scale_transformer_2"] = 1

            try:
                url = self._predict(V[s["kind"]], payload, token)
                self._fetch(url, clip)
                last = self._last_frame(clip, work / f"s{s['i']:02d}-last.png")
                made.append(clip)
                print(f"  shot {s['i']:02d} {s['kind']} ok")
                conditioning = still if (s["reset"] or last is None) else last
            except Exception as e:
                print(f"  shot {s['i']:02d} {s['kind']} FAILED: {str(e)[:120]}")
                conditioning = still

        if not made:
            raise RuntimeError("no shots generated")

        # ── stitch, then mux the MASTER over the top ─────────────────────────
        lst = work / "concat.txt"
        lst.write_text("\n".join(f"file '{c}'" for c in made))
        cut = work / "cut.mp4"
        ff(["-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
            "-c", "copy", "-y", str(cut)], capture=False)
        final = work / "beenga-music-video.mp4"
        ff(["-v", "error", "-i", str(cut), "-i", str(master), "-map", "0:v", "-map", "1:a",
            "-shortest", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-y", str(final)],
           capture=False)

        print(f"{len(made)}/{len(shots)} shots → {probe_duration(final):.1f}s")
        return CogPath(final)

    @staticmethod
    def _fetch_local(src, dest):
        Path(dest).write_bytes(Path(str(src)).read_bytes())
        return dest
