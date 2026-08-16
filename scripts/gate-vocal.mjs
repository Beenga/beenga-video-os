// Gate a separated vocal stem so its non-vocal regions are TRUE digital silence.
//
//   node scripts/gate-vocal.mjs in.mp3 out.wav [--threshold -40] [--report]
//
// WHY THIS EXISTS. Arm C (Wan 2.2 S2V) drives mouth movement from audio ENERGY,
// not from vocal content — measured: an instrumental passage produces 95% of the
// articulation that singing does (VID-SING-010). Feed it a song master and the
// singer mouths through the intro, the break and the outro.
//
// But the same measurement showed that TRUE silence largely stops the mouth
// (VID-SING-009, x0.30 of the vocal rate). So the fix is not to segment the song
// and orchestrate two pipelines — it is to feed S2V a vocal stem whose gaps are
// actually zero.
//
// A separated stem is quiet in its gaps but not silent: Demucs leaves roughly
// -62dB of residual there, and S2V responds to it. This closes that gap.
//
// ⚠ agate's `range` DEFAULTS TO 0.06, which caps attenuation at about -24dB — so
// a gate left on defaults reduces the bleed and never removes it, which is the
// one thing this script exists to do. range=0 is mandatory, not a preference.
//
// ⚠ AND A MEASUREMENT WARNING, learned by getting it wrong: ffmpeg's silencedetect
// and volumedetect log at INFO level. Running them under `-v error` suppresses the
// output, and a parser then reports zero silences for every input — which reads as
// a confident measurement and is nothing of the kind. Never pass -v error to a
// filter you intend to read.
import { execFileSync, spawnSync } from "node:child_process";
import path from "node:path";

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i === -1 ? d : argv[i + 1]; };
const [input, output] = argv.filter((a) => !a.startsWith("--") && !/^-?\d+$/.test(a));
if (!input || !output) {
  console.error("usage: node scripts/gate-vocal.mjs <in> <out.wav> [--threshold -40] [--report]");
  process.exit(1);
}

const THRESHOLD_DB = Number(arg("--threshold", "-28"));
const REPORT = argv.includes("--report");

// agate takes a LINEAR amplitude threshold, not dB.
const linear = Math.pow(10, THRESHOLD_DB / 20);

const FILTER = [
  `agate=threshold=${linear.toFixed(6)}:ratio=9000:range=0:attack=10:release=300`,
].join(",");

/** Read silencedetect for a file.
 *
 *  ⚠ ffmpeg writes its filter logging to STDERR, and execFileSync returns STDOUT.
 *  The first version parsed the return value and crashed on null — which is the
 *  lucky failure. The unlucky one is parsing an empty string and reporting zero
 *  silences for every file, which is exactly the bug that -v error caused earlier
 *  in this same script. Two different routes to the same false measurement. */
function silences(file, noiseDb = -50, minDur = 0.4) {
  const r = spawnSync("ffmpeg", ["-hide_banner", "-i", file, "-af",
    `silencedetect=noise=${noiseDb}dB:d=${minDur}`, "-f", "null", "-"], { encoding: "utf8" });
  const out = r.stderr || "";
  const starts = [...out.matchAll(/silence_start: (-?[\d.]+)/g)].map((m) => Number(m[1]));
  const ends = [...out.matchAll(/silence_end: ([\d.]+)/g)].map((m) => Number(m[1]));
  return starts.map((s, i) => [s, ends[i] ?? null]).filter(([, e]) => e !== null);
}

execFileSync("ffmpeg", ["-v", "error", "-i", input, "-af", FILTER,
                        "-ar", "16000", "-ac", "1", "-y", output]);

console.log(`gated  ${path.basename(input)} → ${path.basename(output)}  (threshold ${THRESHOLD_DB}dB)`);

if (REPORT) {
  const before = silences(input);
  const after = silences(output);
  const total = (runs) => runs.reduce((n, [s, e]) => n + (e - s), 0);
  console.log(`  silent below -50dB, before: ${before.length} runs, ${total(before).toFixed(1)}s`);
  console.log(`  silent below -50dB, after : ${after.length} runs, ${total(after).toFixed(1)}s`);
  if (after.length) {
    console.log(`  gaps now zeroed: ${after.slice(0, 6).map(([s, e]) => `${s.toFixed(1)}-${e.toFixed(1)}`).join(", ")}`);
  }
}
