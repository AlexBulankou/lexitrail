/**
 * issue-393 (zz1's extended acceptance, relaying Alex 2026-09-07: "any new
 * pages we publish always have tags") — every EMITTED page carries the tag.
 *
 * ## Why this is not covered by staticPageAnalytics.test.js
 *
 * That file pins the three RENDERERS, one synthetic input each. It is the
 * right test and it cannot catch this class, for a reason that is structural
 * rather than a matter of coverage:
 *
 *   - its population is ENUMERATED BY HAND (hsk, word, gloss), so a FOURTH
 *     family added later is invisible to it by construction — the new
 *     generator simply is not in the list, and nothing reds;
 *   - it exercises one input per renderer, so a branch inside a generator
 *     that skips the snippet for some page shape passes all three.
 *
 * This walks the artifact that actually ships instead. A renderer test asks
 * "does this function inject the tag"; this asks "did every page we publish
 * come out with it", and only the second question survives someone adding a
 * generator without reading this directory.
 *
 * ## The exemption is a real page, and that is deliberate
 *
 * `404.html` is untagged on purpose (this issue's own text cites it as the
 * standalone-page precedent). It doubles as the NEGATIVE CONTROL: a predicate
 * that matched everything would report 5012/5012 and look identical to a
 * correct one. The single miss, on exactly the page you would predict, is
 * what makes the other 5011 a verdict rather than a grep that cannot fail.
 *
 * So the exemption list is asserted EXACT and STILL NEEDED — if 404.html ever
 * gains the tag, this reds and tells you to delete the entry, rather than
 * letting the list quietly accumulate pages nobody re-examined.
 */

import fs from 'fs';
import path from 'path';
import { GA4_ID } from './hskPages';

const PUBLIC_DIR = path.resolve(__dirname, '..', '..', 'public');

/**
 * Pages deliberately published WITHOUT the tag, each with the reason.
 * A bare list rots into "things that were failing when someone gave up", so
 * every entry carries why, and `EXEMPT_STILL_NEEDED` below proves each one is
 * still untagged rather than a leftover.
 */
const EXEMPT = {
  '404.html': 'the standalone error page — not a content surface, and the '
            + 'precedent this issue cites for pages outside the funnel',
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

const isTagged = (html) => html.includes(GA4_ID);

let PAGES;
beforeAll(() => {
  PAGES = walkHtml(PUBLIC_DIR).map((p) => ({
    rel: path.relative(PUBLIC_DIR, p),
    html: fs.readFileSync(p, 'utf8'),
  }));
});

describe('issue-393: the EMITTED corpus, not the renderers', () => {
  /**
   * Non-vacuity. A walk that returns nothing — a moved directory, a renamed
   * extension, a bad `__dirname` join — makes every assertion below pass on
   * an empty list, which is indistinguishable from a fully tagged corpus.
   * The floor is deliberately well under the current 5012 so ordinary content
   * churn does not red it; it only catches the walk finding ~nothing.
   */
  it('the walk actually finds the corpus', () => {
    expect(PAGES.length).toBeGreaterThan(1000);
  });

  it('every emitted page carries the measurement id', () => {
    const untagged = PAGES.filter((p) => !isTagged(p.html))
      .map((p) => p.rel)
      .filter((rel) => !(rel in EXEMPT));
    expect(untagged).toEqual([]);
  });

  /**
   * The negative control, and the reason the assertion above is a measurement
   * rather than a tautology: the predicate CAN return false, and does, on a
   * real page of this repo's own shape — not on a synthetic string.
   */
  it('CONTROL: the predicate can return false — 404.html is genuinely untagged', () => {
    const notFound = PAGES.find((p) => p.rel === '404.html');
    expect(notFound).toBeDefined();
    expect(isTagged(notFound.html)).toBe(false);
  });

  /**
   * An exemption list is the thing that silently widens until the check covers
   * nothing. This pins that every entry is STILL untagged: tag an exempt page
   * and this reds, asking you to remove the entry rather than leaving a stale
   * carve-out that would hide a real regression on that page later.
   */
  it('every exemption is still NEEDED — the list cannot go stale', () => {
    for (const [rel, reason] of Object.entries(EXEMPT)) {
      const page = PAGES.find((p) => p.rel === rel);
      expect(page).toBeDefined();
      expect(reason.length).toBeGreaterThan(20);
      expect(isTagged(page.html)).toBe(false);
    }
  });

  it('the exemption list is EXACTLY the one page, so a widened list is visible', () => {
    expect(Object.keys(EXEMPT)).toEqual(['404.html']);
  });

  /**
   * The tag has two halves and either alone is inert: the loader without the
   * config sends nothing, the config without the loader has no gtag to call.
   * `isTagged` only looks for the id, so without this a page carrying the id
   * in a comment — or in one half only — would count as tagged.
   */
  it('every tagged page carries BOTH halves, not just the id', () => {
    const broken = PAGES
      .filter((p) => !(p.rel in EXEMPT))
      // issue-NNN: the closing paren is deliberately NOT matched any more. The
      // config call now takes a third argument (`gtag('config', ID, ltCfg)`) so
      // internal traffic can be marked at source. Pinning `')` pinned the ARGUMENT
      // COUNT, which was never this test's subject -- it asks whether both halves
      // of the install are present, and a third argument makes neither half absent.
      // The measurement id is still matched EXACTLY, so a wrong, truncated or
      // missing id still reds, and the loader half is untouched.
      .filter((p) => !(p.html.includes(`googletagmanager.com/gtag/js?id=${GA4_ID}`)
                    && p.html.includes(`gtag('config', '${GA4_ID}'`)))
      .map((p) => p.rel);
    expect(broken).toEqual([]);
  });
});
