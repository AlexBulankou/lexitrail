'use strict';
/**
 * Playwright test-runner config for sweeping an EXTERNAL public URL.
 *
 * No `webServer` key, deliberately: this harness grades the DEPLOYED artifact.
 * Starting a local dev server here would let a sweep silently measure a tree
 * that was never shipped -- exactly the failure docs/itp-playwright-usability.md
 * was written to stop. The local path exists, but it is opt-in and labelled
 * (references/local-surrogate.md), not something the config does behind your back.
 *
 * Viewports are PROJECTS so one run covers both form factors and every finding
 * is attributable to the one it reproduced on.
 */
const { defineConfig } = require('@playwright/test');
const { VIEWPORTS } = require('./lib/routes');
const { resolveChromium } = require('./lib/browser');

// Resolved once, announced once -- a sweep whose screenshots came from an
// unexpected browser build must say which build, or the evidence is not
// reproducible. See lib/browser.js.
const chromium = resolveChromium();
console.log(`[uibug] ${chromium.note}`);

const BASE = process.env.UIBUG_URL || 'https://lexitrail.com';
const ENV = (process.env.UIBUG_ENV || 'both').toLowerCase();
const OUT = process.env.UIBUG_OUT || require('path').join(__dirname, '.runs', 'latest');

const wanted = ENV === 'both' ? ['desktop', 'mobile'] : [ENV];
const projects = wanted
  .filter((n) => VIEWPORTS[n])
  .map((n) => {
    const v = VIEWPORTS[n];
    return {
      name: n,
      use: {
        viewport: { width: v.width, height: v.height },
        isMobile: v.isMobile,
        hasTouch: v.hasTouch,
        deviceScaleFactor: v.deviceScaleFactor || 1,
        ...(v.userAgent ? { userAgent: v.userAgent } : {}),
        ...(chromium.executablePath
          ? { launchOptions: { executablePath: chromium.executablePath } }
          : {}),
      },
    };
  });

if (projects.length === 0) {
  throw new Error(`[uibug] UIBUG_ENV="${ENV}" matched no viewport (desktop|mobile|both)`);
}

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: /sweep\.spec\.js$/,
  // A live public site is not a hermetic fixture: one slow route must not fail
  // the sweep, and retrying a flaky NAVIGATION is legitimate. Retrying a
  // FINDING would not be -- detectors are pure functions of the rendered DOM.
  timeout: 120000,
  retries: process.env.CI ? 1 : 0,
  workers: 1,               // serial: parallel guest sessions would multiply demo rows
  fullyParallel: false,
  reporter: [['list'], ['json', { outputFile: require('path').join(OUT, 'playwright-report.json') }]],
  use: {
    baseURL: BASE,
    trace: 'off',
    video: 'off',
    screenshot: 'off',      // every capture is an explicit page.screenshot in the spec
    ignoreHTTPSErrors: false,
    actionTimeout: 15000,
    navigationTimeout: 45000,
  },
  projects,
});
