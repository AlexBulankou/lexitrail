'use strict';
/**
 * The sweep. One test per route per viewport project.
 *
 * Each test emits three artifacts and asserts nothing about the product:
 *   screens/<viewport>/<NN>-<slug>.png   full-page capture (the "before" evidence)
 *   dom/<viewport>/<NN>-<slug>.json      every visible box + computed style
 *   findings.json                        detector output, merged across the run
 *
 * ASSERTION-FREE ON PURPOSE. This is an exploration pass whose output is read by
 * a human/vision step, not a regression gate. Baking today's defects into
 * expectations would make the harness red forever, and this repo has already
 * written down what happens then: "a gate people routinely override stops being
 * a gate -- the override becomes the habit" (e2e/README.md). The ONE thing it
 * does fail on is an analytics beacon completing, because that is a harm we
 * caused rather than a defect we found.
 *
 * It does record a three-state STATUS per route (ok / blind) so that "I could
 * not look" can never be summed up as "nothing found there".
 */
const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');

const { installAnalyticsAbort } = require('./lib/analytics');
const { installApiMock } = require('./lib/apimock');
const { enterGuestSession, dismissOnboarding, redact } = require('./lib/session');
const { collect } = require('./lib/detectors');
const { ROUTES } = require('./lib/routes');

const OUT = process.env.UIBUG_OUT || path.join(__dirname, '.runs', 'latest');
const BASE = process.env.UIBUG_URL || 'https://lexitrail.com';

const ensure = (p) => { fs.mkdirSync(p, { recursive: true }); return p; };

/** Append one JSON record. Append rather than rewrite: workers and retries must
 *  not clobber each other, and a crashed run still leaves the rows it got. */
const appendRecord = (rec) => {
  ensure(OUT);
  fs.appendFileSync(path.join(OUT, 'findings.ndjson'), JSON.stringify(rec) + '\n');
};

let analytics;
let apiMock = null;

// Surrogate-only. Off by default so a live sweep can never be silently mocked;
// see lib/apimock.js and references/local-surrogate.md.
const MOCK_API = process.env.UIBUG_API_MOCK === '1';

test.beforeEach(async ({ context }) => {
  // On the CONTEXT and BEFORE the first goto -- see lib/analytics.js for why
  // both of those words are load-bearing. Each test gets a fresh context, so
  // installing once globally would leave later tests unguarded.
  analytics = await installAnalyticsAbort(context);
  apiMock = MOCK_API ? await installApiMock(context) : null;
});

test.afterEach(async () => {
  // Guarded: if beforeEach itself threw, `analytics` is undefined, and an
  // unguarded call here replaces the real setup error with a TypeError from
  // this line -- which is what the first run of this harness actually did,
  // hiding a browser-resolution failure behind "cannot read assertClean".
  if (!analytics) return;
  // A completed beacon means we polluted the live GA4 funnel. That is the one
  // failure this harness owns, so it is the one thing it asserts.
  analytics.assertClean();
});

for (const [i, route] of ROUTES.entries()) {
  const nn = String(i + 1).padStart(2, '0');

  test(`${nn}-${route.slug}`, async ({ page }, testInfo) => {
    const viewport = testInfo.project.name;
    const screensDir = ensure(path.join(OUT, 'screens', viewport));
    const domDir = ensure(path.join(OUT, 'dom', viewport));
    const stem = `${nn}-${route.slug}`;

    const record = {
      viewport, route: route.slug, path: route.path, url: BASE + route.path,
      auth: Boolean(route.auth), note: route.note || null,
      status: 'blind', reason: null, findings: [], counts: {},
      screenshot: path.join('screens', viewport, `${stem}.png`),
      dom: path.join('dom', viewport, `${stem}.json`),
    };

    try {
      // Auth first, on the public home page, so the guest identity exists
      // before we ask for a gated route. Navigating to the gated route first
      // would screenshot the login card and label it "practice".
      if (route.auth) {
        await page.goto('/', { waitUntil: 'domcontentloaded' });
        const sess = await enterGuestSession(page);
        if (!sess.ok) {
          record.reason = `guest session failed (${sess.how})`;
          appendRecord(record);
          test.info().annotations.push({ type: 'blind', description: record.reason });
          return;
        }
        record.guestEmail = sess.email; // identity, never the token
      }

      const resp = await page.goto(route.path, { waitUntil: 'domcontentloaded' });
      if (resp && resp.status() >= 400) {
        record.reason = `HTTP ${resp.status()}`;
        appendRecord(record);
        return;
      }

      // Wait for real content, not for networkidle -- this SPA keeps a socket
      // open, so networkidle can never settle and would time out every route.
      if (route.wait) {
        await page.waitForSelector(route.wait, { timeout: 20000 }).catch(() => {});
      }
      await page.waitForTimeout(1200); // let the layout/font pass settle

      if (route.auth) await dismissOnboarding(page);

      // Did we actually land where we asked? A silent redirect back to the
      // login wall is the single most likely way this harness starts lying.
      const landedOnLoginWall = await page
        .locator('text=/ready to start learning/i').first().isVisible().catch(() => false);
      if (route.auth && landedOnLoginWall) {
        record.reason = 'redirected to the login wall despite a guest session';
        appendRecord(record);
        return;
      }

      // An error page IS a page: it has a navbar, a footer, visible elements and
      // a perfectly good DOM, so every "did we render?" check passes on it. The
      // first run of this harness reported `ok` for all four game routes while
      // every one of them showed "Error loading data" -- the finding count was
      // honest about a screen nobody asked to measure.
      //
      // So: name the error copy, and call it BLIND. BLIND rather than a finding,
      // because a backend that is down or a fixture that is wrong is not a UI
      // defect, and filing it as one produces a PR against the wrong repo.
      const errorCopy = await page
        .locator('text=/error loading|failed to load|please try again|something went wrong/i')
        .first().isVisible().catch(() => false);
      if (errorCopy) {
        record.reason =
          'route rendered an ERROR state, not its content -- backend unreachable, ' +
          'or (in surrogate mode) a fixture whose shape the app rejects';
        // Keep the screenshot: it is how you diagnose which of those it was.
        await page.screenshot({ path: path.join(screensDir, `${stem}-ERROR.png`), fullPage: false });
        appendRecord(record);
        console.log(`  [${viewport}] ${stem}: BLIND -- error state`);
        return;
      }

      await page.screenshot({ path: path.join(screensDir, `${stem}.png`), fullPage: true });
      // Above-the-fold too: fullPage stretches the viewport, which hides exactly
      // the clipping and overflow the detectors are here to find.
      await page.screenshot({ path: path.join(screensDir, `${stem}-fold.png`), fullPage: false });

      const data = await page.evaluate(`(${collect.toString()})()`);

      if (!data.elements || data.elements.length === 0) {
        record.reason = 'zero visible elements -- page rendered empty';
        appendRecord(record);
        return;
      }

      fs.writeFileSync(
        path.join(domDir, `${stem}.json`),
        JSON.stringify({ ...data, route: route.slug, viewport }, null, 1)
      );

      record.status = 'ok';
      record.findings = data.findings;
      record.elementCount = data.elements.length;
      record.counts = data.findings.reduce((a, f) => ((a[f.kind] = (a[f.kind] || 0) + 1), a), {});
      record.analyticsBlocked = analytics.blocked;
      if (apiMock) {
        // Recorded per route so a reader can tell a genuinely empty screen from
        // one whose data call never matched the mock.
        record.apiMocked = { served: apiMock.served, byEndpoint: apiMock.byEndpoint };
      }
      appendRecord(record);

      // Visible in the console run, so a human watching the sweep sees the shape
      // of what it found without opening the JSON.
      console.log(`  [${viewport}] ${stem}: ${data.elements.length} els, ` +
        `${data.findings.length} findings ${JSON.stringify(record.counts)}`);
    } catch (err) {
      record.reason = redact(err && err.message ? err.message : String(err));
      appendRecord(record);
      console.log(`  [${viewport}] ${stem}: BLIND -- ${record.reason}`);
    }

    expect(analytics.completed, 'analytics beacons must never complete').toHaveLength(0);
  });
}
