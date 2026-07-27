/**
 * Click-path verifier for the /go/* short links (lexitrail#64).
 *
 * The issue's own framing is the reason this exists: "a 200 from a SPA route is
 * exactly the kind of green signal that means nothing". Lexitrail's production
 * server rewrites `**` to `/index.html`, so EVERY path returns 200 — including
 * paths that render the 404 component. A status-code assertion therefore passes
 * on a completely broken link, which is how `/hsk2` came to have an acceptance
 * criterion ("assert /hsk2 resolves 200") that passes today on a dead page.
 *
 * So this navigates in a real browser from a clean profile and asserts the
 * RENDERED OUTCOME: where you landed, that the UTM survived, and that what came
 * back is the real page rather than the 404 shell.
 *
 * It also checks KNOWN-BROKEN paths on every run and fails if they come back
 * looking healthy. A verifier that only ever exercises the working case is
 * indistinguishable from one that has silently stopped testing anything — and
 * that is the exact defect class this repo has been chasing all week.
 *
 * Usage:
 *   npm install
 *   npm run verify
 *   npm run verify -- --base http://localhost:3000    # against a local `serve -s build`
 */
import { chromium } from "playwright";

const DEFAULT_BASE = "https://lexitrail.com";

/**
 * Routes that MUST redirect. Source of truth is ui/public/serve.json; keep in
 * sync deliberately rather than parsing it, so that deleting a redirect from
 * serve.json makes this file fail rather than silently shrink its own scope.
 */
const MUST_REDIRECT = [
  { path: "/go/ig-hsk", utm_source: "instagram", utm_campaign: "lt_hsk" },
  { path: "/go/ig-wod", utm_source: "instagram", utm_campaign: "lt_wod" },
  { path: "/go/ig-streak", utm_source: "instagram", utm_campaign: "lt_streak" },
  { path: "/go/x-hsk", utm_source: "x", utm_campaign: "lt_hsk" },
  { path: "/go/x-wod", utm_source: "x", utm_campaign: "lt_wod" },
  { path: "/go/x-streak", utm_source: "x", utm_campaign: "lt_streak" },

  // Bio-link paths. These are the ONLY tappable click path on Instagram and
  // TikTok, because neither platform linkifies a caption URL — so a 404 here is
  // not a cosmetic gap, it is every bio click on those channels becoming a lost,
  // unattributed lead. Mandated by SUAM-channel-provisioning.md and reported
  // 404ing in decipher#2494 finding #1; confirmed 404ing in production before
  // this change added them to serve.json.
  //
  // utm_campaign=bio rather than a per-post value: a profile bio is one link for
  // the whole profile, so per-campaign granularity is not physically available
  // on this surface. Per-platform is the most we can attribute.
  { path: "/go/ig", utm_source: "instagram", utm_campaign: "bio" },
  { path: "/go/tiktok", utm_source: "tiktok", utm_campaign: "bio" },
  { path: "/go/tt", utm_source: "tiktok", utm_campaign: "bio" },
  { path: "/go/pinterest", utm_source: "pinterest", utm_campaign: "bio" },
  { path: "/go/yt", utm_source: "youtube", utm_campaign: "bio" },
];

/**
 * Paths that MUST look broken. These are the verifier's positive controls: if
 * one of them starts reporting healthy, the check has lost its ability to tell
 * the difference and every green above becomes meaningless.
 *
 * `/hsk2` is real — it is referenced as a destination but has never existed as
 * an SPA route, and it returns 200 while rendering the 404 component.
 */
const MUST_BE_BROKEN = ["/hsk2", "/go/this-route-does-not-exist"];

/** Body text shorter than this means we got a shell, not a page. */
const MIN_REAL_CONTENT_CHARS = 300;

async function probe(page, base, path) {
  const hops = [];
  const onResponse = (res) => {
    if (res.request().isNavigationRequest()) hops.push({ status: res.status(), url: res.url() });
  };
  page.on("response", onResponse);
  let navError = null;
  try {
    await page.goto(base + path, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(2500); // the SPA has to hydrate before body text means anything
  } catch (e) {
    navError = e.message;
  }
  page.off("response", onResponse);

  const finalUrl = page.url();
  const bodyText = (await page.evaluate(() => document.body?.innerText ?? "").catch(() => "")).trim();
  const flat = bodyText.replace(/\s+/g, " ");
  return {
    path,
    finalUrl,
    hops,
    navError,
    chars: flat.length,
    // The 404 component renders this copy. Matching the rendered text is the
    // whole point — the HTTP status cannot distinguish these cases.
    looksNotFound: /couldn.t find that page|\b404\b|not found/i.test(flat),
    search: (() => { try { return new URL(finalUrl).search; } catch { return ""; } })(),
  };
}

function checkRedirect(r, expect) {
  const problems = [];
  if (r.navError) problems.push(`navigation failed: ${r.navError}`);
  if (r.looksNotFound) problems.push(`landed on the 404 component`);
  if (r.chars < MIN_REAL_CONTENT_CHARS) {
    problems.push(`only ${r.chars} chars rendered (< ${MIN_REAL_CONTENT_CHARS}) — a shell, not a page`);
  }
  const redirected = r.hops.some((h) => h.status >= 300 && h.status < 400);
  if (!redirected) {
    problems.push(`no 3xx hop — served by the SPA rewrite instead of redirecting`);
  }
  if (!r.search.includes(`utm_source=${expect.utm_source}`)) {
    problems.push(`utm_source=${expect.utm_source} missing from final URL (${r.search || "no query"})`);
  }
  if (!r.search.includes(`utm_campaign=${expect.utm_campaign}`)) {
    problems.push(`utm_campaign=${expect.utm_campaign} missing from final URL`);
  }
  return problems;
}

function checkBroken(r) {
  // Inverted: we WANT this to look broken. If it doesn't, the verifier is blind.
  const healthy = !r.looksNotFound && r.chars >= MIN_REAL_CONTENT_CHARS;
  return healthy
    ? [`expected this path to render the 404 component, but it rendered ${r.chars} chars of real ` +
       `content. Three causes, in the order worth checking:\n` +
       `           (1) --base points at something that is not the production app. A stale ` +
       `ui/build (it is gitignored, so it can be arbitrarily old) renders whatever it was built ` +
       `from and will not produce the 404 component. Rebuild before reading a local run.\n` +
       `           (2) the route now genuinely exists — update MUST_BE_BROKEN.\n` +
       `           (3) this verifier can no longer tell a working link from a dead one, in which ` +
       `case every PASS above is worthless.`]
    : [];
}

async function main() {
  const argv = process.argv.slice(2);
  const baseIdx = argv.indexOf("--base");
  const base = baseIdx >= 0 ? argv[baseIdx + 1].replace(/\/$/, "") : DEFAULT_BASE;

  const launchOpts = {};
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE) {
    launchOpts.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  }
  const browser = await chromium.launch(launchOpts);
  // Fresh context = a cold visitor with no session, which is what arrives from a feed.
  const ctx = await browser.newContext();
  const page = await ctx.newPage();

  let failures = 0;
  console.log(`Click-path verification against ${base}\n`);

  console.log("REDIRECTS THAT MUST WORK");
  for (const expect of MUST_REDIRECT) {
    const r = await probe(page, base, expect.path);
    const problems = checkRedirect(r, expect);
    const hopStr = r.hops.map((h) => h.status).join("->") || "none";
    if (problems.length) {
      failures++;
      console.log(`  FAIL ${expect.path}  [${hopStr}] ${r.chars} chars`);
      for (const p of problems) console.log(`         ${p}`);
    } else {
      console.log(`  ok   ${expect.path}  [${hopStr}] -> ${r.finalUrl}`);
    }
  }

  console.log("\nCONTROLS — these MUST look broken, or the check above proves nothing");
  for (const path of MUST_BE_BROKEN) {
    const r = await probe(page, base, path);
    const problems = checkBroken(r);
    const status = r.hops[0]?.status ?? "?";
    if (problems.length) {
      failures++;
      console.log(`  FAIL ${path}  [HTTP ${status}] ${r.chars} chars`);
      for (const p of problems) console.log(`         ${p}`);
    } else {
      console.log(`  ok   ${path}  [HTTP ${status}] renders 404 as expected ` +
                  `(${r.chars} chars) — note the 200: status alone would have called this a pass`);
    }
  }

  await browser.close();

  if (failures) {
    console.log(`\n${failures} failure(s).`);
    process.exit(1);
  }
  console.log(`\nAll ${MUST_REDIRECT.length} redirects land on the destination with UTM intact, ` +
              `and both controls still read as broken.`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
