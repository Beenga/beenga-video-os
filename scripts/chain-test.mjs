// Can we actually make a three-minute video, or only 36 clips glued together?
//
//   node scripts/chain-test.mjs --mode chain  --clips 6 --tag chain6
//   node scripts/chain-test.mjs --mode anchor --clips 6 --tag anchor6
//
// Cross-clip identity is already cleared: three independent clips from one still
// scored mean CSIM 0.796 against ~0.6 for same-person. So a stitched song will
// look like the same singer. What that result does NOT show is whether the clips
// JOIN — whether the last frame of clip N flows into the first frame of clip N+1,
// or whether every seam reads as a hard cut. That is the difference between a
// three-minute video and a slideshow of five-second videos.
//
// TWO STRATEGIES, and they trade the same two properties against each other:
//
//   anchor  Every clip is generated from the SAME reference still. Identity is
//           pinned to one image and cannot wander. But every clip also STARTS
//           from that image's pose, so each seam is a jump back to the beginning.
//
//   chain   Clip N+1 is generated from the LAST FRAME of clip N. The seam is
//           continuous by construction — the first frame of the next clip is
//           literally the conditioning image. But nothing pins identity to the
//           original any more, so error compounds: each clip inherits the drift
//           of every clip before it, which is how a singer slowly becomes a
//           different person over three minutes.
//
// This script runs both and leaves the measurement to scripts/score-chain.py.
// It does not decide which is better, because that is an empirical question and
// the failure modes are not comparable by argument.
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const API = "https://api.replicate.com/v1";
const T = process.env.REPLICATE_API_TOKEN;
if (!T) { console.error("REPLICATE_API_TOKEN not set"); process.exit(1); }

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i === -1 ? d : argv[i + 1]; };
const MODE   = arg("--mode", "chain");            // chain | anchor
const CLIPS  = Number(arg("--clips", "6"));
const TAG    = arg("--tag", `${MODE}${arg("--clips", "6")}`);
const MODEL  = arg("--model", "wan-video/wan-2.2-i2v-fast");
const STILL  = arg("--still", "stills/singer.png");
const SEED   = Number(arg("--seed", "1234"));
const DRY    = argv.includes("--dry-run");

// One prompt for every clip. Varying it per clip would be better film-making and
// worse measurement — the question is whether the JOIN holds, so the prompt is
// held constant and the conditioning image is the only thing that changes.
const PROMPT = arg("--prompt",
  "A young Indian woman singing into a microphone in a recording studio, "
  + "natural head movement, realistic video.");

if (!["chain", "anchor"].includes(MODE)) { console.error("--mode must be chain or anchor"); process.exit(1); }

const outDir = path.join(ROOT, "out", TAG);
const auth = () => ({ Authorization: `Bearer ${T}`, "Content-Type": "application/json" });
const dataUri = (p) => `data:image/png;base64,${fs.readFileSync(p).toString("base64")}`;

async function version(model) {
  const r = await fetch(`${API}/models/${model}`, { headers: auth() });
  if (!r.ok) throw new Error(`${model}: HTTP ${r.status}`);
  return (await r.json()).latest_version.id;
}

const sleep = (ms) => new Promise((s) => setTimeout(s, ms));

async function generate(v, input, tries = 7) {
  let j;
  for (let n = 0; n < tries; n++) {
    const r = await fetch(`${API}/predictions`, {
      method: "POST", headers: auth(), body: JSON.stringify({ version: v, input }),
    });
    if (r.ok) { j = await r.json(); break; }
    if (r.status !== 429) throw new Error(`HTTP ${r.status} — ${(await r.text()).slice(0, 160)}`);
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
  return { url: Array.isArray(j.output) ? j.output[0] : j.output, predict: j.metrics?.predict_time ?? null };
}

/** Last decodable frame of a clip, written as PNG. This becomes the next
 *  conditioning image in chain mode — and is also what the join is measured on. */
function lastFrame(clip, dest) {
  // ⚠ NOT -sseof. It works on i2v output and silently writes nothing on s2v output
  // (73 frames of picture inside a 4.81s container, so the seek lands past the last
  // frame and ffmpeg still exits 0). This script only ever ran on i2v, so the bug
  // stayed hidden here until make-music-video.mjs hit it on shot 8. Decode through.
  execFileSync("ffmpeg", ["-v", "error", "-i", clip, "-update", "1", "-q:v", "2", "-y", dest]);
  return dest;
}

function firstFrame(clip, dest) {
  execFileSync("ffmpeg", ["-v", "error", "-i", clip, "-vf", "select=eq(n\\,0)",
                          "-frames:v", "1", "-y", dest]);
  return dest;
}

console.log(`mode    ${MODE}`);
console.log(`clips   ${CLIPS}  (~${(CLIPS * 5).toFixed(0)}s of video)`);
console.log(`model   ${MODEL}`);
console.log(`still   ${STILL}`);
console.log(`cost    ~$${(CLIPS * 0.05).toFixed(2)}`);
console.log(`out     ${outDir}\n`);

if (DRY) { console.log("dry run — nothing sent, nothing spent."); process.exit(0); }

fs.mkdirSync(outDir, { recursive: true });
const v = await version(MODEL);

const origStill = path.join(ROOT, STILL);
let conditioning = origStill;
const record = { mode: MODE, model: MODEL, version: v, still: STILL, prompt: PROMPT, seed: SEED, clips: [] };

for (let i = 0; i < CLIPS; i++) {
  process.stdout.write(`clip ${String(i).padStart(2)}  from ${path.basename(conditioning).padEnd(22)} `);
  const input = {
    prompt: PROMPT,
    image: dataUri(conditioning),
    // Each clip gets its own seed. Reusing one seed with a changing conditioning
    // image would confound "the chain drifted" with "the seed repeated a motion".
    seed: SEED + i,
    resolution: "480p",
    interpolate_output: false,
  };
  const g = await generate(v, input);
  const clipPath = path.join(outDir, `c${String(i).padStart(2, "0")}.mp4`);
  fs.writeFileSync(clipPath, Buffer.from(await (await fetch(g.url)).arrayBuffer()));

  const first = firstFrame(clipPath, path.join(outDir, `c${String(i).padStart(2, "0")}-first.png`));
  const last = lastFrame(clipPath, path.join(outDir, `c${String(i).padStart(2, "0")}-last.png`));
  record.clips.push({ i, file: path.basename(clipPath), conditioning: path.basename(conditioning),
                      first: path.basename(first), last: path.basename(last), predict: g.predict });
  console.log(`ok ${g.predict?.toFixed(1)}s`);

  // --reanchor K resets to the original still every K clips: chain for continuity,
  // reset to cap drift. Pure chain crossed the same-person threshold by clip 3, so
  // K must be small. K=0 means never reset, i.e. pure chain.
  const REANCHOR = Number(arg("--reanchor", "0"));
  const dueReset = REANCHOR > 0 && ((i + 1) % REANCHOR === 0);
  conditioning = MODE === "anchor" || dueReset ? origStill : last;
}

// Stitch, so the joins can be watched rather than only measured.
const list = path.join(outDir, "concat.txt");
fs.writeFileSync(list, record.clips.map((c) => `file '${path.join(outDir, c.file)}'`).join("\n"));
execFileSync("ffmpeg", ["-v", "error", "-f", "concat", "-safe", "0", "-i", list,
                        "-c", "copy", "-y", path.join(outDir, "stitched.mp4")]);

fs.writeFileSync(path.join(outDir, "chain.json"), JSON.stringify(record, null, 2));
console.log(`\nstitched → ${path.join(outDir, "stitched.mp4")}`);
console.log(`score it → ./.venv/bin/python scripts/score-chain.py out/${TAG}`);
