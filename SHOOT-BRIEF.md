# Shoot brief — training footage for the Beenga India LoRA

Hand this to whoever shoots. It is written for them, not for us.

## What this is for, in one paragraph

We are fine-tuning a video-generation model so that it renders **contemporary India** correctly.
Right now, asked for "a busy street in Mumbai", it produces a Chinese street, a Southeast Asian
street, or a European boulevard — measured across three attempts, none of them India. The footage
below is what teaches it. It is training data, not a showreel: **authenticity and variety matter
far more than production polish.**

## How much

| | |
|---|---|
| **Minimum useful** | 60 clips |
| **Target** | 100–150 clips |
| **Usable length per clip** | **3–6 seconds** |
| Shoot length per clip | 10–15 seconds, so there is a clean 3–6s to trim from |
| Realistic schedule | 2–3 days for 100–150 |

Below ~50 the model overfits to the specific streets and rooms it was shown. Above ~150 the
return flattens for this kind of adapter. **Start at 100. More clips of more places beats longer
clips of fewer places.**

## What to shoot

Weighted toward where the model is measurably worst. Numbers are for a 100-clip target.

| Bucket | Clips | What specifically |
|---|---|---|
| **Streets and public space** | 20 | Traffic, footpaths, markets, autos, buses, metro entrances, shopfronts, street food. Ordinary weekday India. |
| **Homes and interiors** | 15 | Kitchens, living rooms, balconies, terraces, stairwells. Middle-class, lived-in, not styled. |
| **People, medium and close** | 15 | Individuals walking, talking, working, waiting. **Everyday clothing** — kurti, jeans, shirts, cotton saris. Not bridal, not styled. |
| **Workplaces and study** | 10 | Offices, shops, workshops, campuses, co-working, small businesses. |
| **Groups and families** | 10 | Two to five people together — eating, talking, walking, at home. Groups are where the model fails hardest. |
| **Transport and movement** | 10 | Inside autos, trains, buses, on bikes. Motion through a scene. |
| **Festival and celebration** | 10 | Weddings, puja, festival streets. **This bucket keeps the traditional register working** — without it, teaching "contemporary" can break the model's ability to render a wedding when asked. |
| **Evening and night** | 10 | Everything above, after dark. Lit interiors, street lighting, shops at night. |

## What makes a clip usable — this part matters most

**Every clip must have motion.** This is video training data. A locked-off shot of a static scene
teaches the model nothing about how anything moves. Either the camera moves (slow pan, slow push,
walk-along) or the subject does. Ideally both.

**One continuous take per clip. No cuts inside a clip.** A cut mid-clip teaches the model to cut
mid-shot, and it will.

**Technical minimums:**

- 1080p or better, **16:9 landscape**
- 24, 25 or 30 fps, consistent
- Reasonably stable — gimbal or steady hands. Slow deliberate movement, not handheld jitter
- Sharp focus on the subject. Soft or motion-blurred footage teaches softness and blur
- Well exposed. Blown highlights and crushed blacks both carry through into the model
- **No on-screen text, captions, watermarks, logos or timestamps.** Models learn text as texture
  and reproduce garbled versions of it forever
- Audio is irrelevant — it is discarded

**What ruins a clip:**

- Zooms, whip pans, snap moves
- Anything shot vertically
- Filters, LUTs, heavy grading, slow motion, timelapse
- Obvious stock-footage staging — the defect is that the model's India is generic, so generic
  footage will not fix it
- Recognisable brand logos filling the frame

## Rights — read before shooting

**This footage trains a model. That is a different permission from "appearing in a video."**

- **Anyone recognisable needs a written release** that explicitly covers *use as AI/ML training
  data*. A standard model release usually does not.
- **Do not buy stock footage for this.** Most stock licences explicitly forbid using the footage
  as training data. Buying 100 clips and training on them could make the resulting model
  unpublishable — which would defeat the entire point, since everything in this project is
  Apache-2.0 and meant to be released.
- Crowds and public spaces are generally fine; individuals in close-up are not, without a release.
- **Do not shoot children.** Nothing in this project depicts minors, and training data is where
  that starts.
- Record for every clip: date, location, who shot it, and whether releases exist.

## What you do NOT need to hire

**A professional videographer may be overkill.** The training resolution is 480–720p; the model
needs *authentic and varied*, not *cinematic*. A recent phone on a cheap gimbal, shot by someone
with a good eye who lives in the city, produces better training data than a polished commercial
crew shooting staged setups — because the failure being fixed is exactly that the model's India
looks staged and generic.

Where a professional genuinely helps: consistent exposure, steady movement, and getting 100 clips
done in two days instead of two weeks.

## Delivery

- One file per clip, named by bucket: `street-001.mp4`, `home-014.mp4`
- Original camera files, unedited and ungraded — trimming happens here
- A simple sheet: filename, location, city, date, one line of description, release yes/no

We caption and trim. **Do not add captions, titles, or edits of any kind.**
