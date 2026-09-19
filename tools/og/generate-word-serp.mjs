/**
 * Per-word SERP thumbnail generator for Lexitrail (facet lt-serp-perword).
 *
 * Renders a 1200×1200 square for each of the ~5,000 word pages. Each image
 * features the Chinese character inside a 田字格 (tianzige) grid with pinyin,
 * English gloss, and HSK badge. The image is distinctive at Google's ~92px
 * mobile SERP thumbnail size because:
 *   - the 田字格 grid is a culturally recognisable frame
 *   - the crimson brand colour stands out against white SERP backgrounds
 *   - the character is large enough to be legible even at small sizes
 *
 * Output: ui/public/images/serp/hsk{N}/{encoded-word}.png
 *
 * Usage:
 *   node tools/og/generate-word-serp.mjs                    # all ~5,000 words
 *   node tools/og/generate-word-serp.mjs --level 1          # HSK 1 only (~150)
 *   node tools/og/generate-word-serp.mjs --word 我           # single word
 *   node tools/og/generate-word-serp.mjs --check             # verify all exist
 */
import { chromium } from "playwright";
import { readFileSync, mkdirSync, existsSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..", "..");
const TEMPLATE = join(HERE, "word-serp-template.html");
const CSV = join(REPO, "terraform", "csv", "words.csv");
const OUT_BASE = join(REPO, "ui", "public", "images", "serp");

/** Encode a word for filesystem use — mirrors ui/src/utils/wordPages.js wordFilename. */
function encodedFilename(word) {
  return encodeURIComponent(word) + ".jpg";
}

function outPath(level, word) {
  return join(OUT_BASE, `hsk${level}`, encodedFilename(word));
}

/** Parse words.csv manually (no papaparse dependency in tools/og/).
 *  Format: word_id,word,wordset_id,def1,def2
 *  def1=pinyin, def2=english. def2 may be quoted (contains commas).
 *  Returns [{word, pinyin, english, level}]. Merges senses. */
function loadWords() {
  const raw = readFileSync(CSV, "utf8");
  const lines = raw.trim().replace(/\r/g, "").split("\n").slice(1); // skip header
  const seen = new Map();

  for (const line of lines) {
    if (!line.trim()) continue;
    // Parse respecting double-quoted fields (def2 can contain commas)
    const fields = [];
    let i = 0;
    while (i < line.length) {
      if (line[i] === '"') {
        // Quoted field
        let end = line.indexOf('"', i + 1);
        while (end !== -1 && end + 1 < line.length && line[end + 1] === '"') {
          end = line.indexOf('"', end + 2);
        }
        fields.push(line.slice(i + 1, end === -1 ? line.length : end));
        i = end === -1 ? line.length : end + 2; // skip closing quote + comma
      } else {
        const comma = line.indexOf(",", i);
        if (comma === -1) {
          fields.push(line.slice(i));
          break;
        }
        fields.push(line.slice(i, comma));
        i = comma + 1;
      }
    }

    const [, word, wordsetId, pinyin, english] = fields;
    if (!word || !pinyin) continue;
    const level = parseInt(wordsetId, 10);
    if (level < 1 || level > 6) continue;

    const key = `${level}:${word}`;
    if (!seen.has(key)) {
      seen.set(key, { word: word.trim(), pinyin: pinyin.trim(), english: (english || "").trim(), level });
    } else {
      const existing = seen.get(key);
      const eng = (english || "").trim();
      if (eng && !existing.english.includes(eng)) {
        existing.english += `; ${eng}`;
      }
    }
  }
  return [...seen.values()];
}

async function main() {
  const argv = process.argv.slice(2);
  const levelIdx = argv.indexOf("--level");
  const wordIdx = argv.indexOf("--word");
  const check = argv.includes("--check");
  const onlyLevel = levelIdx >= 0 ? parseInt(argv[levelIdx + 1], 10) : null;
  const onlyWord = wordIdx >= 0 ? argv[wordIdx + 1] : null;

  let words = loadWords();
  if (onlyLevel) words = words.filter((w) => w.level === onlyLevel);
  if (onlyWord) words = words.filter((w) => w.word === onlyWord);

  if (!words.length) {
    console.error("No words matched the filter.");
    process.exit(1);
  }

  if (check) {
    let missing = 0;
    for (const w of words) {
      if (!existsSync(outPath(w.level, w.word))) {
        missing++;
        if (missing <= 5) console.error(`  missing: ${outPath(w.level, w.word)}`);
      }
    }
    if (missing) {
      console.error(`${missing} SERP image(s) missing. Run: node tools/og/generate-word-serp.mjs`);
      process.exit(1);
    }
    console.log(`ok: ${words.length} per-word SERP images present`);
    return;
  }

  console.log(`Generating ${words.length} per-word SERP thumbnails...`);

  // Ensure output dirs
  for (let l = 1; l <= 6; l++) {
    mkdirSync(join(OUT_BASE, `hsk${l}`), { recursive: true });
  }

  const launchOpts = {};
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE) {
    launchOpts.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  }

  const browser = await chromium.launch(launchOpts);
  let generated = 0;

  try {
    // Batch in pages of 50 for memory management
    const BATCH = 50;
    for (let i = 0; i < words.length; i += BATCH) {
      const batch = words.slice(i, i + BATCH);
      const page = await browser.newPage({
        viewport: { width: 1200, height: 1200 },
        deviceScaleFactor: 1,
      });
      await page.goto(`file://${TEMPLATE}`);
      // Wait for fonts
      await page.evaluate(() => document.fonts.ready);

      for (const w of batch) {
        const charCount = [...w.word].length;

        await page.evaluate(
          ({ word, pinyin, gloss, level, charCount }) => {
            document.getElementById("hanzi").textContent = word;
            document.getElementById("hanzi").className =
              "hanzi" + (charCount > 1 ? ` chars-${Math.min(charCount, 4)}` : "");
            document.getElementById("pinyin").textContent = pinyin;
            // Truncate long glosses to prevent overflow
            document.getElementById("gloss").textContent =
              gloss.length > 60 ? gloss.slice(0, 57) + "…" : gloss;
            document.getElementById("badge").textContent = `HSK ${level}`;
          },
          { word: w.word, pinyin: w.pinyin, gloss: w.english, level: w.level, charCount },
        );

        const out = outPath(w.level, w.word);
        await page.screenshot({ path: out, type: "jpeg", quality: 85 });
        generated++;
      }

      await page.close();

      if (i % 500 === 0 && i > 0) {
        console.log(`  ... ${generated} / ${words.length}`);
      }
    }
  } finally {
    await browser.close();
  }

  console.log(`Done: ${generated} per-word SERP thumbnails written to ${OUT_BASE}`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
