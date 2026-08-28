// lexitrail#186 — the SPA shell must not claim a canonical.
//
// `serve -s build` returns `public/index.html` for every unmatched URL, so ONE `<link
// rel="canonical" href="https://lexitrail.com/">` in that file is served on `/wordsets`,
// `/about`, `/game/2/PRACTICE`, `/privacy` and `/nonexistent-route-xyz` alike. Measured
// 2026-08-27: all of them returned HTTP 200 carrying canonical=/.
//
// That is stronger than SPA emptiness. An empty page is a page Google cannot rank; a homepage
// canonical is an explicit instruction to FOLD the URL into the homepage — the site actively
// asking for every page but one to be discarded.
//
// 🔴 THIS TEST IS A NEGATIVE ASSERTION, so it needs a control or it passes just as well against a
// file it failed to read, a moved path, or a typo'd pattern. Both controls below are load-bearing.
import fs from 'fs';
import path from 'path';

const PUBLIC = path.resolve(__dirname, '..', '..', 'public');
const shell = () => fs.readFileSync(path.join(PUBLIC, 'index.html'), 'utf8');

const CANONICAL = /<link[^>]+rel=["']canonical["']/i;

test('the SPA shell carries NO canonical', () => {
  expect(shell()).not.toMatch(CANONICAL);
});

test('CONTROL: the file was actually read and is the shell', () => {
  // Without this, the assertion above is satisfied by an empty string.
  const s = shell();
  expect(s.length).toBeGreaterThan(1000);
  expect(s).toContain('<title>Lexitrail');
  expect(s).toContain('id="root"');
});

test('CONTROL: the pattern DOES match a canonical, and does not match its absence', () => {
  // Without this, a typo in CANONICAL makes the main assertion vacuous and green forever.
  //
  // 📌 Deliberately SYNTHETIC rather than a real file. My first version read `public/hsk1.html`
  // (#183's page, which has a correct self-canonical) -- and it failed, because #183 was not
  // merged. A control that depends on unmerged work is a control that reds for a reason having
  // nothing to do with the thing under test. It also conflated two claims: "the pattern works"
  // and "that particular file has one". Only the first is what makes the negative assertion mean
  // something.
  expect('<link rel="canonical" href="https://lexitrail.com/x">').toMatch(CANONICAL);
  expect("<link rel='canonical' href='/x'>").toMatch(CANONICAL);       // quote style
  expect('<link rel="alternate" href="https://lexitrail.com/x">').not.toMatch(CANONICAL);
  expect('the word canonical in prose').not.toMatch(CANONICAL);        // not a bare substring
});
