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
from pathlib import Path as PPath
from typing import Optional

import requests
from cog import BasePredictor, Input, Path, Secret


# ── OUTPUT IS A SINGLE FILE, DELIBERATELY ────────────────────────────────────
#
# There was a save_audio option returning {video, audio} via a BaseModel. Two
# reasons it is gone:
#
#   1. Replicate zips multi-file outputs, so the model page stopped previewing the
#      video inline — you got a download instead of something you could watch.
#   2. It only ever made sense for synthesised speech, and TTS has been removed.
#      With `vocal`/`song` the caller already has the audio; handing it back is
#      returning their own upload.
#
# It also removes the BaseModel, which cost two failed deploys: pydantic undeclared
# in cog.yaml, then pydantic.BaseModel being unable to schema cog.types.Path. Both
# presented as predictions stuck in "starting" with no logs.

API = "https://api.replicate.com/v1"

S2V = "wan-video/wan-2.2-s2v"
I2V = "wan-video/wan-2.2-i2v-fast"
T2V = "wan-video/wan-2.2-t2v-fast"
DEMUCS = "ryan5453/demucs"
# Apache-2.0, four Hindi voices (hf_alpha/hf_beta female, hm_omega/hm_psi male).
# ⚠ Chosen on licence as much as quality: XTTS-v2 is Coqui's non-commercial CPML and
# F5-TTS is cc-by-nc-4.0. Both look permissive from a distance. Neither is.
# ── TTS: REMOVED 2026-08-16 ──────────────────────────────────────────────────
#
# There was a `say` input that synthesised speech and lip-synced to it. Two engines
# were tried and both were judged not good enough for Hindi: Kokoro (Apache-2.0,
# four Hindi voices) sounds synthetic, and MiniMax speech-2.8-hd — better, and the
# one place the Apache-throughout property was being broken — was still not usable.
#
# So lip sync now requires REAL AUDIO: `vocal` or `song`. That is the honest
# position anyway. The model's job is to move a mouth in time with a voice, and it
# does that as well as the voice it is given.
#
# Restoring it means re-adding the input and one call. The measured finding worth
# keeping either way: MiniMax has no Hindi voice_ids at all — `voice_id` selects a
# timbre and `language_boost: "Hindi"` steers the language. Guessed names like
# "Hindi_Sweet_Girl" fail with "Speech generation failed".

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



# Target frame rate for everything that gets stitched.
#
# ⚠ i2v can interpolate itself (interpolate_output), s2v CANNOT — it has no such
# field and writes 16fps, which reads as choppy. That is also a correctness problem:
# concatenating 16fps and 30fps clips with -c copy produces a broken timeline. So
# every s2v clip is lifted to 30fps here, and the whole timeline is uniform.
#
# minterpolate synthesises motion-compensated in-between frames rather than
# duplicating, which is the difference between "smoother" and "same judder, more
# files". It costs a few seconds of CPU on a 5s clip.
FPS = 30


def to_fps(src, dest, fps=FPS):
    r = ff(["-v", "error", "-i", str(src), "-filter:v",
            f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1",
            "-c:a", "copy", "-y", str(dest)])
    p = PPath(dest)
    if p.exists() and p.stat().st_size > 0:
        return dest
    # Motion interpolation can fail on odd inputs; a plain rate change still keeps
    # the timeline uniform, which is the part that must not break.
    ff(["-v", "error", "-i", str(src), "-filter:v", f"fps={fps}", "-y", str(dest)])
    return dest if PPath(dest).exists() else src


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
        return f"data:{mime};base64,{base64.b64encode(PPath(path).read_bytes()).decode()}"

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
        p = PPath(dest)
        return dest if p.exists() and p.stat().st_size > 0 else None

    # ── predict ──────────────────────────────────────────────────────────────

    def predict(
        self,
        prompt: str = Input(description="What the video shows. The only required input — everything else is optional and adds to it."),
        reference_image: Optional[Path] = Input(description="A still of the performer. Fixes who appears in every shot, which is what keeps a longer video looking like one person. Without it, the opening frame is generated from the prompt.", default=None),
        song: Optional[Path] = Input(description="A full song. Becomes the video's audio, and is separated automatically to drive lip sync if no `vocal` is given.", default=None),
        vocal: Optional[Path] = Input(description="An ISOLATED vocal track, to drive lip sync directly. Must be vocal only — a full mix makes the performer mouth through the instrumental passages. Use `song` if you only have the mix.", default=None),
        start_at: Optional[float] = Input(description="Where in the audio to start, in seconds. Leave empty and it begins at the first singing, so a short render of a long song shows the vocal rather than the intro.", default=None),
        seconds: float = Input(description="Maximum length — a ceiling, not a target. The video never outlasts its audio, so a 3-second line gives a 3-second video. Capped at 45s unless you supply your own replicate_token.", default=15, ge=5, le=180),
        reanchor: int = Input(description="Reset to the reference image every N shots. 2 is the measured optimum: 0 loses the performer's identity within about 20 seconds, 1 makes every seam a visible cut.", default=2, ge=0, le=8),
        seed: int = Input(description="Random seed.", default=1000),
        lora_weights_high: Optional[str] = Input(description="Advanced. URL of a Wan 2.2 high-noise LoRA (.safetensors), applied to the non-speaking shots only. Leave empty unless you have one.", default=None),
        lora_weights_low: Optional[str] = Input(description="Advanced. URL of the matching low-noise LoRA. Wan 2.2 A14B is mixture-of-experts, so an adapter is always two files.", default=None),
        replicate_token: Secret = Input(description="Advanced. Your own Replicate API token. Supply it to render past 45 seconds and be billed for the underlying generations yourself.", default=None),
    ) -> Path:

        caller_token = replicate_token.get_secret_value() if replicate_token else None
        # Resolution order: the caller's token, then the environment, then a token baked
        # into the image at build time.
        #
        # ⚠ WHY A BAKED TOKEN AT ALL. This model orchestrates other Replicate predictions,
        # and Replicate cannot bill those to whoever clicked Run — the container's calls
        # are billed to whatever token is inside it. There is also no per-model
        # environment-variable setting for hosted models. So a web visitor with no token
        # of their own gets nothing unless one ships with the image.
        #
        # ⚠ The file is written on the build machine only and is NOT in source control.
        # Anyone able to pull r8.im/beenga/* could read it, so it should be a token that
        # can be rotated independently of the account's main one.
        baked = PPath("/src/.replicate_token")
        token = (caller_token
                 or os.environ.get("REPLICATE_API_TOKEN")
                 or (baked.read_text().strip() if baked.exists() else None))
        if not token:
            raise RuntimeError(
                "No Replicate token available. Supply `replicate_token` — this model "
                "orchestrates other Replicate predictions and cannot run without one.")

        if not caller_token and seconds > FREE_MAX_SECONDS:
            seconds = FREE_MAX_SECONDS
            print(f"capped to {FREE_MAX_SECONDS}s — supply replicate_token to render longer")

        work = PPath(tempfile.mkdtemp(prefix="beenga-"))
        V = {}

        # ── work out what we were given ──────────────────────────────────────
        #
        # Everything except `prompt` is optional, and the combination decides the
        # pipeline. Lip sync needs a vocal; a vocal can be supplied directly or
        # extracted from a full mix. With neither, this is a motion video and no
        # s2v shot is planned at all.
        master = None
        if song is not None:
            master = work / "master.mp3"
            self._fetch_local(song, master)

        stem = None
        if vocal is not None:
            stem = work / "vocal.mp3"
            self._fetch_local(vocal, stem)
        elif master is not None:
            # ⚠ The mix cannot drive s2v directly. Given an instrumental passage the
            # model articulates at 95% of the vocal rate (VID-SING-010), so the
            # performer mouths through the intro, the break and the outro. Separated
            # first, the mouth stops when the singing does (VID-SING-013).
            print("no vocal supplied — separating one from the mix…")
            v = self._version(DEMUCS, token)
            out = self._predict(v, {"audio": self._data_uri(master, "audio/mpeg"),
                                    "stem": "vocals"}, token)
            # ⚠ Demucs returns a DICT, not a URL: {"vocals": ..., "no_vocals": ...}.
            # `stem: "vocals"` puts it in two-way mode and it hands back BOTH halves.
            # Passing that straight to requests fails with "No connection adapters
            # were found", which reads as a network error and is a shape error.
            if isinstance(out, dict):
                url = out.get("vocals") or out.get("vocal")
                if not url:
                    raise RuntimeError(f"demucs returned no vocal stem: {list(out)}")
            else:
                url = out
            stem = work / "vocal.mp3"
            self._fetch(url, stem)

        lip_sync = stem is not None
        audio_out = master or stem          # what the finished video plays
        print("lip sync: " + ("on" if lip_sync else "off — no vocal or song supplied"))

        # ── the reference still ──────────────────────────────────────────────
        #
        # Optional. Without one the opening shot is generated from the prompt and
        # everything chains from it — which still holds together, but identity is
        # anchored to a generated frame rather than to an image the caller chose.
        still = work / "still.png"
        if reference_image is not None:
            self._fetch_local(reference_image, still)
        else:
            print("no reference image — generating the opening frame from the prompt…")
            V["t2v"] = self._version(T2V, token)
            url = self._predict(V["t2v"], {"prompt": prompt, "seed": seed,
                                           "resolution": "480p",
                                           "interpolate_output": False}, token)
            first = work / "seed.mp4"
            self._fetch(url, first)
            if self._last_frame(first, still) is None:
                raise RuntimeError("could not derive an opening frame from the prompt")

        duration = probe_duration(audio_out) if audio_out else seconds
        gaps = self._vocal_gaps(stem) if lip_sync else []
        in_silence = lambda t: any(s <= t < e for s, e in gaps)

        # WHERE IN THE AUDIO TO START.
        #
        # Rendering 10 seconds of a 3-minute song from t=0 gives you the intro —
        # which on most tracks is instrumental, so the clip has no singing in it and
        # no lip sync at all. Technically what was asked for; useless as a clip.
        #
        # So when the render is shorter than the audio and no start is given, begin
        # at the first singing instead. An explicit start_at always wins.
        begin = start_at if start_at is not None else 0.0
        if start_at is None and lip_sync and seconds < duration - 1:
            first_vocal = next((e for s_, e in gaps if e < duration - 1), 0.0)
            if first_vocal > 0.5:
                begin = first_vocal
                print(f"short render of a long track — starting at the first vocal, {begin:.1f}s")
        begin = max(0.0, min(begin, max(0.0, duration - 1)))
        target = min(seconds, max(0.0, duration - begin) if audio_out else seconds)

        # ── plan the shots ───────────────────────────────────────────────────
        shots, t, i = [], begin, 0
        while t < begin + target - 0.5:
            kind = "s2v" if (lip_sync and not in_silence(t + 0.4)) else "i2v"
            shots.append({"i": i, "at": round(t, 2), "kind": kind,
                          "reset": reanchor > 0 and i % reanchor == 0})
            t += CLIP[kind]
            i += 1

        n_s2v = sum(1 for s in shots if s["kind"] == "s2v")
        print(f"{len(shots)} shots — {n_s2v} sung (s2v), {len(shots) - n_s2v} instrumental (i2v)")

        V["i2v"] = self._version(I2V, token)
        if any(sh["kind"] == "s2v" for sh in shots):
            V["s2v"] = self._version(S2V, token)
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
                           # ⚠ ON here, OFF in the benchmark, and the distinction matters.
                           # Wan writes 16fps, which reads as choppy. interpolate_output
                           # lifts it to 30fps with ffmpeg. Those synthesised in-between
                           # frames make temporal MEASUREMENT meaningless — scoring motion
                           # coherence on them scores ffmpeg — so scripts/run-benchmark.mjs
                           # pins it off. This is delivery, not measurement, so it is on.
                           "interpolate_output": True,
                           # ⚠ Pinned, not left to the default. It currently defaults to
                           # False (checker ON) — but a default is upstream's to change,
                           # and this one should never flip silently on a public model.
                           "disable_safety_checker": False}
                if lora_weights_high:
                    payload["lora_weights_transformer"] = lora_weights_high
                    payload["lora_scale_transformer"] = 1
                if lora_weights_low:
                    payload["lora_weights_transformer_2"] = lora_weights_low
                    payload["lora_scale_transformer_2"] = 1

            try:
                url = self._predict(V[s["kind"]], payload, token)
                self._fetch(url, clip)
                if s["kind"] == "s2v":
                    # s2v writes 16fps and cannot interpolate itself.
                    lifted = work / f"s{s['i']:02d}-30.mp4"
                    if to_fps(clip, lifted) == str(lifted) or PPath(lifted).exists():
                        clip = lifted
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
        final = work / "beenga-video.mp4"
        if audio_out is not None:
            # The MIX is what plays, not the stem that drove the model.
            # The audio must start where the video does, or the lip sync is out by
            # exactly `begin` seconds — which looks like the model failing.
            ff(["-v", "error", "-i", str(cut), "-ss", str(begin), "-i", str(audio_out),
                "-map", "0:v", "-map", "1:a", "-shortest",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-y", str(final)],
               capture=False)
        else:
            ff(["-v", "error", "-i", str(cut), "-c", "copy", "-y", str(final)], capture=False)

        print(f"{len(made)}/{len(shots)} shots → {probe_duration(final):.1f}s")
        return Path(final)

    @staticmethod
    def _fetch_local(src, dest):
        PPath(dest).write_bytes(PPath(str(src)).read_bytes())
        return dest
