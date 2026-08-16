// Wave 0 — run the Beenga video benchmark against a base model and save clips.
//
// Raw prompts by default: this measures the BASE model's behaviour, which is the
// baseline every later wave is scored against. Pass --enhance once lib/prompt.mjs
// actually has rules in it.
//
//   node scripts/run-benchmark.mjs --model wan-video/wan-2.2-5b-fast --dry-run
//   node scripts/run-benchmark.mjs --model wan-video/wan-2.2-5b-fast --tag base-5b
//   node scripts/run-benchmark.mjs --only VID-MOT-001,VID-DEF-001 --seed 77 --tag spot
//
// TWO THINGS THIS RUNNER DOES THAT THE IMAGE ONE DID NOT, both because video costs
// 50-400x more per sample than an image:
//
//   1. --dry-run resolves everything — version, input schema, prompts, cost — and
//      spends nothing. Use it every time before a real run.
//   2. A cost ceiling. The run refuses to start if the estimate exceeds --max-cost
//      (default $5). A typo in --only that selects the whole suite at 720p should
//      not be discovered from a bill.
//
// WHY INPUTS ARE SCHEMA-FILTERED. The Wan family on Replicate is not one interface:
// t2v, i2v, s2v and the 5b variant differ in field names and in which fields exist
// at all, and they change as models are updated. Rather than hardcode a guess per
// model, we read the version's OpenAPI schema and send only fields it declares.
// Anything dropped is logged, so a silently ignored parameter shows up in the run
// record instead of quietly changing what we measured.
import fs from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { enhance, isEmpty } from "../lib/prompt.mjs";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const API = "https://api.replicate.com/v1";
const T = process.env.REPLICATE_API_TOKEN;
if (!T) { console.error("REPLICATE_API_TOKEN not set — copy .env.example to .env"); process.exit(1); }

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i === -1 ? d : argv[i + 1]; };
const has = (k) => argv.includes(k);

const MODEL    = arg("--model", "wan-video/wan-2.2-5b-fast");
const SEED     = Number(arg("--seed", "1234"));
const ONLY     = arg("--only", "")?.split(",").filter(Boolean);
const TAG      = arg("--tag", "baseline");
const RES      = arg("--res", "480p");
const MAX_COST = Number(arg("--max-cost", "5"));
const FRAMES   = arg("--frames", "");   // leave unset to use each model's native default
const FPS      = arg("--fps", "");      // ditto — see candidateInput()
const ENHANCE  = has("--enhance");
const DRY      = has("--dry-run");
const RETRY_FAILED = has("--retry-failed");

// Per-video prices, Replicate, checked 2026-08-15. Update alongside the README table.
// Used only for the pre-flight estimate and the run record — Replicate bills, not us.
const PRICE = { "480p": 0.05, "720p": 0.10 };
const unit = PRICE[RES] ?? 0.05;

const suite = JSON.parse(fs.readFileSync(path.join(ROOT, "benchmarks/beenga-video-v1.json"), "utf8"));
const outDir = path.join(ROOT, "out", TAG);

const auth = () => ({ Authorization: `Bearer ${T}`, "Content-Type": "application/json" });

/** Real duration of a written clip. Never inferred from the schema — see the note
 *  in candidateInput(). A model that advertises 121 frames and writes 81 is not a
 *  hypothetical; it is wan-2.2-5b-fast. */
function measureDuration(file) {
  const r = spawnSync("ffprobe", ["-v", "error", "-show_entries", "format=duration",
                                  "-of", "csv=p=0", file], { encoding: "utf8" });
  const v = Number(String(r.stdout || "").trim());
  return Number.isFinite(v) && v > 0 ? Number(v.toFixed(3)) : null;
}

async function resolveModel(model) {
  const r = await fetch(`${API}/models/${model}`, { headers: auth() });
  if (!r.ok) throw new Error(`${model}: HTTP ${r.status} — ${(await r.text()).slice(0, 160)}`);
  const j = await r.json();
  const v = j.latest_version;
  if (!v) throw new Error(`${model}: no latest_version — is the model public?`);
  const props = v.openapi_schema?.components?.schemas?.Input?.properties ?? {};
  const required = v.openapi_schema?.components?.schemas?.Input?.required ?? [];
  // The clip config we are choosing NOT to override. Recorded so a later reader can
  // tell whether two models were compared at the same duration.
  const native = {};
  for (const k of ["num_frames", "frames_per_second", "resolution", "aspect_ratio"]) {
    if (k in props) native[k] = props[k].default ?? null;
  }
  return { id: v.id, accepts: new Set(Object.keys(props)), required, native };
}

// Superset of everything any Wan variant might want. Filtered against the schema
// below, so adding a key here is safe even if most models ignore it.
//
// FRAME COUNT AND FPS ARE DELIBERATELY NOT SENT unless asked for with --frames/--fps.
//
// ⚠ CORRECTED 2026-08-16 — THE SCHEMA DEFAULT IS NOT WHAT THE MODEL PRODUCES.
//
// The original reasoning here was: 5b-fast defaults to 121 frames at 24fps and
// t2v-fast to 81 at 16fps, both ≈5 seconds, so leaving each on its own default
// compares equal durations at each model's native rate. That was read off the
// OpenAPI schema and never checked against a file.
//
// Measured across every clip in out/:
//
//   wan-2.2-5b-fast    81 frames  → 3.375s   (schema advertises 121 → 5.04s)
//   wan-2.2-t2v-fast   81 frames  → 5.062s   (matches)
//   wan-2.2-i2v-fast   81 frames  → 5.062s   (matches)
//   wan-2.2-s2v                   → 4.812s
//
// Only 5B disagrees with its own schema, and by 33%. So wave 0 compared 3.4s of 5B
// against 5.1s of A14B — the exact confound this comment claimed to be avoiding.
//
// The base-model decision survives it: "renders an Indian street vs a Chinese one"
// is not a thing 1.7 seconds explains. But any TEMPORAL comparison between the two
// is invalid, and the cost-per-second figures were wrong (see the README).
//
// The fix is not to trust a different number — it is to MEASURE the output. Every
// clip's real duration now goes into runs.json under `measured_duration_s`.
function candidateInput(c, prompt) {
  const input = {
    prompt,
    seed: SEED,
    resolution: RES,       // enum ['480p','720p'] on the fast variants; absent on s2v
    aspect_ratio: "16:9",  // enum ['16:9','9:16']; absent on i2v, which takes it from the image
    go_fast: true,

    // BOTH OF THESE ARE OFF ON PURPOSE. Neither default is safe for a benchmark.
    //
    // interpolate_output defaults to TRUE on t2v-fast and FALSE on i2v-fast. It
    // interpolates the clip to 30fps with ffmpeg. Leaving it at its default would
    // (a) make t2v and i2v results incomparable, and (b) contaminate every temporal
    // measurement in this suite — interpolated frames are synthesised, so scoring
    // motion coherence or frame-to-frame identity on them measures ffmpeg rather
    // than Wan. Interpolation is a fine production choice; it is not a measurement
    // surface.
    interpolate_output: false,
    //
    // optimize_prompt translates the prompt to Chinese before generation. Whatever
    // it does to quality, it is a prompt rewriter, and wave 0 exists to measure the
    // model's response to OUR prompt. Turning it on would put an unversioned rewriter
    // between the benchmark and the result. Worth testing deliberately later; never
    // on by accident.
    optimize_prompt: false,
    // i2v / s2v only — resolved to real URLs or file paths before use.
    image: c.image ?? null,
    audio: c.audio ?? null,
  };
  if (FRAMES) input.num_frames = Number(FRAMES);
  if (FPS) input.frames_per_second = Number(FPS);
  return input;
}

// Replicate takes file inputs as a URL or a data URI, never a local path. A path
// string is accepted by the API and then fails inside the model, which bills as a
// failed prediction — so convert here rather than discovering it per case.
const MIME = { ".wav": "audio/wav", ".mp3": "audio/mpeg", ".png": "image/png",
               ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp" };

function asDataUri(rel) {
  const abs = path.isAbsolute(rel) ? rel : path.join(ROOT, rel);
  const mime = MIME[path.extname(abs).toLowerCase()];
  if (!mime) throw new Error(`no mime type for ${rel}`);
  return `data:${mime};base64,${fs.readFileSync(abs).toString("base64")}`;
}

function filterInput(cand, accepts) {
  const sent = {}, dropped = [];
  for (const [k, v] of Object.entries(cand)) {
    if (v === null || v === undefined) continue;
    if (!accepts.has(k)) { dropped.push(k); continue; }
    sent[k] = (k === "image" || k === "audio") && typeof v === "string" && !/^(https?|data):/.test(v)
      ? asDataUri(v) : v;
  }
  return { sent, dropped };
}

/** Log-safe copy — a 200KB base64 audio blob in runs.json makes it unreadable. */
const summarise = (sent) => Object.fromEntries(Object.entries(sent).map(([k, v]) =>
  [k, typeof v === "string" && v.startsWith("data:") ? `${v.slice(0, 24)}…(${v.length}b)` : v]));

const sleep = (ms) => new Promise((s) => setTimeout(s, ms));

// Replicate throttles prediction CREATION, and the limit is per account — so two
// benchmark runs going at once share it. The first real wave-0 run lost 16 of 23
// cases to HTTP 429 because this function had no retry: a transient throttle came
// back as a per-case FAIL, and the partial result set looked like a finished run.
// A benchmark that silently drops two thirds of its cases is worse than one that
// stops, so 429 is now retried rather than recorded.
async function createPrediction(version, input, tries = 7) {
  for (let n = 0; n < tries; n++) {
    const r = await fetch(`${API}/predictions`, {
      method: "POST", headers: auth(), body: JSON.stringify({ version, input }),
    });
    if (r.ok) return r.json();
    if (r.status !== 429) throw new Error(`HTTP ${r.status} — ${(await r.text()).slice(0, 200)}`);
    // Respect Retry-After when Replicate sends it; otherwise back off exponentially.
    const wait = Number(r.headers.get("retry-after")) * 1000 || Math.min(60000, 4000 * 2 ** n);
    process.stdout.write(`429 wait ${Math.round(wait / 1000)}s… `);
    await sleep(wait);
  }
  throw new Error(`rate limited after ${tries} attempts`);
}

async function generate(version, input) {
  let j = await createPrediction(version, input);
  // Video takes ~30s on the fast variants and minutes on the unoptimised ones.
  // Poll slower than the image runner did; there is nothing to gain from 900ms.
  while (!["succeeded", "failed", "canceled"].includes(j.status)) {
    await sleep(3000);
    const p = await fetch(`${API}/predictions/${j.id}`, { headers: auth() });
    if (p.status === 429) continue;   // polling is cheap; just wait another tick
    if (!p.ok) throw new Error(`poll HTTP ${p.status}`);
    j = await p.json();
  }
  if (j.status !== "succeeded") throw new Error(`${j.status}: ${j.error ?? "no detail"}`);
  return { url: Array.isArray(j.output) ? j.output[0] : j.output, predict: j.metrics?.predict_time ?? null };
}

// ── select cases ─────────────────────────────────────────────────────────────

let cases = ONLY?.length ? suite.cases.filter((c) => ONLY.includes(c.id)) : suite.cases;

// --retry-failed re-runs only what did not generate last time under this tag. Needed
// because the first wave-0 run lost most of its cases to a rate limit; without it the
// choice is re-paying for the clips that already succeeded or hand-listing the rest.
const priorPath = path.join(outDir, "runs.json");
const prior = fs.existsSync(priorPath) ? JSON.parse(fs.readFileSync(priorPath, "utf8")) : null;
if (RETRY_FAILED) {
  if (!prior) { console.error(`--retry-failed: no prior run at ${priorPath}`); process.exit(1); }
  const done = new Set(prior.runs.filter((r) => r.status === "generated").map((r) => r.id));
  cases = cases.filter((c) => !done.has(c.id));
  console.log(`--retry-failed: ${done.size} already generated, ${cases.length} to retry\n`);
}

// A case that needs a still or an audio track cannot run until that asset exists.
// Skip loudly rather than sending a broken request and paying for the failure.
const skipped = [];
cases = cases.filter((c) => {
  const need = c.needs ?? "t2v";
  if (need === "t2v") return true;
  const asset = need === "s2v" ? c.audio : c.image;
  const ok = asset && fs.existsSync(path.join(ROOT, asset));
  if (!ok) skipped.push({ id: c.id, needs: need, missing: asset ?? "(unspecified)" });
  return ok;
});

const shots = cases.reduce((n, c) => n + (c.repeat ?? 1), 0);
const estimate = shots * unit;

console.log(`suite     ${suite.suite}`);
console.log(`model     ${MODEL}`);
console.log(`res/seed  ${RES} / ${SEED}${ENHANCE ? "  (prompt layer ON)" : ""}`);
console.log(`cases     ${cases.length}  →  ${shots} clips`);
console.log(`estimate  ~$${estimate.toFixed(2)} at $${unit.toFixed(2)}/clip`);
console.log(`out       ${outDir}\n`);

// A "wave 1" run against an empty prompt layer produces baseline output under a
// wave-1 tag, which is exactly how a false result gets into a table.
if (ENHANCE && isEmpty()) {
  console.log("WARNING: --enhance passed but lib/prompt.mjs has no rules yet.");
  console.log("         This run is identical to a baseline run. Tag it accordingly.\n");
}

if (skipped.length) {
  console.log("skipped — asset missing:");
  for (const s of skipped) console.log(`  ${s.id.padEnd(14)} needs ${s.needs}, missing ${s.missing}`);
  console.log("");
}

if (estimate > MAX_COST) {
  console.error(`refusing to run: estimate $${estimate.toFixed(2)} exceeds --max-cost $${MAX_COST.toFixed(2)}`);
  console.error(`raise it deliberately with --max-cost ${Math.ceil(estimate)} if that is what you meant.`);
  process.exit(1);
}

const model = await resolveModel(MODEL);
console.log(`version   ${model.id}`);
const nf = model.native.num_frames, nfps = model.native.frames_per_second;
if (nf && nfps) console.log(`native    ${nf} frames @ ${nfps}fps  ≈ ${(nf / nfps).toFixed(2)}s${FRAMES || FPS ? "  (OVERRIDDEN)" : ""}`);
console.log(`accepts   ${[...model.accepts].join(", ")}\n`);

// ── run ──────────────────────────────────────────────────────────────────────

if (!DRY) fs.mkdirSync(outDir, { recursive: true });

const runs = [];
for (const c of cases) {
  const reps = c.repeat ?? 1;
  for (let i = 0; i < reps; i++) {
    const label = reps > 1 ? `${c.id}-r${i}` : c.id;
    process.stdout.write(`${label.padEnd(18)} ${c.concept.padEnd(30)} `);

    const e = ENHANCE ? enhance(c.prompt) : { prompt: c.prompt, applied: [] };
    const cand = candidateInput(c, e.prompt);
    // Each repeat gets its own seed — VID-ID-006 measures identity drift ACROSS
    // independent generations, so reusing one seed would measure nothing.
    if (cand.seed !== undefined) cand.seed = SEED + i;
    const { sent, dropped } = filterInput(cand, model.accepts);

    const missing = model.required.filter((k) => !(k in sent));
    if (missing.length) {
      console.log(`SKIP required field(s) not supplied: ${missing.join(", ")}`);
      runs.push({ ...c, label, status: "skipped", reason: `missing required: ${missing.join(",")}` });
      continue;
    }

    if (DRY) {
      console.log(`dry  sends[${Object.keys(sent).join(",")}]${dropped.length ? `  drops[${dropped.join(",")}]` : ""}`);
      runs.push({ ...c, label, status: "dry-run", sent_prompt: e.prompt, applied: e.applied, sent: summarise(sent), dropped });
      continue;
    }

    try {
      const g = await generate(model.id, sent);
      const buf = Buffer.from(await (await fetch(g.url)).arrayBuffer());
      const file = `${label}.mp4`;
      const written = path.join(outDir, file);
      fs.writeFileSync(written, buf);
      const measured = measureDuration(written);
      runs.push({
        ...c, label, file, sent_prompt: e.prompt, applied: e.applied, sent: summarise(sent), dropped,
        predict: g.predict, measured_duration_s: measured, status: "generated", score: null, observed: null,
      });
      console.log(`ok   ${g.predict?.toFixed(1)}s gen  ${measured ?? "?"}s clip${dropped.length ? `  drops[${dropped.join(",")}]` : ""}`);
    } catch (err) {
      runs.push({ ...c, label, file: null, status: "error", error: String(err.message).slice(0, 200) });
      console.log(`FAIL ${err.message.slice(0, 90)}`);
    }
  }
}

const record = {
  suite: suite.suite, model: MODEL, version: model.id, seed: SEED, resolution: RES,
  tag: TAG, enhanced: ENHANCE, prompt_layer_empty: isEmpty(), dry_run: DRY,
  native_clip_config: model.native, overrides: { frames: FRAMES || null, fps: FPS || null },
  skipped, runs,
};

if (!DRY) {
  // Merge over any prior run under this tag, keyed by label, so a retry pass never
  // discards clips that already succeeded and were already paid for.
  if (prior) {
    const byLabel = new Map(prior.runs.map((r) => [r.label ?? r.id, r]));
    for (const r of runs) byLabel.set(r.label ?? r.id, r);
    record.runs = [...byLabel.values()];
    record.merged_from_prior = true;
  }
  fs.writeFileSync(priorPath, JSON.stringify(record, null, 2));
  const ok = runs.filter((r) => r.status === "generated").length;
  const total = record.runs.filter((r) => r.status === "generated").length;
  console.log(`\n${ok}/${runs.length} generated this pass → ${priorPath}`);
  console.log(`${total} generated under tag '${TAG}' in total`);
  console.log(`billed roughly $${(ok * unit).toFixed(2)} this pass`);
} else {
  console.log(`\ndry run — nothing sent, nothing spent. ${runs.length} clips would cost ~$${estimate.toFixed(2)}.`);
}
