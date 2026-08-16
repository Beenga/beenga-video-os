// The deliverable: one song in, one lip-synced music video out, up to three minutes.
//
//   node scripts/make-music-video.mjs --song ~/demo/gs/songs/bhor-bhajan --dry-run
//   node scripts/make-music-video.mjs --song ~/demo/gs/songs/bhor-bhajan --seconds 60
//   node scripts/make-music-video.mjs --song ... --lora-high URL --lora-low URL
//
// Everything here is a measured result from this repo, wired together. Nothing is
// a guess, and each decision below names the case that produced it.
//
// ── WHY TWO MODELS AND NOT ONE ───────────────────────────────────────────────
//
// S2V generates motion FROM AUDIO; i2v generates motion FROM A PROMPT. They cannot
// both drive one clip, so shots are ROUTED:
//
//   singer is audibly singing  ->  s2v          lip sync is the point
//   instrumental passage       ->  i2v          no vocal to sync to, so use the
//                                               prompt (and, later, the Beenga LoRA)
//
// This is also what a real music video does — performance shots cut with b-roll.
//
// ── WHY THE VOCAL STEM AND NEVER THE MASTER ──────────────────────────────────
//
// VID-SING-010: fed an instrumental passage, S2V articulates at 95% of the vocal
// rate. It responds to audio ENERGY, not vocal content, so a master track makes
// the singer mouth through the intro, the break and the outro.
//
// VID-SING-013, 2 of 2 seeds: fed the Demucs vocal stem, the mouth stops when the
// singing stops. So s2v shots get the STEM. The master is muxed back over the
// finished video at the end, where it belongs.
//
// ── WHY reanchor 2 ───────────────────────────────────────────────────────────
//
// Measured over 36 clips (LONGFORM.md):
//   chain     seamless joins (x0.25) but identity collapses to 0.518 by ~20s
//   anchor    identity flat, but every seam is a visible cut (x3.82)
//   reanchor2 joins x0.74, identity BOUNDED — both groups trend -0.029 over 3 min
//
// So: chain one clip off the previous, then reset to the reference still, repeat.
//
// ── WHY CUTS LAND ON SECTION BOUNDARIES ──────────────────────────────────────
//
// The reset seams are the only ones a viewer might notice. Lyria returns section
// starts, and beenga-in/lib/lyria.mjs already says it: "cutting on a chorus
// boundary is musical, cutting on a lyric line is arbitrary." Reset shots are
// therefore aligned to the nearest section start.
import fs from "node:fs";
import path from "node:path";
import { execFileSync, spawnSync } from "node:child_process";

const API = "https://api.replicate.com/v1";
const T = process.env.REPLICATE_API_TOKEN;
if (!T) { console.error("REPLICATE_API_TOKEN not set"); process.exit(1); }

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i === -1 ? d : argv[i + 1]; };
const has = (k) => argv.includes(k);

const ROOT     = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const SONG_DIR = arg("--song", "");
const STILL    = arg("--still", path.join(ROOT, "stills/singer.png"));
const SECONDS  = Number(arg("--seconds", "180"));
const TAG      = arg("--tag", "musicvideo");
const REANCHOR = Number(arg("--reanchor", "2"));
const MAX_COST = Number(arg("--max-cost", "5"));
const LORA_HI  = arg("--lora-high", "");
const LORA_LO  = arg("--lora-low", "");
const DRY      = has("--dry-run");

if (!SONG_DIR) { console.error("--song <dir with master.mp3, guide-vocal.mp3>"); process.exit(1); }

const MASTER = path.join(SONG_DIR, "master.mp3");
const STEM   = path.join(SONG_DIR, "guide-vocal.mp3");
for (const f of [MASTER, STEM, STILL]) {
  if (!fs.existsSync(f)) { console.error(`missing: ${f}`); process.exit(1); }
}

// Measured, not assumed — see the duration note in run-benchmark.mjs. Both models
// are probed at runtime anyway; these are only used for the pre-flight estimate.
const CLIP = { s2v: 4.81, i2v: 5.06 };
const PRICE = { s2v: 0.09, i2v: 0.05 };

const outDir = path.join(ROOT, "out", TAG);
const auth = () => ({ Authorization: `Bearer ${T}`, "Content-Type": "application/json" });
const sleep = (ms) => new Promise((s) => setTimeout(s, ms));
const ff = (args) => spawnSync("ffmpeg", ["-hide_banner", ...args], { encoding: "utf8" });

/** Where the vocal actually is. Drives shot routing.
 *  No -v error: silencedetect logs at INFO and -v error silently returns nothing. */
function vocalWindows(stem) {
  const out = ff(["-i", stem, "-af", "silencedetect=noise=-28dB:d=0.8", "-f", "null", "-"]).stderr || "";
  const starts = [...out.matchAll(/silence_start: (-?[\d.]+)/g)].map((m) => Number(m[1]));
  const ends = [...out.matchAll(/silence_end: ([\d.]+)/g)].map((m) => Number(m[1]));
  return starts.map((s, i) => [s, ends[i] ?? Infinity]).filter(([, e]) => Number.isFinite(e));
}
const inSilence = (t, gaps) => gaps.some(([s, e]) => t >= s && t < e);

/** Section starts from the Lyria map beside the song, if present. */
function sectionStarts(dir) {
  const mf = path.join(dir, "..", "manifest.json");
  if (!fs.existsSync(mf)) return [];
  const slug = path.basename(dir);
  const rec = JSON.parse(fs.readFileSync(mf, "utf8")).generated?.find((r) => r.slug === slug);
  return (rec?.sections ?? []).map((s) => s.start).filter((n) => Number.isFinite(n)).sort((a, b) => a - b);
}

const duration = Number(spawnSync("ffprobe", ["-v", "error", "-show_entries", "format=duration",
  "-of", "csv=p=0", MASTER], { encoding: "utf8" }).stdout.trim());
const target = Math.min(SECONDS, duration);
const gaps = vocalWindows(STEM);
const sections = sectionStarts(SONG_DIR);

// ── plan the shots ───────────────────────────────────────────────────────────
const shots = [];
let t = 0, i = 0;
while (t < target - 0.5) {
  const isReset = REANCHOR > 0 && i % REANCHOR === 0;
  // A reset seam is the visible one, so pull it to the nearest section boundary.
  if (isReset && sections.length && i > 0) {
    const near = sections.reduce((b, s) => Math.abs(s - t) < Math.abs(b - t) ? s : b, sections[0]);
    if (Math.abs(near - t) <= 2.5 && near < target - 1) t = near;
  }
  const kind = inSilence(t + 0.4, gaps) ? "i2v" : "s2v";
  shots.push({ i, at: Number(t.toFixed(2)), kind, reset: isReset,
               onSection: sections.some((s) => Math.abs(s - t) < 0.05) });
  t += CLIP[kind];
  i++;
}

const cost = shots.reduce((n, s) => n + PRICE[s.kind], 0);
const nS2V = shots.filter((s) => s.kind === "s2v").length;

console.log(`song       ${SONG_DIR}`);
console.log(`duration   ${duration.toFixed(1)}s, rendering ${target.toFixed(1)}s`);
console.log(`vocal gaps ${gaps.length} (${gaps.reduce((n, [s, e]) => n + (e - s), 0).toFixed(1)}s non-vocal)`);
console.log(`sections   ${sections.length}`);
console.log(`shots      ${shots.length}  —  ${nS2V} s2v (lip sync), ${shots.length - nS2V} i2v`);
console.log(`strategy   reanchor ${REANCHOR}, ${shots.filter((s) => s.onSection).length} seams on section boundaries`);
console.log(`lora       ${LORA_HI ? "yes" : "none (stock i2v)"}`);
console.log(`estimate   ~$${cost.toFixed(2)}`);
console.log(`out        ${outDir}\n`);

for (const s of shots.slice(0, DRY ? 99 : 0)) {
  console.log(`  ${String(s.i).padStart(2)}  t=${String(s.at).padStart(6)}s  ${s.kind}` +
              `${s.reset ? "  reset" : "  chain"}${s.onSection ? "  [section]" : ""}`);
}
if (DRY) { console.log("\ndry run — nothing sent, nothing spent."); process.exit(0); }
if (cost > MAX_COST) { console.error(`refusing: $${cost.toFixed(2)} exceeds --max-cost $${MAX_COST}`); process.exit(1); }

// ── generate ─────────────────────────────────────────────────────────────────
fs.mkdirSync(outDir, { recursive: true });
const version = async (m) =>
  (await (await fetch(`${API}/models/${m}`, { headers: auth() })).json()).latest_version.id;
const V = { s2v: await version("wan-video/wan-2.2-s2v"), i2v: await version("wan-video/wan-2.2-i2v-fast") };
const dataUri = (f, mime) => `data:${mime};base64,${fs.readFileSync(f).toString("base64")}`;

async function predict(v, input, tries = 8) {
  let j;
  for (let n = 0; n < tries; n++) {
    const r = await fetch(`${API}/predictions`, { method: "POST", headers: auth(),
      body: JSON.stringify({ version: v, input }) });
    if (r.ok) { j = await r.json(); break; }
    if (r.status !== 429) throw new Error(`HTTP ${r.status} — ${(await r.text()).slice(0, 160)}`);
    // Replicate throttles hard below $5 account credit — see the README.
    const wait = Number(r.headers.get("retry-after")) * 1000 || Math.min(60000, 4000 * 2 ** n);
    process.stdout.write(`429 ${Math.round(wait / 1000)}s… `);
    await sleep(wait);
  }
  if (!j) throw new Error("rate limited");
  while (!["succeeded", "failed", "canceled"].includes(j.status)) {
    await sleep(3000);
    const p = await fetch(`${API}/predictions/${j.id}`, { headers: auth() });
    if (p.status === 429) continue;
    j = await p.json();
  }
  if (j.status !== "succeeded") throw new Error(`${j.status}: ${j.error ?? "no detail"}`);
  return Array.isArray(j.output) ? j.output[0] : j.output;
}


/** Last decodable frame of a clip.
 *
 *  ⚠ DO NOT USE -sseof HERE. It works on i2v output and silently produces nothing
 *  on s2v output, exiting 0 either way. Cause: s2v writes 73 frames at 16fps
 *  (4.56s of picture) inside a 4.81s container, so seeking to duration-0.2 lands
 *  past the final frame — "Output file is empty, nothing was encoded". The first
 *  version of this pipeline crashed six shots later, when a path that was never
 *  written got handed to the next shot as its conditioning image.
 *
 *  Decoding straight through and letting -update overwrite is slower by a fraction
 *  of a second on a 5s clip and cannot fail this way. Returns null rather than
 *  throwing, so a bad tail degrades to a re-anchor instead of killing the render. */
function lastFrame(clip, dest) {
  ff(["-v", "error", "-i", clip, "-update", "1", "-q:v", "2", "-y", dest]);
  return fs.existsSync(dest) && fs.statSync(dest).size > 0 ? dest : null;
}

const origStill = STILL;
let conditioning = origStill;
const made = [];

for (const s of shots) {
  process.stdout.write(`${String(s.i).padStart(2)}  ${s.kind}  t=${String(s.at).padStart(6)}s  `);
  const clipPath = path.join(outDir, `s${String(s.i).padStart(2, "0")}.mp4`);
  let input;

  if (s.kind === "s2v") {
    // ⚠ THE STEM, NOT THE MASTER. VID-SING-010 vs 013.
    const seg = path.join(outDir, `a${String(s.i).padStart(2, "0")}.wav`);
    ff(["-v", "error", "-ss", String(s.at), "-t", String(CLIP.s2v), "-i", STEM,
        "-ar", "16000", "-ac", "1", "-y", seg]);
    input = { prompt: "A young Indian woman singing, realistic video.",
              image: dataUri(conditioning, "image/png"), audio: dataUri(seg, "audio/wav"), seed: 1000 + s.i };
  } else {
    input = { prompt: "A young Indian woman in a modern Indian setting, natural movement, realistic video.",
              image: dataUri(conditioning, "image/png"), seed: 1000 + s.i,
              resolution: "480p", interpolate_output: false };
    if (LORA_HI) { input.lora_weights_transformer = LORA_HI; input.lora_scale_transformer = 1; }
    if (LORA_LO) { input.lora_weights_transformer_2 = LORA_LO; input.lora_scale_transformer_2 = 1; }
  }

  try {
    const url = await predict(V[s.kind], input);
    fs.writeFileSync(clipPath, Buffer.from(await (await fetch(url)).arrayBuffer()));
    const last = lastFrame(clipPath, path.join(outDir, `s${String(s.i).padStart(2, "0")}-last.png`));
    made.push({ ...s, file: path.basename(clipPath) });
    console.log(last ? "ok" : "ok (no last frame — next shot re-anchors)");
    // If the tail frame could not be read, fall back to the still rather than
    // handing the next shot a path that does not exist.
    conditioning = s.reset || !last ? origStill : last;
  } catch (e) {
    console.log(`FAIL ${String(e.message).slice(0, 80)}`);
    conditioning = origStill;
  }
}

if (!made.length) { console.error("nothing generated"); process.exit(1); }

// ── stitch, then mux the MASTER over the top ─────────────────────────────────
const list = path.join(outDir, "concat.txt");
fs.writeFileSync(list, made.map((m) => `file '${path.join(outDir, m.file)}'`).join("\n"));
const silentCut = path.join(outDir, "cut.mp4");
execFileSync("ffmpeg", ["-v", "error", "-f", "concat", "-safe", "0", "-i", list,
                        "-c", "copy", "-y", silentCut]);
const final = path.join(outDir, "beenga-music-video.mp4");
execFileSync("ffmpeg", ["-v", "error", "-i", silentCut, "-i", MASTER,
                        "-map", "0:v", "-map", "1:a", "-shortest",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-y", final]);

fs.writeFileSync(path.join(outDir, "plan.json"), JSON.stringify(
  { song: SONG_DIR, still: STILL, reanchor: REANCHOR, lora: { high: LORA_HI || null, low: LORA_LO || null },
    sections, gaps, shots: made }, null, 2));

const dur = spawnSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", final],
                      { encoding: "utf8" }).stdout.trim();
console.log(`\n${made.length}/${shots.length} shots  →  ${final}`);
console.log(`final duration ${Number(dur).toFixed(1)}s`);
