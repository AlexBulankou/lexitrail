// issue-384: the SRS interval ladder exists twice, and this is what makes that safe.
//
// `srs.js` is the system of record for what "due" means. `backend/app/srs_ladder.py`
// mirrors ONLY the interval ladder, so the Today home's per-wordset due counts can be
// computed in SQL instead of by downloading ~5,600 words to the browser to render seven
// integers (10s+, then an outright failure — that is the bug this endpoint replaces).
//
// 🔴 THIS IS HALF OF THE GUARD. Its twin is `backend/tests/test_srs_ladder_parity_384.py`,
// and BOTH are required — see that file's docstring for the retraction that produced them.
//
// Short version: I first shipped only this half, arguing that `cloudbuild.yaml` builds an
// image without running pytest so a test there would never fire. The premise is true; the
// conclusion was false. `.github/workflows/backend-tests.yml` runs pytest on every PR — I
// checked one CI surface and generalised a true negative from it without enumerating the
// other. The real reason needs both halves, because the workflows are PATH-FILTERED:
//
//     edit ui/src/utils/srs.js        -> ui-tests runs,      backend-tests does NOT
//     edit backend/app/srs_ladder.py  -> backend-tests runs, ui-tests does NOT
//
// So a single parity test is blind to half the edits it exists to catch — and blind to
// the half MORE likely to drift silently, since nobody editing the Python ladder has any
// reason to touch `ui/`. This file covers the JS-side edit; its twin covers the other.
//
// Same shape and same reason as `designTokens.test.js`, which pins the two copies of the
// token layer declaration-for-declaration.
import fs from 'fs';
import path from 'path';

import { srsIntervalMs, MASTERY_FLOOR } from './srs';

const DAY_MS = 24 * 60 * 60 * 1000;

const PY = fs.readFileSync(
  path.resolve(__dirname, '../../../backend/app/srs_ladder.py'),
  'utf8'
);

// Parse the two literal arrays out of the Python. Deliberately a parse of the SOURCE
// rather than a hand-copied expectation: a hand-copied number is a THIRD copy, and it
// would drift in exactly the way this file exists to catch.
const pyList = (name) => {
  // Match to the LAST `]` on the line, not the first: GRADUATED_DAYS' value
  // contains a nested `INTERVAL_DAYS[0]`, and a lazy `[^\\]]*` stops inside it.
  // My first version did exactly that and produced NaN rungs — it went red rather
  // than silently agreeing, which is the only reason the parser bug was visible.
  const m = PY.match(new RegExp(`^${name}\\s*=\\s*\\[(.*)\\]`, 'm'));
  if (!m) throw new Error(`srsLadderParity: could not find ${name} in srs_ladder.py`);
  return m[1]
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)
    .map((x) => {
      // GRADUATED_DAYS' first rung is written as `INTERVAL_DAYS[0]`, by derivation
      // rather than as a literal, so that changing the weekly interval cannot leave
      // the graduation ladder claiming it still starts at 7. Resolve that reference
      // instead of failing on it — rejecting it would push the Python toward a
      // literal, which is the very coupling it is avoiding.
      const ref = x.match(/^INTERVAL_DAYS\[(\d+)\]$/);
      if (ref) return pyList('INTERVAL_DAYS')[Number(ref[1])];
      return Number(x);
    });
};

describe('the SRS ladder is identical on both sides', () => {
  test('INTERVAL_DAYS matches, rung for rung', () => {
    const py = pyList('INTERVAL_DAYS');
    // Read the JS side through its PUBLIC function rather than the private array:
    // what has to agree is the interval a state RESOLVES to, and testing the array
    // would pass while an index or a clamp diverged.
    py.forEach((days, state) => {
      expect(srsIntervalMs(state)).toBe(days * DAY_MS);
    });
  });

  test('GRADUATED_DAYS matches, rung for rung', () => {
    const py = pyList('GRADUATED_DAYS');
    py.forEach((days, i) => {
      expect(srsIntervalMs(-i)).toBe(days * DAY_MS);
    });
  });

  test('both sides saturate at the same place', () => {
    const learn = pyList('INTERVAL_DAYS');
    const grad = pyList('GRADUATED_DAYS');
    // Past the end of each ladder the interval must stop moving. A divergence here
    // is the subtle one: the ladders could match rung for rung while one side kept
    // indexing past the clamp and the other did not.
    expect(srsIntervalMs(learn.length + 50)).toBe(learn[learn.length - 1] * DAY_MS);
    expect(srsIntervalMs(-(grad.length + 50))).toBe(grad[grad.length - 1] * DAY_MS);
    expect(MASTERY_FLOOR).toBe(-(grad.length - 1));
  });

  test('the graduation ladder starts where the learning ladder does', () => {
    // Pinned because the Python writes it as a REFERENCE and a future editor could
    // "simplify" it to a literal 7 — after which changing the weekly interval would
    // silently leave the graduation ladder behind.
    expect(pyList('GRADUATED_DAYS')[0]).toBe(pyList('INTERVAL_DAYS')[0]);
    expect(PY).toMatch(/GRADUATED_DAYS\s*=\s*\[INTERVAL_DAYS\[0\]/);
  });
});
