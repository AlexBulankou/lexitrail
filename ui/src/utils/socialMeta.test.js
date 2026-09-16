/**
 * Link-preview metadata completeness on the generated static pages.
 *
 * ## The four defects this pins, all measured at the wire 2026-09-16
 *
 *   1. All 4,999 word pages declared `twitter:card = summary_large_image` and emitted NO
 *      `twitter:image` — a large-image card with no image for it to show. The six level pages
 *      DID emit one, which is how the bug survived review: the tag existed in the repo, just not
 *      in the renderer next door.
 *   2. No `og:image:width` / `og:image:height` / `og:image:alt` on any word or level page.
 *      Width and height are what let Facebook render the FIRST share of a URL with an image
 *      instead of queueing an async fetch to measure it and showing nothing that time.
 *   3. No `max-image-preview:large` anywhere on the property — no robots meta, no X-Robots-Tag.
 *   4. `og:site_name` and `og:locale` absent on all 5,010 generated pages.
 *
 * ## Why a CORPUS test and not only renderer tests
 *
 * Same structural reason staticPageCorpus.test.js gives for the GA4 tag: a renderer test asks
 * "does this function inject the tag", and there is no shared <head> in this repo — hskPages.js,
 * wordPages.js and glossPages.js each own their own, so the three drift one tag at a time and
 * every renderer test still passes. Defect 1 IS that drift. Only walking the artifact that ships
 * answers "did every page we publish come out with it", and only that question notices a fourth
 * page family added by someone who never read this directory.
 *
 * ## Scope honesty, so nobody re-describes these tags later
 *
 * These tags fix SOCIAL UNFURLS and raise a Google PREVIEW CEILING. They are not a ranking input.
 * `max-image-preview:large` is the documented prerequisite for the large-image treatment in
 * Discover, web search and Google Images — without it the cap is a thumbnail — but it is a
 * permission, not a trigger: Google still decides. Nothing here should ever be cited as an
 * expected ranking change.
 */

import fs from 'fs';
import path from 'path';
import {
  ORIGIN, SOCIAL_META, OG_IMAGE_PATH, OG_IMAGE_WIDTH, OG_IMAGE_HEIGHT,
} from './hskPages';
import { wordImageAlt } from './wordPages';

const PUBLIC_DIR = path.resolve(__dirname, '..', '..', 'public');

/**
 * Pages deliberately published WITHOUT the shared block, each with the reason — the same
 * discipline (and the same staleness guard) as staticPageCorpus.test.js's EXEMPT.
 */
const EXEMPT = {
  '404.html': 'the standalone error page — not a content surface and not a share target, '
            + 'the precedent staticPageCorpus.test.js already cites for pages outside the funnel',
  'index.html': 'the CRA SPA shell, hand-maintained rather than generated — it is the ONE page '
              + 'these three generators do not produce, so changing it is a separate change with '
              + 'a separate review; it already carries og:image:width/height for the same asset',
};

function walkHtml(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkHtml(full));
    else if (entry.isFile() && entry.name.endsWith('.html')) out.push(full);
  }
  return out;
}

let PAGES;
beforeAll(() => {
  PAGES = walkHtml(PUBLIC_DIR).map((p) => ({
    rel: path.relative(PUBLIC_DIR, p),
    html: fs.readFileSync(p, 'utf8'),
  }));
});

const generated = () => PAGES.filter((p) => !(p.rel in EXEMPT));
const attr = (html, tag) => {
  const m = html.match(new RegExp(`<meta (?:property|name)="${tag}" content="([^"]*)"`));
  return m && m[1];
};

describe('og:image dimensions are a claim about a REAL file', () => {
  /**
   * 🔴 The load-bearing test of this change. og:image:width/height are a promise about the bytes
   * at OG_IMAGE_PATH, repeated on 5,005 pages. If the asset is ever re-cut at another size, every
   * one of those pages starts lying to Facebook's scraper — and the symptom is invisible from
   * inside the repo, exactly like ogAbsolute.test.js's: the markup looks right, the build
   * succeeds, the image exists, and a third-party scraper silently lays out the card wrong.
   *
   * So the numbers are checked against the PNG's own IHDR header rather than trusted. 1200x630 is
   * what it measured on 2026-09-16; this test is what keeps that true.
   */
  it('OG_IMAGE_WIDTH/HEIGHT match the committed PNG header', () => {
    const file = path.join(PUBLIC_DIR, OG_IMAGE_PATH);
    expect(fs.existsSync(file)).toBe(true);
    const buf = fs.readFileSync(file);
    // PNG: 8-byte signature, then the IHDR chunk — width and height are big-endian uint32 at
    // byte 16 and byte 20. Read directly rather than pulling in an image library for 8 bytes.
    expect(buf.slice(1, 4).toString('ascii')).toBe('PNG');
    expect(buf.readUInt32BE(16)).toBe(OG_IMAGE_WIDTH);
    expect(buf.readUInt32BE(20)).toBe(OG_IMAGE_HEIGHT);
  });
});

describe('the shared block says what it is meant to say', () => {
  it('carries max-image-preview:large, og:site_name and og:locale', () => {
    expect(SOCIAL_META).toContain('<meta name="robots" content="max-image-preview:large">');
    expect(SOCIAL_META).toContain('<meta property="og:site_name" content="LexiTrail">');
    expect(SOCIAL_META).toContain('<meta property="og:locale" content="en_US">');
  });

  /**
   * 🔴 `max-image-preview:large` is a CEILING. A `noindex` or `nosnippet` smuggled into the same
   * shared block would deindex the whole generated corpus in one commit — 5,010 pages, from a
   * three-line constant, with no other symptom. This is the cheapest possible guard against that.
   */
  it('CONTROL: the robots block never suppresses indexing or snippets', () => {
    expect(SOCIAL_META).not.toMatch(/noindex|nofollow|nosnippet|noarchive|none/);
  });
});

describe('wordImageAlt — a real per-word description, not boilerplate', () => {
  const w = { level: 6, word: '名誉', pinyin: 'míngyù', english: 'reputation' };

  it('names the word, its reading and its gloss', () => {
    expect(wordImageAlt(w)).toBe(
      '名誉 — míngyù — reputation. An HSK 6 Chinese vocabulary word on LexiTrail.',
    );
  });

  /**
   * CONTROL: it VARIES. Alt text identical on 4,999 pages would be boilerplate wearing an
   * accessibility label, and every assertion above would still pass.
   */
  it('CONTROL: it varies by word and by level', () => {
    const other = wordImageAlt({ level: 1, word: '我', pinyin: 'wǒ', english: 'I' });
    expect(other).not.toBe(wordImageAlt(w));
    expect(other).toContain('HSK 1');
  });

  /**
   * words.csv has rows with no gloss and rows with no reading. Joining blindly would render
   * "名誉 —  — . An HSK 6 …" — visible punctuation debris read aloud by a screen reader.
   */
  it('degrades cleanly when pinyin or gloss is missing', () => {
    expect(wordImageAlt({ level: 3, word: '啊', pinyin: '', english: '' }))
      .toBe('啊. An HSK 3 Chinese vocabulary word on LexiTrail.');
    expect(wordImageAlt({ level: 3, word: '啊', pinyin: 'a', english: '' }))
      .toBe('啊 — a. An HSK 3 Chinese vocabulary word on LexiTrail.');
  });
});

describe('the EMITTED corpus — every generated page, not the renderers', () => {
  /**
   * Non-vacuity, same rationale as staticPageCorpus.test.js: a walk that returns nothing makes
   * every assertion below pass on an empty list, which looks exactly like a clean corpus.
   */
  it('the walk actually finds the corpus', () => {
    expect(generated().length).toBeGreaterThan(1000);
  });

  it('every generated page carries the shared robots/site_name/locale block', () => {
    const missing = generated()
      .filter((p) => !p.html.includes(SOCIAL_META))
      .map((p) => p.rel);
    expect(missing).toEqual([]);
  });

  /**
   * Defect 1, pinned on the artifact. A page may not declare a large-image card and then decline
   * to name an image — that combination is strictly worse than `summary`, because the scraper
   * reserves the large slot and renders it empty.
   */
  it('no page declares summary_large_image without a twitter:image', () => {
    const broken = generated()
      .filter((p) => p.html.includes('content="summary_large_image"'))
      .filter((p) => !attr(p.html, 'twitter:image'))
      .map((p) => p.rel);
    expect(broken).toEqual([]);
  });

  it('every generated page names an og:image with its width, height and alt', () => {
    const incomplete = generated().filter((p) => !(
      attr(p.html, 'og:image')
      && attr(p.html, 'og:image:width')
      && attr(p.html, 'og:image:height')
      && attr(p.html, 'og:image:alt')
    )).map((p) => p.rel);
    expect(incomplete).toEqual([]);
  });

  /**
   * Every image URL a scraper reads must be ABSOLUTE and must resolve to a file in this repo.
   * ogAbsolute.test.js makes the absolute-URL argument for the SPA shell; this extends it to the
   * 5,010 pages, and adds the existence check — a card pointing at a 404 renders worse than one
   * with no image at all, and the gloss pages point at per-word cards that are generated by a
   * DIFFERENT script (generate-gloss-cards.js), so "the PNG was never rendered" is reachable.
   */
  it('every og:image and twitter:image is absolute and exists on disk', () => {
    const bad = [];
    for (const p of generated()) {
      for (const tag of ['og:image', 'twitter:image']) {
        const url = attr(p.html, tag);
        if (!url) continue;
        if (!url.startsWith(`${ORIGIN}/`)) { bad.push(`${p.rel}: ${tag} not absolute`); continue; }
        const file = path.join(PUBLIC_DIR, url.slice(ORIGIN.length));
        if (!fs.existsSync(file)) bad.push(`${p.rel}: ${tag} -> missing ${url}`);
      }
    }
    expect(bad).toEqual([]);
  });

  /**
   * CONTROL, and the reason the assertions above are measurements rather than tautologies: the
   * predicate CAN return false, and does, on real pages of this repo's own shape. An exemption
   * list is also the thing that silently widens until the check covers nothing — so each entry is
   * pinned as STILL NEEDED. Give 404.html the block and this reds, asking you to delete the
   * entry rather than leaving a carve-out that hides a real regression there later.
   */
  it('CONTROL: every exemption is real, reasoned and still needed', () => {
    for (const [rel, reason] of Object.entries(EXEMPT)) {
      const page = PAGES.find((p) => p.rel === rel);
      expect(page).toBeDefined();
      expect(reason.length).toBeGreaterThan(20);
      expect(page.html.includes(SOCIAL_META)).toBe(false);
    }
  });
});
