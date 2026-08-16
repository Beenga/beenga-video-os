# Long-form — can this make a three-minute video?

> **Validated on the real deliverable, 2026-08-16.** `out/mv-full/` is 175.7s, 36/36 shots, mixed
> s2v and i2v routing. All 36 shots have a detectable face. s2v mean CSIM 0.791, i2v 0.766, and
> both the reset and chained groups are flat across three minutes (0.697→0.712 and 0.849→0.853).
>
> ⚠ **Three shots scored below the 0.6 same-person line and it is a measurement artefact, not a
> defect.** Shots 6, 14 and 26 — all s2v, all conditioned on the reference still. Looking at the
> frames: the same woman, singing with her eyes closed and her head tilted mid-note. ArcFace is
> pose- and expression-sensitive, and a neutral reference still scores badly against an
> eyes-closed open-mouthed frame.
>
> **CSIM against a neutral still is not a reliable identity metric for expressive singing
> content.** It was reliable for the pure-i2v chain test, where every clip was a similar talking
> pose. Do not port the threshold across without re-validating it — the same mistake as reading
> mouth-activity ratios before there was a floor clip.

Run 2026-08-15 on `wan-2.2-i2v-fast`. Two strategies, six clips each (~30s of video per
strategy), one shared reference still, 12 clips, **$0.60**.

Cross-clip identity was already cleared in wave 0 — three independent clips from one still
scored mean CSIM 0.796. What that did not test is whether clips **join**. This does.

## Result

| | Median join cost | Identity vs the original still |
|---|---|---|
| **`chain`** — clip N+1 conditioned on the last frame of clip N | **×0.25** (seamless) | 0.859 → **0.518** (**−0.341**) |
| **`anchor`** — every clip conditioned on the same still | ×3.82 (visible cut) | 0.859 → **0.872** (+0.013) |

Join cost is the seam's visual step as a multiple of that clip's own natural frame-to-frame step,
so a clip that moves a lot is not penalised for it. ×1.0 is indistinguishable from an ordinary
frame advance.

Both predicted shapes held. The magnitudes are the useful part.

### Chain fails in about twenty seconds

Per-clip identity against the original still:

```
c0 0.859   c1 0.744   c2 0.685   c3 0.595   c4 0.567   c5 0.518
```

Drift is roughly linear at **−0.068 per clip** and crosses the ~0.6 same-person threshold at
**clip 3 — around 20 seconds.** Extrapolated to the 36 clips a three-minute song needs, the
endpoint is not a degraded singer, it is a different person.

So: chaining is excellent for a single continuous shot of up to about fifteen seconds, and
unusable as a long-form strategy on its own. That is much earlier than expected and is the most
useful number in this file.

### Anchor holds identity and pays for it at every seam

Identity is flat across the whole chain — it drifts *up* by 0.013, which is noise. Every seam is
a ×3.8 step, because each clip restarts from the same pose.

## What this actually means, which is less bad than it sounds

**A music video is cut.** A hard cut every few seconds is the idiom, not a defect — the failure
would be a cut in the *wrong place*, not a cut at all. `anchor` produces exactly one artefact:
a visual discontinuity at a predictable moment. If those moments land on musical boundaries,
they stop being artefacts and become edits.

And the boundaries are already computed. `beenga-in/lib/lyria.mjs::planFromSections` returns
section starts from Lyria's structure map, with this note already in it:

> *cutting on a chorus boundary is musical, cutting on a lyric line is arbitrary*

So the viable three-minute path today is **anchor mode with seams placed on section
boundaries**, not chain mode. It needs no new model and no training.

## Open, and worth a cheap test

**~~Periodic re-anchoring.~~ Measured — and it wins.** `--reanchor 2` chains one clip, resets to
the original still, repeats.

| Mode | Median join cost | Identity min | Pattern |
|---|---|---|---|
| `chain` | ×0.25 | **0.518** — below threshold | monotonic collapse |
| `anchor` | ×3.82 | 0.788 | flat |
| **`reanchor2`** | **×0.74** | **0.643** | **bounded sawtooth** |

Re-anchoring beats `anchor` on joins by 5x and beats `chain` on identity decisively. But the
important property is not the averages — it is that **the drift stops accumulating.** Read
like-for-like rather than first-against-last:

```
anchored clips  c0 0.859   c2 0.788   c4 0.830     flat
chained  clips  c1 0.744   c3 0.643   c5 0.715     flat
```

Every reset returns to the same band, and the chained clips oscillate around a floor near 0.68
instead of walking away. **36 clips should therefore look like 6.** That is what makes three
minutes viable, and it is a stronger claim than "the average is acceptable".

⚠ The `delta` printed by `score-chain.py` is misleading for this mode — it compares c0 (anchored)
against c5 (chained) and reports −0.144, which reads as decline when the series is actually
stable. A sawtooth needs like-for-like comparison. The scorer should be fixed to group by
conditioning source before that field is quoted.

### Recommended production setting

**`--reanchor 2`, with the re-anchor seams placed on section boundaries** from
`beenga-in/lib/lyria.mjs::planFromSections`. The chained seams are invisible (×0.37–0.74); the
reset seams (×1.68, ×2.43) are the ones a viewer might notice, and those are exactly the ones
that can be made to land on a chorus.

**~~Whether the drift is identity or exposure.~~ Checked — it is identity.** CSIM falling could
have been the chain slowly darkening or blurring rather than the face changing. It is not:

| | luma | contrast | sharpness (var. of Laplacian) |
|---|---|---|---|
| `chain` c0→c5 | 84.4 → 80.8 (−4%) | 61.5 → 62.4 (flat) | 90.6 → **156.3** |
| `anchor` c0→c5 | flat | flat | flat |

The chain does not darken and does not blur — it gets **sharper**. So the −0.341 is a real
change of face, and the number can be quoted.

**Secondary defect, logged separately: the chain over-sharpens.** Sharpness rises 73% over six
clips, the classic feedback-loop artefact of feeding a generation back into itself. Not visible
at six clips. It would be at thirty-six, and it is another reason pure chaining does not scale.

**Not yet tested at three minutes.** Everything here is a 6-clip extrapolation. The linear fit is
clean, but a 36-clip run is the only way to know it stays linear, and it costs $1.80.

## Method

- `scripts/chain-test.mjs` generates both strategies; `scripts/score-chain.py` scores them.
- Identity is measured against the ORIGINAL still, never against the previous clip — comparing
  neighbours reports every step as small while the chain walks away from the starting face.
- Each clip gets its own seed, so "the chain drifted" is not confounded with "the seed repeated
  a motion".
- Expected shapes were written into the script docstring before the run, so the result could
  contradict them. It did not, but the join magnitudes were not predicted.
