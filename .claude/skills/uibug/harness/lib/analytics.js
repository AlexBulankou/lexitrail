'use strict';
/**
 * Analytics beacon abort -- MANDATORY, and load-bearing enough to have its own file.
 *
 * Per docs/itp-playwright-usability.md 2.3: this harness drives the LIVE site, where
 * GA4 (G-910V8PX54C) is live. Every click we make fires real gtag events, so an
 * unguarded sweep silently poisons the production funnel with robot sessions.
 *
 * THE MATCHER IS A REGEX ON PURPOSE. gtag.js loads from `www.googletagmanager.com`
 * and beacons hit `www.google-analytics.com` / `region1.google-analytics.com`. The
 * obvious Playwright glob `**\/google-analytics.com/**` has no wildcard segment to
 * absorb the `www.` / `region1.` subdomain and no `/domain/` boundary when the host
 * IS `www.domain` -- so it matches nothing and lets every beacon through while
 * looking installed. A regex substring-matches the full URL and catches them all.
 *
 * It must be installed on the CONTEXT (not the page) and BEFORE the first goto,
 * or the page-load beacon escapes.
 */

const ANALYTICS_RE =
  /googletagmanager\.com|google-analytics\.com|analytics\.google\.com|doubleclick\.net/;

/**
 * @param {import('@playwright/test').BrowserContext} context
 * @returns {{blocked: number, completed: string[], assertClean: () => void}}
 */
async function installAnalyticsAbort(context) {
  const state = { blocked: 0, completed: [] };

  await context.route(ANALYTICS_RE, (route) => {
    state.blocked++;
    return route.abort();
  });

  // Trust but verify: if a beacon ever COMPLETES, the abort did not hold and we
  // need to know loudly rather than reporting a clean run. This is the check that
  // would have caught the broken-glob form.
  context.on('requestfinished', (req) => {
    if (ANALYTICS_RE.test(req.url())) state.completed.push(req.url());
  });

  state.assertClean = () => {
    if (state.completed.length > 0) {
      throw new Error(
        `[uibug] ${state.completed.length} analytics beacon(s) COMPLETED -- the GA4 ` +
          `funnel was polluted. First: ${state.completed[0]}`
      );
    }
  };

  return state;
}

module.exports = { installAnalyticsAbort, ANALYTICS_RE };
