#!/usr/bin/env node
'use strict';
/**
 * CLI front door: `node run.js --url <url> --env <desktop|mobile|both> --out <dir>`
 *
 * A thin wrapper over `playwright test` so the skill has one documented entry
 * point and the config stays declarative. It also does the two things a bare
 * `playwright test` will not: refuse to start against an unreachable target,
 * and fold the per-route ndjson into one summary a human can read.
 */
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const argv = process.argv.slice(2);
const arg = (name, dflt) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : dflt;
};
const has = (name) => argv.includes(`--${name}`);

// Surrogate mode: stub api.lexitrail.com so a local build renders real screens
// instead of its error state. Opt-in, and stamped into findings.json so no
// downstream reader can mistake a mocked measurement for a live one.
const mockApi = has('mock-api');

const url = arg('url', process.env.UIBUG_URL || 'https://lexitrail.com');
const env = arg('env', 'both').toLowerCase();
const out = path.resolve(arg('out', path.join(__dirname, '.runs', new Date().toISOString().slice(0, 10))));

if (!['desktop', 'mobile', 'both'].includes(env)) {
  console.error(`[uibug] --env must be desktop|mobile|both, got "${env}"`);
  process.exit(64);
}

fs.mkdirSync(out, { recursive: true });
fs.rmSync(path.join(out, 'findings.ndjson'), { force: true });

// Preflight unless explicitly skipped. Skipping is allowed (a local surrogate on
// a port that 404s at `/` is legitimate) but must be a deliberate keystroke.
if (!has('skip-reach')) {
  const r = spawnSync(process.execPath, [path.join(__dirname, 'reach.js'), url], { stdio: 'inherit' });
  if (r.status === 2) {
    console.error('[uibug] target unreachable -- aborting before the sweep (exit 2 = BLIND)');
    process.exit(2);
  }
}

console.log(`[uibug] sweeping ${url}  env=${env}  out=${out}`);

const res = spawnSync(
  'npx',
  ['playwright', 'test', '--config', path.join(__dirname, 'playwright.config.js')],
  {
    stdio: 'inherit',
    cwd: __dirname,
    env: { ...process.env, UIBUG_URL: url, UIBUG_ENV: env, UIBUG_OUT: out,
           UIBUG_API_MOCK: mockApi ? '1' : '',
           PLAYWRIGHT_BROWSERS_PATH: process.env.PLAYWRIGHT_BROWSERS_PATH || '/opt/pw-browsers' },
  }
);

// --- summarize ------------------------------------------------------------
const ndjson = path.join(out, 'findings.ndjson');
if (!fs.existsSync(ndjson)) {
  console.error('[uibug] no records written -- the sweep never measured anything (BLIND)');
  process.exit(2);
}

const rows = fs.readFileSync(ndjson, 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse);
const ok = rows.filter((r) => r.status === 'ok');
const blind = rows.filter((r) => r.status !== 'ok');
const byKind = {};
for (const r of ok) for (const f of r.findings) byKind[f.kind] = (byKind[f.kind] || 0) + 1;

const summary = {
  url, env, out,
  surrogate: mockApi || !/^https:\/\/lexitrail\.com/.test(url),
  apiMocked: mockApi,
  routesMeasured: ok.length,
  routesBlind: blind.length,
  blind: blind.map((r) => ({ viewport: r.viewport, route: r.route, reason: r.reason })),
  findingsByKind: byKind,
  totalFindings: Object.values(byKind).reduce((a, b) => a + b, 0),
  analyticsBlocked: Math.max(0, ...ok.map((r) => r.analyticsBlocked || 0)),
  rows,
};
fs.writeFileSync(path.join(out, 'findings.json'), JSON.stringify(summary, null, 2));

console.log('\n[uibug] ---- summary ----');
console.log(`  measured : ${ok.length} route/viewport pairs`);
console.log(`  BLIND    : ${blind.length}`);
for (const b of summary.blind) console.log(`             - [${b.viewport}] ${b.route}: ${b.reason}`);
console.log(`  findings : ${summary.totalFindings} ${JSON.stringify(byKind)}`);
console.log(`  analytics beacons blocked: ${summary.analyticsBlocked} (completed: 0)`);
console.log(`  artifacts: ${out}`);
if (summary.surrogate) {
  console.log('  ⚠ SURROGATE RUN -- these are measurements of this tree, not of the');
  console.log('    live site. Every PR resting on them must say so.');
}

if (ok.length === 0) {
  console.error('[uibug] measured nothing -- BLIND');
  process.exit(2);
}
process.exit(res.status === 0 ? 0 : 1);
