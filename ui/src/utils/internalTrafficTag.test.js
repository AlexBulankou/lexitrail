/**
 * issue-NNN — internal traffic is designated by a TAG, not by a GA4 console IP rule.
 *
 * IP rules cannot cover the traffic that actually pollutes this property: the
 * Playwright e2e runs, the agent probes and Alex's own phone have no stable IP
 * (#394 measured one harness run at ~1.6% of monthly sessions, clustering during
 * investigation bursts). The tag marks at source instead. Nothing is EXCLUDED until
 * the GA4 "Internal Traffic" data filter is set Active in the console -- that half
 * has no Admin API method at all -- so this file pins the MARKING only.
 *
 * 🔴 WHAT THIS FILE IS REALLY GUARDING. An UNCONDITIONAL `traffic_type: 'internal'`
 * marks every real visitor internal, and the moment that console filter goes Active
 * it strips 100% of live traffic -- non-retroactively, so the data is gone and the
 * reports read as "nobody visited". That failure is silent in review (the tag looks
 * present and correct) and unrecoverable afterwards.
 *
 * So this does not grep for a string. It EXECUTES the shipped block against
 * simulated visitors and asserts who comes out marked -- because "the code contains
 * a conditional" and "the conditional is the right way round" are different claims,
 * and only the second one is the one that destroys the property when false.
 */

import fs from 'fs';
import path from 'path';
import { stripComments } from './stripComments';

const INDEX_HTML = path.join(__dirname, '..', '..', 'public', 'index.html');

/**
 * The bare `<script>` block. index.html also carries `<script async src=...>` (the
 * gtag loader), `<script src="%PUBLIC_URL%/config.js">` and a
 * `<script type="application/ld+json">` -- none of which this regex matches, because
 * it requires the bare opening tag.
 */
function gaBlock() {
  const html = fs.readFileSync(INDEX_HTML, 'utf8');
  const m = html.match(/<script>\n([\s\S]*?)<\/script>/);
  expect(m).not.toBeNull();
  expect(m[1]).toContain("gtag('config'");
  return m[1];
}

/**
 * Run the shipped block with `location`, `navigator` and `localStorage` shadowed by
 * parameters, and report the `gtag('config', ...)` call it produced.
 *
 * `window` is shadowed too, but `dataLayer` goes on the real global because the
 * block's own `function gtag(){dataLayer.push(arguments);}` reads it UNQUALIFIED --
 * exactly as in a browser, where `window.dataLayer = ...` creates that global.
 * Shadowing it instead leaves the helper unbound and every case throws rather than
 * measures, which would look like a passing suite of vacuous tests.
 */
function visit({ search = '', webdriver = false, store = {}, storageThrows = false } = {}) {
  const dataLayer = [];
  globalThis.dataLayer = dataLayer;
  const deny = () => { throw new Error('storage disabled'); };
  const localStorage = storageThrows
    ? { getItem: deny, setItem: deny, removeItem: deny }
    : {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: (k) => { delete store[k]; },
    };
  // eslint-disable-next-line no-new-func
  new Function('window', 'location', 'navigator', 'localStorage', gaBlock())(
    { dataLayer }, { search }, { webdriver }, localStorage);
  const config = dataLayer.map((a) => Array.from(a)).find((a) => a[0] === 'config');
  return { config, store };
}

const isMarked = (v) => !!(v.config && v.config[2] && v.config[2].traffic_type === 'internal');

describe('issue-NNN: internal traffic is marked by tag, and ONLY internal traffic is', () => {
  it('the block still installs the tag — a marking that broke the install fixes nothing', () => {
    const v = visit();
    expect(v.config).toBeDefined();
    expect(v.config[1]).toBe('G-910V8PX54C');
  });

  // ---- visitors who must NEVER be marked -------------------------------------

  it('a plain visitor is NOT marked', () => {
    expect(isMarked(visit())).toBe(false);
  });

  it('a visitor arriving with ordinary query params is NOT marked', () => {
    // The opt-in is a substring test (`indexOf('internal=1')`), so this is the case
    // that would catch it firing on a campaign URL that merely contains the word.
    expect(isMarked(visit({ search: '?utm_source=google&utm_campaign=hsk1&q=internal' }))).toBe(false);
  });

  it('a visitor with storage disabled (private mode) is NOT marked', () => {
    // The catch must fall through leaving the flag false. A catch that left it true,
    // or a throw that escaped and killed the tag, is the whole reason for the try.
    expect(isMarked(visit({ storageThrows: true }))).toBe(false);
  });

  it('a real browser reporting navigator.webdriver === false is NOT marked', () => {
    expect(isMarked(visit({ webdriver: false }))).toBe(false);
  });

  it('an older browser where navigator.webdriver is undefined is NOT marked', () => {
    // `=== true`, not truthiness and not `!== false` -- the latter would mark every
    // browser predating the property, i.e. silently, a large slice of real mobile.
    expect(isMarked(visit({ webdriver: undefined }))).toBe(false);
  });

  // ---- visitors who must be marked -------------------------------------------

  it('?internal=1 marks, and persists to the next visit without the query string', () => {
    const first = visit({ search: '?internal=1' });
    expect(isMarked(first)).toBe(true);
    expect(isMarked(visit({ store: first.store }))).toBe(true);
  });

  it('?internal=0 clears the opt-in — the escape hatch actually works', () => {
    const out = visit({ search: '?internal=0', store: { 'lexitrail.internal': '1' } });
    expect(isMarked(out)).toBe(false);
    expect(isMarked(visit({ store: out.store }))).toBe(false);
  });

  it('Playwright/Selenium are marked with no opt-in — the #394 harness runs', () => {
    expect(isMarked(visit({ webdriver: true }))).toBe(true);
  });

  it('automation is marked even when storage throws', () => {
    // The webdriver check sits AFTER the try/catch on purpose: a harness running
    // with storage disabled must still be caught.
    expect(isMarked(visit({ webdriver: true, storageThrows: true }))).toBe(true);
  });

  // ---- the structural guard ---------------------------------------------------

  it('traffic_type is assigned on exactly ONE line, inside the guard', () => {
    // stripComments is load-bearing and NOT decoration: the block explains the
    // hazard in prose, so `traffic_type` appears 3x raw and 1x in code. A naive
    // count is use/mention-vulnerable and would red on the explanation itself --
    // whose natural "repair" is deleting the warning. (Measured: 3 raw, 1 stripped.)
    const code = stripComments(gaBlock());
    expect(code.match(/traffic_type/g)).toHaveLength(1);
    expect(code).toContain("if (ltInternal) ltCfg.traffic_type = 'internal';");
  });

  it('CONTROL: stripComments kept the code and removed the comments', () => {
    // Without this, a stripper that ate only the guard line would pass the test
    // above vacuously. Both directions, per stripComments' own docstring, which
    // requires exactly this of every test that uses it.
    const code = stripComments(gaBlock());
    expect(code).toContain('var ltInternal = false;');
    expect(code).not.toContain('Sammamish');
  });
});
