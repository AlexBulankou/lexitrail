#!/usr/bin/env node
'use strict';
/**
 * Preflight: is the target actually reachable from THIS box?
 *
 * Three-state, same convention as e2e/tap_targets.py:
 *   0 PASS  -- reachable, HTTP < 400
 *   1 FAIL  -- reachable but the server errored
 *   2 BLIND -- could not reach it (egress policy, DNS, TLS)
 *
 * A blocking proxy answers with a real HTTP 403, so status code alone cannot
 * separate BLIND from FAIL; we key off `x-deny-reason` / the allowlist body.
 *
 * BLIND is separate from FAIL because they need opposite responses. A 500 is a
 * finding about the site. A blocked CONNECT is a finding about OUR sandbox, and
 * reporting it as "the site is broken" -- or worse, quietly sweeping a local
 * build instead and calling it prod -- is how a bug report ends up about a page
 * no user has ever seen.
 */
const url = process.argv[2] || process.env.UIBUG_URL || 'https://lexitrail.com';

const BLOCKED_MSG =
  'This is an egress-policy denial, not a site outage.\n' +
  'Report the blocked host to the user: the environment\'s network policy governs\n' +
  'it and cannot be worked around from here. Ask them to add the host under the\n' +
  'environment\'s network egress settings. Do NOT substitute a local build for the\n' +
  'live site without saying so -- see references/local-surrogate.md.';

(async () => {
  const t0 = Date.now();
  try {
    const res = await fetch(url, { method: 'GET', redirect: 'follow' });
    const ms = Date.now() - t0;

    // A blocking proxy answers with a real, well-formed HTTP 403 -- so status
    // alone cannot tell "the site refused us" from "our sandbox refused the
    // site", and those need opposite responses. The egress proxy labels its own
    // denials (`x-deny-reason`, and a body naming the allowlist), so check for
    // that before believing a 4xx is about the site.
    const denyReason = res.headers.get('x-deny-reason');
    const body = await res.text().catch(() => '');
    if (denyReason || /not in allowlist|egress|blocked by policy/i.test(body)) {
      console.log(`BLIND ${url} -> HTTP ${res.status} (${denyReason || 'policy denial'}) (${ms}ms)`);
      console.log(body.trim().slice(0, 300));
      console.log(BLOCKED_MSG);
      process.exit(2);
    }

    if (res.status >= 400) {
      console.log(`FAIL ${url} -> HTTP ${res.status} (${ms}ms)`);
      process.exit(1);
    }
    console.log(`PASS ${url} -> HTTP ${res.status} (${ms}ms)`);
    process.exit(0);
  } catch (err) {
    const msg = String((err && err.cause && err.cause.message) || err.message || err);
    console.log(`BLIND ${url} -> ${msg}`);
    if (/403|proxy|tunnel|CONNECT/i.test(msg)) console.log(BLOCKED_MSG);
    process.exit(2);
  }
})();
