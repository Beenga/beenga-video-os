#!/usr/bin/env python3
"""Cut vertical shorts for mobile from the finished 16:9 video.

⚠ WHY BLURRED-FILL RATHER THAN A CROP.

The clips are 832x464. A true 9:16 crop takes a 261px-wide strip and upscales it
roughly 4x to reach 1080x1920, which turns soft and mushy. Blurred-fill keeps the
whole frame at close to native scale in the middle band and fills the rest with a
blurred, enlarged copy of the same footage. It loses screen area but keeps the
faces sharp, and faces are what this film is.

Native 9:16 renders would beat both, but that means regenerating clips at a
vertical aspect from the stills — a cost, not an edit.

⚠ EACH SHORT TAKES ITS OWN AUDIO FROM THE MASTER.

Not from the assembled video's audio track, so a short can start anywhere without
inheriting a fade or a partial bar from the long cut.
"""
import os
import subprocess

ROOT = "/Users/hanumanji/demo/beenga-video-os"
BASE = f"{ROOT}/out/chhupke"
SRC = f"{BASE}/chhupke-se-aa.mp4"
SONG = "/Users/hanumanji/demo/gs/songs/chupke/Chhupke Se Aa.wav"
OUT = f"{BASE}/shorts"
W, H = 1080, 1920

# (name, start, duration) — chosen as self-contained emotional beats, each able to
# open cold without the shots before it.
CUTS = [
    ("01-longing", 0.0, 20.0),    # curtains, the letter, her at the window
    ("02-memory", 18.0, 20.0),    # the garden, the flower, warmth
    ("03-rain", 60.0, 20.0),      # the courtyard, rain, alone
    ("04-reunion", 92.0, 22.0),   # the street, recognition, the flower returning
]

# Blurred cover behind, sharp contained copy in front, both from the same source.
# ⚠ The background must scale by HEIGHT to cover the canvas. Scaling by width
# gives a 1080x602 image, and cropping 1920 out of 602 fails outright — which is
# exactly how the first attempt died. -2 keeps dimensions even for libx264.
VF = (f"[0:v]scale=-2:{H},crop={W}:{H}:(in_w-{W})/2:0,"
      f"boxblur=24:3,eq=brightness=-0.06[bg];"
      f"[0:v]scale={W}:-2[fg];"
      f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]")


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, start, dur in CUTS:
        out = f"{OUT}/{name}.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-v", "error",
            "-ss", str(start), "-t", str(dur), "-i", SRC,
            "-ss", str(start), "-t", str(dur), "-i", SONG,
            "-filter_complex", VF,
            "-map", "[v]", "-map", "1:a",
            # Fade the tail so a short does not stop mid-phrase.
            "-af", f"afade=t=out:st={dur-1.2}:d=1.2",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-y", out], check=True)
        size = os.path.getsize(out) / 1024 / 1024
        print(f"  {name:<12} {start:5.1f}s +{dur:4.1f}s   {size:5.1f} MB   {out}")


if __name__ == "__main__":
    main()
