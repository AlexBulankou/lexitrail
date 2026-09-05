/**
 * lexitrail#368 — social-scraper image URLs in the SPA shell must be ABSOLUTE.
 *
 * CRA substitutes %PUBLIC_URL% with the empty string in a production build, so
 * `%PUBLIC_URL%/images/...` emits `/images/...` — root-relative. Facebook,
 * Pinterest and Twitter scrapers require absolute URLs and treat a relative one
 * as absent, so the homepage failed Rich-Pin/unfurl checks while the image
 * itself was fine (verified 200 at the wire, 2026-09-05).
 *
 * 🔴 Why this needs a test and not just the comment in index.html: the failure is
 * INVISIBLE from inside the repo. The markup looks right, the build succeeds, the
 * image exists, and the only symptom is a third-party scraper silently declining
 * to show a card. There is no error and no discovery event — which is exactly the
 * shape that comes back if someone "tidies" these into %PUBLIC_URL% for
 * consistency with the favicon two lines below.
 *
 * ⚠️ Deliberately NOT asserted: that favicon/manifest are absolute. They must stay
 * %PUBLIC_URL%-relative — a browser resolves those against the document, and only
 * scrapers need absolute. Making everything absolute would be the over-correction.
 */
import fs from 'fs';
import path from 'path';
import { ORIGIN } from './hskPages';

const INDEX = path.join(__dirname, '..', '..', 'public', 'index.html');
const html = () => fs.readFileSync(INDEX, 'utf8');

// Every meta tag a social scraper reads an IMAGE out of.
const SCRAPER_IMAGE_TAGS = [
  /<meta\s+property="og:image"\s+content="([^"]+)"/,
  /<meta\s+property="twitter:image"\s+content="([^"]+)"/,
  /<meta\s+name="thumbnail"\s+content="([^"]+)"/,
];

describe('index.html — scraper image URLs are absolute (#368)', () => {
  test('positive control: every tag under test is actually present', () => {
    // Without this, a renamed or removed tag makes `match` null below and the
    // assertions would range over nothing — passing vacuously at the exact
    // moment the markup changed.
    const s = html();
    expect(SCRAPER_IMAGE_TAGS.filter((re) => !re.test(s))).toEqual([]);
  });

  test('each scraper image URL is absolute, and none is %PUBLIC_URL%-relative', () => {
    const s = html();
    const bad = SCRAPER_IMAGE_TAGS
      .map((re) => s.match(re)[1])
      .filter((url) => !url.startsWith(`${ORIGIN}/`));
    expect(bad).toEqual([]);
  });

  test('favicon and manifest stay %PUBLIC_URL%-relative — this is not a blanket rule', () => {
    // Guards the over-correction, not the bug. A browser resolves these against
    // the document; only scrapers need absolute.
    const s = html();
    expect(s).toMatch(/<link rel="icon" href="%PUBLIC_URL%\/favicon\.ico"/);
    expect(s).toMatch(/href="%PUBLIC_URL%\/manifest\.json"/);
  });
});
