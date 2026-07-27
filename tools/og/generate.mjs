/**
 * Per-platform social creative generator for Lexitrail (lexitrail#63, AC3).
 *
 * Replaces the single byte-identical 1200x630 app screenshot that was serving
 * as the creative on every channel. Two separate problems were bundled in that
 * one file:
 *
 *   1. Aspect. 1.905:1 is CORRECT for a link-preview card (og:image) and wrong
 *      for all three feed platforms we post to, in the expensive direction —
 *      landscape letterboxes inside vertical feeds. So the fix is not "stop
 *      using landscape", it is one asset per surface, landscape included.
 *   2. Provenance. It was a capture of a live practice session, so it carried
 *      a demo-account email, "recalled 0 out of 149", zeroed counters, a running
 *      timer and app chrome. The dominant message of our whole organic surface
 *      was a user who had learned none of the deck, 17 seconds in.
 *
 * AC3 asks for a generator rather than a human re-cropping one file, which is
 * what this is: copy comes from copy.json, sample vocabulary comes from the
 * repo's own HSK CSV, and every platform size is one entry in PRESETS.
 *
 * Usage:
 *   npm install          # once, in this directory
 *   npm run generate     # writes ui/public/images/og/generated/
 *   npm run generate -- --preset ig-portrait   # just one
 *
 * If playwright's bundled chromium is not the build installed in this
 * environment, set PLAYWRIGHT_CHROMIUM_EXECUTABLE to the browser binary. That
 * mismatch is not a missing browser and the error message says so, because
 * misreading it as one cost days of wrongly believing this box had no browser.
 */
import { chromium } from "playwright";
import { readFileSync, mkdirSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { assertClean } from "./forbidden.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..", "..");
const OUT_DIR = join(REPO, "ui", "public", "images", "og", "generated");
const TEMPLATE = join(HERE, "template.html");

/**
 * One entry per surface we actually publish to.
 *
 * `layout` picks the template's arrangement: `split` puts the pitch beside the
 * sample (only readable in landscape), `stack` puts it above (everything else).
 * `cards` is tuned per canvas so the grid never crushes the glyphs — the
 * character is the one element that must stay legible at feed thumbnail size.
 */
export const PRESETS = [
  {
    name: "og-landscape",
    width: 1200, height: 630, layout: "split", cards: 4,
    use: "og:image / twitter:summary_large_image — link previews (Slack, iMessage, FB, X)",
  },
  {
    name: "ig-square",
    width: 1080, height: 1080, layout: "stack", cards: 4,
    use: "Instagram feed 1:1",
  },
  {
    name: "ig-portrait",
    width: 1080, height: 1350, layout: "stack", cards: 6,
    use: "Instagram feed 4:5 — the largest slice of feed real estate IG allows",
  },
  {
    name: "pinterest",
    width: 1000, height: 1500, layout: "stack", cards: 6,
    use: "Pinterest 2:3 — the ratio Pinterest documents as standard",
  },
  {
    name: "tiktok",
    width: 1080, height: 1920, layout: "stack", cards: 6,
    use: "TikTok / Reels / Stories 9:16 full-bleed",
  },
];

/** Parse the repo's HSK CSV. Columns: No,Chinese,Pinyin,English. */
function readHskWords(level) {
  const path = join(REPO, "terraform", "csv", `HSK${level}.csv`);
  const rows = readFileSync(path, "utf8").trim().split("\n").slice(1);
  return rows
    .map((line) => {
      // Simple split is safe here: the glosses in these files contain no commas
      // beyond the field separators, and we validate the shape below.
      const parts = line.split(",");
      if (parts.length < 4) return null;
      const [, hanzi, pinyin, ...rest] = parts;
      const gloss = rest.join(",").trim();
      if (!hanzi?.trim() || !pinyin?.trim() || !gloss) return null;
      return { hanzi: hanzi.trim(), pinyin: pinyin.trim(), gloss };
    })
    .filter(Boolean);
}

/**
 * Pick sample words deterministically.
 *
 * Deterministic on purpose: a random pick would make every regeneration a
 * different asset, so the committed PNGs would churn and a reviewer could not
 * tell a copy change from a reshuffle. Spread across the list rather than
 * taking the first N, which are the most trivial entries in an HSK deck.
 */
function pickWords(words, n) {
  const picked = [];
  const stride = Math.max(1, Math.floor(words.length / n));
  for (let i = 0; picked.length < n && i < words.length; i += stride) {
    const w = words[i];
    // Single-character entries render best in a small card; a 4-character
    // idiom at 9.6vmin overflows it.
    if ([...w.hanzi].length <= 2) picked.push(w);
  }
  // Fall back to filling from the front if the stride pass came up short.
  for (let i = 0; picked.length < n && i < words.length; i++) {
    if (!picked.includes(words[i]) && [...words[i].hanzi].length <= 2) picked.push(words[i]);
  }
  return picked.slice(0, n);
}

async function main() {
  const argv = process.argv.slice(2);
  const onlyIdx = argv.indexOf("--preset");
  const only = onlyIdx >= 0 ? argv[onlyIdx + 1] : null;

  const copy = JSON.parse(readFileSync(join(HERE, "copy.json"), "utf8"));
  const words = readHskWords(2);
  if (words.length < 6) {
    throw new Error(`Expected HSK2 vocabulary, parsed only ${words.length} rows`);
  }

  const presets = only ? PRESETS.filter((p) => p.name === only) : PRESETS;
  if (!presets.length) {
    throw new Error(`Unknown preset ${only}. Known: ${PRESETS.map((p) => p.name).join(", ")}`);
  }

  // AC2 gate, before we render anything. Checks resolved text — the copy plus
  // every card that will appear in any preset.
  const maxCards = Math.max(...presets.map((p) => p.cards));
  const sampleForCheck = pickWords(words, maxCards);
  assertClean([
    copy.badge, copy.wordmark, copy.headline, copy.mechanism, copy.coverage,
    ...sampleForCheck.flatMap((w) => [w.hanzi, w.pinyin, w.gloss]),
  ]);

  mkdirSync(OUT_DIR, { recursive: true });

  const launchOpts = {};
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE) {
    launchOpts.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  }

  let browser;
  try {
    browser = await chromium.launch(launchOpts);
  } catch (err) {
    throw new Error(
      `Could not launch chromium. If this says the browser build is missing, it ` +
        `is a VERSION MISMATCH between playwright and the installed chromium, ` +
        `not an absent browser — point PLAYWRIGHT_CHROMIUM_EXECUTABLE at the ` +
        `binary you have.\nOriginal: ${err.message}`,
    );
  }

  const written = [];
  try {
    for (const preset of presets) {
      const page = await browser.newPage({
        viewport: { width: preset.width, height: preset.height },
        deviceScaleFactor: 1,
      });
      await page.goto(`file://${TEMPLATE}`);

      const cards = pickWords(words, preset.cards);
      await page.evaluate(
        ({ copy, cards, layout }) => {
          document.documentElement.dataset.layout = layout;
          document.getElementById("badge").textContent = copy.badge;
          document.getElementById("wordmark").textContent = copy.wordmark;
          document.getElementById("headline").textContent = copy.headline;
          document.getElementById("mechanism").textContent = copy.mechanism;
          document.getElementById("coverage").textContent = copy.coverage;

          const sample = document.getElementById("sample");
          sample.innerHTML = "";
          for (const w of cards) {
            const el = document.createElement("div");
            el.className = "card";
            const h = document.createElement("div");
            h.className = "hanzi";
            h.textContent = w.hanzi;
            const p = document.createElement("div");
            p.className = "pinyin";
            p.textContent = w.pinyin;
            const g = document.createElement("div");
            g.className = "gloss";
            g.textContent = w.gloss;
            el.append(h, p, g);
            sample.append(el);
          }
        },
        { copy, cards, layout: preset.layout },
      );

      // Fonts must be resolved before the shot or CJK glyphs can capture as
      // fallback boxes — a failure that looks like a design choice in review.
      await page.evaluate(() => document.fonts.ready);

      // Shrink-to-fit. Hand-tuning vmin values until five aspect ratios all
      // happen to fit is not a generator, it is a human re-cropping one file
      // with extra steps — and it silently re-breaks the moment the copy or the
      // card count changes. So the generator finds its own scale: shrink the
      // card type until nothing clips, and fail loudly if even the floor is not
      // enough (which means the design genuinely cannot hold that much content
      // at that aspect, and a human should decide what to drop).
      const fit = await page.evaluate(() => {
        const clipped = () =>
          [...document.querySelectorAll(".card")].some((c) => c.scrollHeight > c.clientHeight + 1);
        let f = 1;
        while (clipped() && f > 0.6) {
          f = Math.round((f - 0.02) * 100) / 100;
          document.documentElement.style.setProperty("--fit", String(f));
          document.body.getBoundingClientRect(); // force reflow before re-measuring
        }
        return f;
      });

      // Overflow gate. One layout serving five aspect ratios WILL clip
      // something eventually, and a clipped asset looks deliberate in review —
      // the first render of ig-portrait cut the bottom card row off at the
      // canvas edge and the text gate above was perfectly happy. So this is
      // mechanical rather than a habit of remembering to look.
      const overflow = await page.evaluate(() => {
        const doc = document.documentElement;
        const bad = [];

        // (a) Boxes escaping the CANVAS — content sliced by the screenshot edge.
        for (const el of document.querySelectorAll(".card, .pitch, .badge")) {
          const r = el.getBoundingClientRect();
          if (r.bottom > window.innerHeight + 0.5 || r.right > window.innerWidth + 0.5 ||
              r.top < -0.5 || r.left < -0.5) {
            bad.push(`canvas-overflow: ${el.className} {top:${Math.round(r.top)} ` +
                     `bottom:${Math.round(r.bottom)} right:${Math.round(r.right)}}`);
          }
        }

        // (b) Content escaping its OWN CARD. This is the case (a) cannot see, and
        // it is the more dangerous one: `.card` sets overflow:hidden, so a card
        // too short for its glyph silently slices the gloss off and the document
        // never reports a scroll overflow at all. Adding that overflow:hidden to
        // satisfy check (a) is what created this blind spot in the first place —
        // the suppression of a symptom read as a fix.
        for (const card of document.querySelectorAll(".card")) {
          const cr = card.getBoundingClientRect();
          if (card.scrollHeight > card.clientHeight + 1) {
            bad.push(`card-clipped: content ${card.scrollHeight}px in ${card.clientHeight}px box ` +
                     `("${card.querySelector(".hanzi")?.textContent ?? "?"}")`);
            continue;
          }
          for (const child of card.children) {
            const r = child.getBoundingClientRect();
            if (r.top < cr.top - 0.5 || r.bottom > cr.bottom + 0.5) {
              bad.push(`card-clipped: .${child.className} escapes its card ` +
                       `(child ${Math.round(r.top)}-${Math.round(r.bottom)} vs card ` +
                       `${Math.round(cr.top)}-${Math.round(cr.bottom)})`);
            }
          }
        }

        return {
          scrollH: doc.scrollHeight, viewH: window.innerHeight,
          scrollW: doc.scrollWidth, viewW: window.innerWidth,
          bad,
        };
      });
      if (overflow.bad.length || overflow.scrollH > overflow.viewH || overflow.scrollW > overflow.viewW) {
        throw new Error(
          `Preset "${preset.name}" (${preset.width}x${preset.height}) CLIPS content — ` +
            `refusing to write a truncated creative.\n` +
            `  document ${overflow.scrollW}x${overflow.scrollH} vs canvas ` +
            `${overflow.viewW}x${overflow.viewH}\n` +
            (overflow.bad.length
              ? `  elements outside the canvas:\n${overflow.bad.map((b) => `    - ${b}`).join("\n")}`
              : `  no single element flagged, so the overflow is in spacing/margins`),
        );
      }

      const out = join(OUT_DIR, `${preset.name}.png`);
      await page.screenshot({ path: out });
      await page.close();
      written.push(
        `${preset.name}.png  ${preset.width}x${preset.height}  fit=${fit}  (${preset.use})`,
      );
    }
  } finally {
    await browser.close();
  }

  console.log(`Wrote ${written.length} creative(s) to ${OUT_DIR}:`);
  for (const w of written) console.log(`  ${w}`);
  console.log(`\nAC2 text gate passed. Now LOOK at the PNGs — the gate reads text, not pixels.`);
  console.log(`Existing files in output dir: ${readdirSync(OUT_DIR).join(", ")}`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
