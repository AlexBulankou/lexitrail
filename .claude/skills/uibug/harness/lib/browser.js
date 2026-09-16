'use strict';
/**
 * Resolve a chromium executable.
 *
 * Playwright pins an exact browser revision per release and refuses to launch
 * anything else ("Please run npx playwright install"). Sandboxes like this one
 * ship a pre-installed browser at PLAYWRIGHT_BROWSERS_PATH whose revision tracks
 * the image, not our package.json -- so the two drift apart on any image bump or
 * any `npm update`, and the harness dies with a message that sounds like a
 * missing install when nothing is missing at all.
 *
 * Downloading the pinned revision is the obvious fix and the wrong one here:
 * it is ~150MB through an egress proxy, on every fresh container, to obtain a
 * browser we already have. So: if the pinned revision is present, use it (let
 * Playwright do its normal thing); otherwise fall back to whatever chromium IS
 * installed and say so out loud.
 *
 * The fallback is safe for what this harness measures -- layout, box geometry
 * and computed style are Chromium behaviours, not Playwright-protocol ones, and
 * a revision or two of drift does not move them. It is NOT safe to stay silent
 * about, because a screenshot from an unexpected browser build is exactly the
 * kind of thing that makes a bug report irreproducible. Hence the console note.
 */
const fs = require('fs');
const path = require('path');

const ROOT = process.env.PLAYWRIGHT_BROWSERS_PATH || '/opt/pw-browsers';

/** Every `chrome`/`headless_shell` binary under a browsers root, newest revision first. */
function discover() {
  if (!fs.existsSync(ROOT)) return [];
  const found = [];
  for (const dir of fs.readdirSync(ROOT)) {
    if (!/^chromium(-|_)/.test(dir) && dir !== 'chromium') continue;
    const rev = parseInt((dir.match(/(\d+)$/) || [])[1] || '0', 10);
    for (const rel of [
      'chrome-linux/chrome',
      'chrome-linux/headless_shell',
      'chrome-mac/Chromium.app/Contents/MacOS/Chromium',
    ]) {
      const p = path.join(ROOT, dir, rel);
      if (fs.existsSync(p)) found.push({ path: p, revision: rev, dir });
    }
  }
  return found.sort((a, b) => b.revision - a.revision);
}

/** The revision this Playwright build insists on, or null if we cannot tell. */
function pinnedRevision() {
  try {
    // Not `require.resolve('playwright-core/browsers.json')`: playwright-core's
    // package.json "exports" map does not list browsers.json, so that throws
    // ERR_PACKAGE_PATH_NOT_EXPORTED. Resolve the package entry and walk up.
    const pkgDir = path.dirname(require.resolve('playwright-core'));
    const candidates = [
      path.join(pkgDir, 'browsers.json'),
      path.join(pkgDir, '..', 'browsers.json'),
      path.join(pkgDir, '..', '..', 'browsers.json'),
    ];
    const hit = candidates.find((c) => fs.existsSync(c));
    if (!hit) return null;
    const bj = JSON.parse(fs.readFileSync(hit, 'utf8'));
    const c = bj.browsers.find((b) => b.name === 'chromium');
    return c ? parseInt(c.revision, 10) : null;
  } catch (_) {
    return null;
  }
}

/**
 * @returns {{executablePath?: string, note: string}} -- spread into `launchOptions`.
 * Empty when the pinned revision is present, so the default path stays default.
 */
function resolveChromium() {
  const pinned = pinnedRevision();
  const available = discover();

  if (pinned && available.some((a) => a.revision === pinned)) {
    return { note: `chromium ${pinned} (pinned revision present)` };
  }
  if (available.length === 0) {
    return { note: `no chromium found under ${ROOT}; Playwright will use its own` };
  }

  const pick = available[0];
  return {
    executablePath: pick.path,
    note:
      `chromium ${pick.revision} from ${ROOT} (Playwright pins ${pinned ?? '?'}; ` +
      `using the installed build instead of downloading ~150MB)`,
  };
}

module.exports = { resolveChromium, discover, pinnedRevision, ROOT };
