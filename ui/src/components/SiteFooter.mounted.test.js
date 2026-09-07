// PR #405 review AC (hc2/HCL): the 447-test static suite proves the three
// generators; nothing asserted the SPA mounts. Precisely that gap shipped a
// TermsOfService that IMPORTED SiteFooter and never rendered it. An import is
// a MENTION; a JSX element is a USE — the reviewer's own postmortem — so this
// pin discriminates on `<SiteFooter`, never on the import line.
//
// Structural pins, not RTL renders, following WordCard.hintText.test.js's
// stated constraint (this repo has no @testing-library/react; components pull
// contexts/services and don't render standalone). Comments are stripped first
// so a prose mention can't satisfy a pin — same discipline as that file.
//
// Game.js / SessionSize / Completed are deliberately exempt (fixed scroll
// containers mid-activity — the PR body's ruling). Their absence is asserted
// too: a footer appearing there should be a decision, not a drive-by.
const fs = require('fs');
const path = require('path');

const C = (f) => path.join(__dirname, f);
const stripComments = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

const MOUNTED = ['Home.js', 'About.js', 'NotFound.js', 'PrivacyPolicy.js',
  'TermsOfService.js', 'Wordsets.js'];
const EXEMPT = ['Game.js'];

describe('SiteFooter is USED (JSX), not merely imported', () => {
  test.each(MOUNTED)('%s renders <SiteFooter', (f) => {
    const src = stripComments(fs.readFileSync(C(f), 'utf8'));
    // control: the import alone must NOT satisfy the pin
    expect(src).toMatch(/import\s+SiteFooter/);
    expect(src).toMatch(/<SiteFooter\s*\/?>/);
  });

  test.each(EXEMPT)('%s stays footer-free (deliberate exemption)', (f) => {
    const src = stripComments(fs.readFileSync(C(f), 'utf8'));
    expect(src).not.toMatch(/<SiteFooter\s*\/?>/);
  });
});
