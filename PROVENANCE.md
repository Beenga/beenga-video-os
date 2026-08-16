# Provenance lock

Evidence that each upstream component was licensed as claimed, at the revision we actually took.

An Apache-2.0 grant is irrevocable (§2), but only for the revision you received. If a repository
is later deleted, gated, or relicensed for future versions, this file plus the mirror is what
proves what we were granted and lets us keep building. A tag is not evidence — tags move.
**Pin the commit SHA.**

---

## Finding: there are no LICENSE files

Checked 2026-08-15 across every component below. **Not one of them ships a `LICENSE` or `NOTICE`
file in its Hugging Face repo.** The licence is declared only in the YAML frontmatter of
`README.md` — an ordinary, editable file with no special status.

Two consequences:

1. **The snapshot matters more, not less.** There is no licence file to hash. The evidence that
   a component was Apache-2.0 is the model card *as it read at a specific SHA*. Archive
   `README.md` at the pinned SHA and hash that.
2. **Apache §4(d) does not currently apply.** NOTICE propagation is only triggered when upstream
   ships a NOTICE file. None do. Same conclusion `beenga-image` reached for BFL's `flux2` repo —
   and the same caveat: re-check if you re-vendor at a later commit.

## Finding: two licences are not what the ecosystem says they are

Both were caught by querying the Hub API rather than reading summaries.

| Component | Commonly stated | **Actually tagged** |
|---|---|---|
| `TMElyralab/MuseTalk` | MIT | **`creativeml-openrail-m`** |
| `stabilityai/sd-vae-ft-mse` | CreativeML OpenRAIL-M | **`mit`** |

MuseTalk's *code* repo on GitHub is MIT. Its *weights* repo on Hugging Face is tagged
CreativeML OpenRAIL-M. Arm B is therefore more encumbered than the GitHub licence suggests, and
the encumbrance comes from MuseTalk's own card — not, as we first assumed, from the VAE it pulls
in. The VAE is clean.

This is the second time on this project that a licence turned out to differ from the one
everybody repeats. Assume it will happen again and check the API, not the blog post.

---

## Components

Status: `pending` — not yet mirrored. `locked` — SHA pinned, card archived, weights mirrored.

Revision SHAs resolved 2026-08-15.

| Component | Licence (card) | Revision SHA | Arm | Status |
|---|---|---|---|---|
| `Wan-AI/Wan2.2-TI2V-5B` | `apache-2.0` | `921dbaf3f1674a56f47e83fb80a34bac8a8f203e` | base | pending |
| `Wan-AI/Wan2.2-T2V-A14B` | `apache-2.0` | `c8c270b13ee05bfa474194ac9fb07a5868a97cea` | base | pending |
| `Wan-AI/Wan2.2-I2V-A14B` | `apache-2.0` | `206a9ee1b7bfaaf8f7e4d81335650533490646a3` | A, B | pending |
| `Wan-AI/Wan2.2-S2V-14B` | `apache-2.0` | `dab4e9c55bbe4c8c4d03db1c2c98c7f0ac9c454b` | C | pending |
| `MeiGen-AI/InfiniteTalk` | `apache-2.0` | `d59847ebda` — resolve full | **D** | pending |
| `MeiGen-AI/MeiGen-MultiTalk` | `apache-2.0` | `b3ccbea2f6` — resolve full | D (predecessor) | pending |
| `BadToBest/EchoMimicV3` | `apache-2.0` | `311e176905` — resolve full | E | pending |
| `Wan-AI/Wan2.2-Animate-2-14B` | `apache-2.0` | `6e8f1973bf` — resolve full | F | pending |
| `vinthony/SadTalker` | `mit` | `4aedd06435` — resolve full | fallback | pending |
| `openai/whisper-large-v3` | `apache-2.0` | `06f233fe06e710322aca913c1bc4249a0d71fce1` | shared | pending |
| ~~`ByteDance/LatentSync-1.6`~~ | ~~`openrail++`~~ | `c42c7e6c8e9c213626389fa7d9a3c444b8536353` | ~~A~~ | **excluded** |
| ~~`TMElyralab/MuseTalk`~~ | ~~`creativeml-openrail-m`~~ | `3ef28bc5cff08c90ad8178a25f1b570cd800170f` | ~~B~~ | **excluded** |
| ~~`stabilityai/sd-vae-ft-mse`~~ | `mit` | `31f26fdeee1355a5c34592e401dd41e45d25a493` | ~~B~~ | not needed |
| ai-toolkit / DiffSynth-Studio | verify | — resolve git SHA | training | pending |

The two struck-through rows are the reason this file exists. Both were going to be shipped on the
strength of a licence claim that a five-second API call disproved.

**Requirement change, 2026-08-15: Apache-only, freely distributable, upgradable forever.** That
excludes both OpenRAIL components outright — not on quality, but because a propagating
behavioural restriction is the licence locking the requirement rules out. The replacement arms
(D/E/F) are all Apache-2.0 or MIT, verified the same way. `sd-vae-ft-mse` leaves the tree with
MuseTalk; it was clean anyway.

## How to record a component

```bash
# resolve the revision SHA
curl -s https://huggingface.co/api/models/Wan-AI/Wan2.2-TI2V-5B | jq -r '.sha, .cardData.license'

# archive the model card AT that revision — it is the only statement of the licence
SHA=921dbaf3f1674a56f47e83fb80a34bac8a8f203e
mkdir -p licenses/wan2.2-ti2v-5b
curl -sL "https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B/raw/$SHA/README.md" \
  | tee "licenses/wan2.2-ti2v-5b/MODEL_CARD@$SHA.md" | shasum -a 256

# mirror the weights under a path containing the SHA
huggingface-cli download Wan-AI/Wan2.2-TI2V-5B --revision "$SHA" --local-dir ./dl
rclone copy ./dl "r2:beenga-weights/wan2.2-ti2v-5b/$SHA/"
```

## Mirror layout

```
r2://beenga-weights/<component>/<revision-sha>/...
                    licenses/<component>/MODEL_CARD@<sha>.md
                    licenses/<component>/sha256.txt
```

**The mirror must not live on Hugging Face.** The whole point is a second failure domain — if
the Hub removes an upstream repo for a legal reason, a copy on the same Hub goes with it. Use
object storage on unrelated infrastructure.

Approximate sizes, to confirm at mirror time: TI2V-5B ~20GB · A14B variants ~60–80GB each ·
S2V-14B ~50–60GB · LatentSync ~5GB · MuseTalk ~10GB. Everything is ~250GB; only the arms that
survive wave 0 is ~100GB.

At Cloudflare R2 ($0.015/GB-month, no egress fees) that is **$1.50–$3.75/month**. At Backblaze
B2 ($0.006/GB-month), **$0.60–$1.50/month**.

## Re-check triggers

- A component is upgraded to a new revision — the licence may differ at the new SHA.
- An upstream repo changes owner or org.
- Before any public release of weights or a self-hostable pipeline.
- Before describing any Beenga artefact as "Apache-2.0" in public.
