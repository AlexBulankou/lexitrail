// lexitrail#204 — `serve.json`'s rewrites and `App.js`'s routes must agree.
//
// THE DEFECT THIS EXISTS FOR. Before #204 the server config was a single catch-all
// `{"source":"**"}` plus `serve -s`, so every path returned the SPA shell with HTTP 200 — an
// indexable soft-404 on every typo'd or stale inbound link. The fix enumerates the real routes,
// which buys the 404 and creates a NEW hazard: a route added to `App.js` and not to `serve.json`
// now returns 404 to real users, silently, with nothing in the repo to notice.
//
// 🔴 So this test is the point of the change, not an accessory to it. It DERIVES the required
// rewrite sources from App.js rather than listing them, because a hand-maintained second list is
// the thing that just went wrong one level up (decipher#3067: a relationship between two files
// encoded as a constant).
import fs from 'fs';
import path from 'path';

const UI = path.resolve(__dirname, '..', '..');
const app = () => fs.readFileSync(path.join(UI, 'src', 'App.js'), 'utf8');
const serveCfg = () => JSON.parse(fs.readFileSync(path.join(UI, 'public', 'serve.json'), 'utf8'));

/** Every `<Route path="...">` in App.js, minus the client-side catch-all. */
export const appRoutes = () =>
  [...app().matchAll(/<Route\s+[^>]*path=["']([^"']+)["']/gs)].map((m) => m[1])
    .filter((p) => p !== '*');

/** The serve.json rewrite sources a given React Router pattern requires.
 *
 * `/wordsets/*`         -> the bare path AND its subtree
 * `/game/:a/:b?`        -> with and without the optional segment
 * anything else         -> itself
 */
export const requiredSources = (routePath) => {
  if (routePath.endsWith('/*')) {
    const base = routePath.slice(0, -2);
    return [base, `${base}/**`];
  }
  if (routePath.endsWith('?')) {
    const withOpt = routePath.slice(0, -1);
    return [withOpt.slice(0, withOpt.lastIndexOf('/')), withOpt];
  }
  return [routePath];
};

test('CONTROL: App.js is being read and parsed', () => {
  // Without this, an empty route list makes every assertion below vacuous.
  const r = appRoutes();
  expect(r).toContain('/');
  expect(r).toContain('/about');
  expect(r.length).toBeGreaterThanOrEqual(7);
});

test('CONTROL: requiredSources expands the two special shapes', () => {
  expect(requiredSources('/wordsets/*')).toEqual(['/wordsets', '/wordsets/**']);
  expect(requiredSources('/game/:wordsetId/:mode?'))
    .toEqual(['/game/:wordsetId', '/game/:wordsetId/:mode']);
  expect(requiredSources('/privacy')).toEqual(['/privacy']);
});

test('🔴 every App.js route has a serve.json rewrite', () => {
  const sources = new Set(serveCfg().rewrites.map((r) => r.source));
  const missing = appRoutes()
    .flatMap(requiredSources)
    .filter((s) => !sources.has(s));
  expect(missing).toEqual([]);
});

test('the catch-all is GONE — it is what made every path a 200', () => {
  const sources = serveCfg().rewrites.map((r) => r.source);
  expect(sources).not.toContain('**');
  expect(sources).not.toContain('/**');
});

test('no rewrite points anywhere but the shell', () => {
  // A rewrite to a real file would shadow that file's own headers and status.
  for (const r of serveCfg().rewrites) expect(r.destination).toBe('/index.html');
});

test('🔴 the Dockerfile does NOT pass -s', () => {
  // `--single` injects its own `**` catch-all that overrides the enumeration entirely. Measured:
  // with `-s`, an enumerated rewrite list AND a 404.html still returned 200 on unknown paths.
  // This is the one line that makes everything else in #204 take effect.
  const df = fs.readFileSync(path.join(UI, 'Dockerfile'), 'utf8');
  const cmd = df.split('\n').find((l) => l.startsWith('CMD'));
  expect(cmd).toBeDefined();
  expect(cmd).toContain('"serve"');
  expect(cmd).not.toMatch(/"-s"|"--single"/);
});

test('404.html exists, is standalone, and is noindex', () => {
  const p404 = fs.readFileSync(path.join(UI, 'public', '404.html'), 'utf8');
  expect(p404).toMatch(/name="robots"\s+content="noindex"/);
  // Standalone on purpose: a 404 page that needs the app to boot is a 404 page that can fail.
  expect(p404).not.toMatch(/<script[^>]+src=/);
  expect(p404).toMatch(/href="\/"/);
});
