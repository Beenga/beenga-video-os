#!/usr/bin/env python3
"""Cut the generated clips to the treatment's timings and lay the song under them.

⚠ CLIPS ARE SHORTER THAN SOME SHOTS, AND THAT IS FIXED HERE, NOT BY RE-RENDERING.

The video models cap out around 4.7-4.8s regardless of the duration requested, but
the treatment asks for shots from 1s to 8s. Rather than pay to regenerate, each
clip is retimed to its slot:

  shot shorter than clip -> trim
  shot longer  than clip -> slow with setpts, which suits this film because every
                            move in it is already slow (a push in, a track back, a
                            circle, a pull out)

Retiming past about 1.7x starts to look like slow motion rather than a slow
camera, so anything beyond that is reported rather than silently applied.

⚠ AUDIO COMES FROM THE ORIGINAL MIX, NOT FROM THE CLIPS.

Each clip carries whatever audio slice drove its generation. Using those would
stitch the song back together out of fragments. The full master is laid under the
finished cut instead, so timing is exact.
"""
import json
import os
import subprocess
import sys

ROOT = "/Users/hanumanji/demo/beenga-video-os"
BASE = f"{ROOT}/out/chhupke"
SONG = "/Users/hanumanji/demo/gs/songs/chupke/Chhupke Se Aa.wav"
OUT = f"{BASE}/chhupke-se-aa.mp4"
W, H, FPS = 832, 448, 30
XFADE = 0.5          # dissolve length; the treatment asks for smooth transitions

# Editorial substitutions: use another shot's footage in this slot. Chosen by eye
# in review, where a slot's own clip was weaker than one already rendered
# elsewhere. The shot's TIMING stays its own; only the picture is borrowed.
SUBSTITUTE = {
    "s04": "s01",
    "s08": "s11",
    "s16": "s07",
    "s18": "s01",   # closes on the opening image - a bookend
}
MAX_STRETCH = 1.7    # beyond this, slowing reads as slow motion


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip())


def parse_t(t):
    a, b = t.split("-")
    def s(v):
        m, sec = v.split(":")
        return int(m) * 60 + float(sec)
    return s(a), s(b)


def main():
    shots = json.load(open(f"{BASE}/shots.json"))["shots"]
    tmp = f"{BASE}/_seg"
    os.makedirs(tmp, exist_ok=True)
    segs, notes = [], []

    for sh in shots:
        sid = sh["id"]
        pick = SUBSTITUTE.get(sid, sid)
        # Prefer a lip-sync render if one exists for this shot, else the animated still.
        src = next((p for p in (f"{BASE}/clips-runpod/{pick}.mp4", f"{BASE}/clips/{pick}.mp4")
                    if os.path.exists(p)), None)
        if pick != sid:
            notes.append(f"{sid}: using {pick}'s footage")
        if not src:
            notes.append(f"{sid}: no clip, skipped")
            continue
        a, b = parse_t(sh["t"])
        # ⚠ Each dissolve OVERLAPS its two segments by XFADE, so an N-shot cut loses
        # (N-1)*XFADE overall. A first pass came out 9.3s short of a 114.5s song for
        # exactly this reason. Every segment except the last carries an extra XFADE
        # so the overlaps net out and the picture matches the track.
        want = round(b - a + (XFADE if sh is not shots[-1] else 0), 2)
        have = probe(src)
        out = f"{tmp}/{sid}.mp4"

        if want <= have:
            vf = f"scale={W}:{H},fps={FPS}"
            args = ["-t", str(want)]
        else:
            factor = want / have
            if factor > MAX_STRETCH:
                notes.append(f"{sid}: needs {factor:.2f}x stretch ({have:.1f}s -> {want:.1f}s) "
                             f"- capped at {MAX_STRETCH}x, will hold on the last frame")
                factor = MAX_STRETCH
            vf = f"setpts={factor:.4f}*PTS,scale={W}:{H},fps={FPS}"
            args = ["-t", str(want)]

        subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-i", src,
                        "-vf", vf, *args, "-an",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                        "-pix_fmt", "yuv420p", "-y", out], check=True)
        segs.append((sid, out, want))

    # Dissolve between shots rather than hard cutting: the treatment asks for smooth
    # transitions and explicitly rules out rapid cuts.
    if not segs:
        sys.exit("no segments")
    cur = segs[0][1]
    for i, (sid, path, dur) in enumerate(segs[1:], start=1):
        nxt = f"{tmp}/_acc{i}.mp4"
        off = max(0.1, probe(cur) - XFADE)
        subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-i", cur, "-i", path,
                        "-filter_complex",
                        f"[0][1]xfade=transition=fade:duration={XFADE}:offset={off},format=yuv420p[v]",
                        "-map", "[v]", "-c:v", "libx264", "-preset", "medium",
                        "-crf", "18", "-y", nxt], check=True)
        cur = nxt

    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-i", cur, "-i", SONG,
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-y", OUT], check=True)

    print(f"segments : {len(segs)}")
    print(f"video    : {probe(cur):.2f}s   song: {probe(SONG):.2f}s")
    print(f"output   : {OUT}")
    if notes:
        print("\nnotes:")
        for n in notes:
            print("  " + n)


if __name__ == "__main__":
    main()
