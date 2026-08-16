// Generate the reference still that the i2v and s2v cases need as their subject.
//
//   node scripts/make-still.mjs
//   node scripts/make-still.mjs --seed 77 --out stills/singer-b.png
//
// WHY A STILL EXISTS AT ALL. Wan 2.2 S2V takes image + audio and animates THAT
// person. So the still is not decoration — it fixes the singer's identity for
// every singing case, and it is the thing cross-clip identity is measured
// against. One still, reused across all the singing cases, is also what makes
// VID-ID-006 meaningful: three clips from one still should be one person.
//
// The prompt is written for the framing S2V wants — face-on, medium close-up,
// mouth already mid-phrase. A profile or a wide shot gives the audio-driven
// model less to work with and confounds the lip-sync measurement with pose.
//
// Deliberately generated on an image model rather than pulled from stock: a
// licensed photograph of a real person, animated to sing words they never sang,
// is a different thing to publish than a synthetic face, and the benchmark does
// not need a real person to answer the question it is asking.
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

/** Load .env from the repo root if the token is not already exported.
 *
 *  Without this the scripts require `set -a; . .env; set +a` before every run,
 *  which is invisible friction and the reason "it's one command" was not true.
 *  Same pattern as beenga-in/lib/replicate.mjs: resolve from the MODULE url, not
 *  cwd, so it works no matter where it is invoked from. */
function loadEnv() {
  const p = path.join(ROOT, ".env");
  if (!fs.existsSync(p)) return;
  for (const line of fs.readFileSync(p, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/i);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}
loadEnv();

const API = "https://api.replicate.com/v1";
const T = process.env.REPLICATE_API_TOKEN;
if (!T) { console.error("REPLICATE_API_TOKEN not set"); process.exit(1); }

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i === -1 ? d : argv[i + 1]; };
const MODEL = arg("--model", "black-forest-labs/flux-2-klein-4b");
const SEED = Number(arg("--seed", "4242"));
const OUT = arg("--out", "stills/singer.png");

// Complexion is stated explicitly and more than once. beenga-image measured that a
// single mention of a deep tone renders lighter than asked, and that stacking
// descriptions of the same tone fixes it. Whether that carries to this model is
// not the question here — but the still is the identity every singing case
// inherits, so it is the wrong place to leave the tone to chance.
const PROMPT =
  "A 26-year-old Indian woman singing into a microphone, medium close-up, facing "
  + "the camera straight on, mouth slightly open mid-phrase, natural expression. "
  + "Deep brown skin, richly pigmented complexion, warm deep brown skin tone across "
  + "the whole face. Long dark hair, contemporary casual clothing, modern recording "
  + "studio softly out of focus behind her. Realistic photography, sharp facial "
  + "detail, even lighting on the face.";

const auth = () => ({ Authorization: `Bearer ${T}`, "Content-Type": "application/json" });

const meta = await (await fetch(`${API}/models/${MODEL}`, { headers: auth() })).json();
const version = meta.latest_version?.id;
if (!version) { console.error(`${MODEL}: no latest_version`); process.exit(1); }

let r = await fetch(`${API}/predictions`, {
  method: "POST", headers: auth(),
  body: JSON.stringify({ version, input: {
    prompt: PROMPT, seed: SEED, aspect_ratio: "16:9",
    output_format: "png", output_megapixels: "1",
  } }),
});
if (!r.ok) { console.error(`HTTP ${r.status} — ${(await r.text()).slice(0, 200)}`); process.exit(1); }

let j = await r.json();
while (!["succeeded", "failed", "canceled"].includes(j.status)) {
  await new Promise((s) => setTimeout(s, 1200));
  j = await (await fetch(`${API}/predictions/${j.id}`, { headers: auth() })).json();
}
if (j.status !== "succeeded") { console.error(`${j.status}: ${j.error ?? "no detail"}`); process.exit(1); }

const url = Array.isArray(j.output) ? j.output[0] : j.output;
const buf = Buffer.from(await (await fetch(url)).arrayBuffer());
const dest = path.join(ROOT, OUT);
fs.mkdirSync(path.dirname(dest), { recursive: true });
fs.writeFileSync(dest, buf);

console.log(`${OUT}  ${(buf.length / 1024).toFixed(0)}KB  seed ${SEED}  ${j.metrics?.predict_time?.toFixed(1)}s`);
