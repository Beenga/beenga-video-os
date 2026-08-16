# Wave 1 — prompt layer

Run 2026-08-15 on `wan-2.2-5b-fast`, the base chosen in wave 0. Six default-behaviour cases,
three seeds each, 18 clips, **$0.90**. Compared against baselines already on disk at the same
three seeds: same model, same seeds, one variable.

Two rules, both earned by 3-seed evidence rather than ported on faith. See `lib/prompt.mjs`.

## Result: the era rule works, the dress rule does not

| Case | Baseline (3 seeds) | Wave 1 (3 seeds) | Verdict |
|---|---|---|---|
| `VID-DEF-001` rooftop in Delhi | Silk sari, heavy gold, ceremonial styling | Cleaner contemporary rooftops, gold load clearly reduced, sunglasses on one seed — **but a sari on 3/3** | **partial** |
| `VID-DEF-002` portrait | Red-gold brocade, jhumkas, nose ring, jasmine, festival bokeh | Domestic settings, jewellery much reduced — **but a sari on 3/3, and ceremonial props (marigold garlands, puja) survive on 2/3** | **partial** |
| `VID-DEF-005` bridal **(guard)** | Correct traditional bridal | **Byte-identical** — the layer fires no rules on stated traditional intent | **pass** |
| `VID-DEF-003` / `004` / `006` | Already acceptable | Undisturbed | **no regression** |

**The guard result is the most reassuring one.** `VID-DEF-005` output is identical to baseline
because `enhance()` correctly applied nothing to it. A contemporary default that quietly stripped
a requested lehenga would have turned a passing case into a failing one, which is worse than the
defect it was fixing.

## What moved and what did not

- **Setting and era: fixed.** Weathered/ceremonial backdrops became clean contemporary ones on
  3/3 for both target cases.
- **Jewellery load: substantially reduced** on 3/3.
- **Garment: unchanged.** A sari on 3/3 of both cases, with `Modern everyday clothing.` present in
  the prompt every time.

Whether a sari is a *failure* deserves care — it is ordinary everyday dress for millions of women,
and calling it a stereotype would itself be a bad prior. The benchmark's claim is narrower: for
"a young Indian woman standing on a rooftop in Delhi", a model that returns a sari on 3 of 3
seeds and never a kurti, jeans or a shirt is expressing a default, not a preference. The
comparable image-side result was "clean modern terrace, shirt and jeans". The distribution is the
defect, not any single frame.

## The next experiment is cheap and already suggested by the sibling repo

`beenga-image` records that a single restatement of an attribute loses, and that **five stacked
positive restatements win** — that is what fixed clean-shaven (3-of-4 failures → 6/6) and then
complexion. `Modern everyday clothing.` is a single mention competing against a strong prior. It
lost, exactly as one mention did there.

So wave 1.1: **stack the dress instruction** the way `SHAVE_STACK` is stacked, and re-run the two
target cases at three seeds. Costs about $0.30 and is free to write.

If stacking fixes it, this whole defect closes for **$1.20 total and no training**, and the LoRA
question moves to whatever else survives. If stacking does not fix it, the garment default is the
first genuine training target this project has found — and it is a narrow one, which is good news
for dataset size.

## Method notes

- Judged visually across three seeds per case. No instrument exists for "is this garment
  contemporary", and inventing a confident-looking one would repeat the mistake the mouth-activity
  threshold made before it had a floor.
- Regression probes were checked for disturbance, not scored.
- Wave 1 spend $0.90. Project total to date ~$5.80.
