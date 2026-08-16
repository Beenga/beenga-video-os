// Beenga video prompt layer — wave 0.
//
// THIS FILE IS DELIBERATELY EMPTY OF RULES. That is the point, and it should stay
// that way until wave 0 has run.
//
// In beenga-image, every rule in lib/prompt.mjs exists because a specific benchmark
// case failed, and the file says so case by case. The rules that ended up there are
// not general truths about image models — they are facts about how FLUX.2 Klein
// behaved on 29 measured prompts. Two of them were added only after an earlier,
// confident conclusion turned out to be wrong.
//
// So none of them are ported here on faith:
//
//   * NEGATION REWRITING. "FLUX cannot negate" is a fact about FLUX's text encoder.
//     Wan 2.2 uses umt5-xxl, a different encoder entirely. Whether it handles "no
//     moustache" is an empirical question this suite will answer. VID-ID-005 is the
//     probe.
//
//   * CONTEMPORARY DEFAULT. Klein's prior for "India" was ceremonial. Wan was
//     trained on a different corpus and may not share it. VID-DEF-001 and
//     VID-DEF-002 reuse the exact prompts that failed on the image side, precisely
//     so the two suites can be compared. If Wan passes them, this rule never gets
//     written and we saved the work.
//
//   * ATTRIBUTE STACKING. Restating an attribute five times fixed clean-shaven and
//     complexion on stills. Video adds a time axis that stacking may not reach at
//     all: an attribute can be correct in frame 1 and wrong by frame 120, and no
//     amount of describing it more loudly in a prompt obviously fixes drift.
//
// Writing rules before measuring is exactly the mistake beenga-image documents
// itself avoiding — the original spec there proposed ~69 concept buckets, and
// measuring first reduced it to two defects, then one.
//
// The machinery below is complete and tested. Wave 1 should be a data edit to the
// three arrays, not a rewrite of enhance().

// ── 1. Negations ─────────────────────────────────────────────────────────────
// Populate only if VID-ID-005 (or another case) shows Wan renders a negated
// attribute anyway. Ordered longest-first when populated, so "no facial hair"
// matches before "no hair" could. Replacements must never contain wording that a
// later rule matches — that bug produced "bare clean eyelids with bare clean
// eyelids of any kind" on the image side.
const NEGATIONS = [];

// ── 2. Scene defaults ────────────────────────────────────────────────────────
//
// EARNED 2026-08-15, wave 0, three seeds on wan-2.2-5b-fast.
//
// VID-DEF-001 ("a young Indian woman standing on a rooftop in Delhi") and
// VID-DEF-002 ("a portrait video of an Indian woman") returned a ceremonial silk
// sari with gold jewellery on 3 of 3 seeds each. 5B's prior for an unqualified
// Indian person is ceremonial — the same defect beenga-image measured on FLUX.2
// Klein, in a different modality, on a different model family.
//
// So this rule is ported from beenga-image/lib/prompt.mjs rather than invented,
// and the strings are close to identical. That is deliberate: the defect matched,
// so the fix should be the one already proven against it.
//
// ⚠ WHAT IS *NOT* PORTED, and why. beenga-image also carries negation rewriting
// ("FLUX cannot negate") and a per-tone complexion stack. Neither is here. Wan
// uses umt5-xxl, a different text encoder, and no video case has yet failed on a
// negation or on complexion — the complexion instrument was not even trustworthy
// until this run. Porting them now would be importing conclusions instead of
// evidence, which is the mistake this project exists to avoid.
//
// ⚠ SCOPE, measured rather than assumed. VID-DEF-004 ("a busy street in Mumbai")
// already renders ordinary contemporary clothing on 5B without help — the
// ceremonial pull is on PERSON-focused prompts, not on scenes. The rule is still
// written to fire on both, because a scene that is already correct is not harmed
// by being told it is present-day, and narrowing it would need evidence we do not
// have.
const INDIA = /\b(indian?|delhi|mumbai|bombay|bengaluru|bangalore|chennai|kolkata|hyderabad|pune|jaipur|ahmedabad|kochi|lucknow)\b/i;

// The guard. VID-DEF-005 asks explicitly for a traditional red bridal lehenga at a
// wedding and passed 3/3 on both bases. A contemporary default that strips it
// would turn a passing case into a failing one, so intent always wins.
const TRADITIONAL_INTENT = new RegExp(
  "\\b(traditional|classical|bharatanatyam|kathak|kuchipudi|odissi|bhangra|garba|" +
  "temple|ritual|ceremon|wedding|bridal|festival|puja|pooja|diwali|navratri|" +
  "historical|period|ancient|mytholog|village|rural|folk)\\w*\\b", "i");

// Only nudge toward modern dress when no garment is named at all — otherwise the
// rule argues with a request the user made explicitly.
const GARMENT = /\b(sari|saree|lehenga|salwar|kurti|kurta|dupatta|sherwani|dhoti|blouse|dress|shirt|t-?shirt|jeans|suit|top|gown|uniform)\b/i;

const TRADITIONAL_OR_GARMENT = new RegExp(
  `(${TRADITIONAL_INTENT.source})|(${GARMENT.source})`, "i");

const DEFAULTS = [
  { name: "contemporary",
    test: INDIA,
    unless: TRADITIONAL_INTENT,
    say: "Present-day contemporary India, modern well-maintained surroundings, clean and "
       + "tidy environment, current-day styling." },
  { name: "modern-dress",
    test: INDIA,
    unless: TRADITIONAL_OR_GARMENT,
    say: "Modern everyday clothing." },
];

// ── 3. Fragile attributes ────────────────────────────────────────────────────
// Populate only for attributes measured to survive alone and fail under load.
//
// Two rules any entry must follow, both learned by breaking them in beenga-image:
//
//   * NO NEGATIONS, and never name the unwanted thing. "definitely not tight
//     ringlets" contributed "ringlets" as a positive token and made the failure
//     worse.
//   * DO NOT REPEAT BODY-PART NOUNS. Extra mentions of arms/hands/legs raise the
//     odds of extra limbs. Describe the garment, not the body it exposes. This
//     matters more in video, not less — VID-MOT-004 exists to catch it.
const FRAGILE = [];

/**
 * Apply the Beenga video prompt layer.
 *
 * Returns the prompt unchanged while the rule arrays are empty, so --enhance is
 * safe to wire up now and becomes meaningful the moment wave 0 produces evidence.
 *
 * @param {string} raw            the user's prompt, untouched
 * @param {object} [opts]
 * @param {boolean} [opts.defaults=true]   apply measured scene defaults
 * @param {boolean} [opts.reinforce=true]  restate measured fragile attributes
 * @returns {{prompt: string, applied: string[]}}
 */
export function enhance(raw, { defaults = true, reinforce = true } = {}) {
  const applied = [];
  let out = raw;

  for (const [re, positive] of NEGATIONS) {
    if (re.test(out)) {
      out = out.replace(re, positive);
      applied.push(`negation:${re.source.slice(0, 28)}`);
    }
  }

  const tail = [];

  // A rule's `test`/`unless` may be a RegExp or a predicate. Same convention as
  // FRAGILE below — the first draft assumed a function and threw on every regex.
  const fires = (t, s) => (t === undefined ? false : typeof t === "function" ? t(s) : t.test(s));

  if (defaults) {
    for (const rule of DEFAULTS) {
      if (fires(rule.test, raw) && !fires(rule.unless, raw)) {
        tail.push(rule.say);
        applied.push(`default:${rule.name}`);
      }
    }
  }

  if (reinforce) {
    // A rule's `test` is either a RegExp or a predicate over the raw prompt.
    const hit = (f) => (typeof f.test === "function" ? f.test(raw) : f.test.test(raw));
    const recap = FRAGILE.filter(hit).map((f) => f.say);
    if (recap.length) {
      tail.push(...recap);
      applied.push(`reinforce:${recap.length}`);
    }
  }

  if (tail.length) out = `${out.trim().replace(/\.?$/, ".")} ${tail.join(" ")}`;
  return { prompt: out, applied };
}

/** True while no rule has been earned yet. The runner reports this so a "wave 1" run that
 *  silently did nothing cannot be mistaken for a wave 1 result. */
export const isEmpty = () => NEGATIONS.length + DEFAULTS.length + FRAGILE.length === 0;
