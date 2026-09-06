"""issue-384: the SRS ladder exists twice — this is the BACKEND half of the guard.

`ui/src/utils/srs.js` is the system of record for what "due" means.
`app/srs_ladder.py` mirrors only the interval LADDER, so the Today home's due
counts can be computed in SQL instead of by downloading ~5,600 words to the
browser to render seven integers.

## 🔴 WHY THERE ARE TWO PARITY TESTS AND NOT ONE

I first wrote only the jest half (`ui/src/utils/srsLadderParity.test.js`) and
justified it with a claim that was FALSE: that `cloudbuild.yaml` builds an image
without running pytest, so a test here would never fire. The premise is true and
the conclusion is not — `.github/workflows/backend-tests.yml` runs
`python3 -m pytest tests/` on every PR. I checked ONE ci surface, found a true
negative there, and generalised it to "no CI runs this" without enumerating the
other. It was published in four places before the green `pytest` check on the PR
contradicted it.

Enumerating both workflows shows the real reason, and it is a better one — the
two are PATH-FILTERED and the coupling can be broken from either side:

    edit ui/src/utils/srs.js      -> ui-tests runs      backend-tests does NOT
    edit backend/app/srs_ladder.py -> backend-tests runs  ui-tests does NOT

So a single parity test is blind to exactly half the edits it exists to catch —
and blind to the half MORE likely to drift silently, since someone editing the
Python ladder has no reason to touch `ui/`. One test per side is not redundancy;
it is the only arrangement where both directions are covered.
"""
import re
import unittest
from pathlib import Path

from app.srs_ladder import INTERVAL_DAYS, GRADUATED_DAYS, interval_days

SRS_JS = Path(__file__).resolve().parents[2] / 'ui' / 'src' / 'utils' / 'srs.js'


def _js_list(name: str) -> list[int]:
    """Pull a literal array out of srs.js.

    Parses the SOURCE rather than comparing against a hand-copied expectation: a
    hand-copied number would be a THIRD copy, drifting in exactly the way this
    file exists to catch.
    """
    src = SRS_JS.read_text()
    # Match to the LAST `]` on the line: GRADUATED_DAYS' value contains a nested
    # `INTERVAL_DAYS[0]`, and a non-greedy `[^\]]*` stops inside it.
    m = re.search(rf'^const {name}\s*=\s*\[(.*)\]', src, re.M)
    if not m:
        raise AssertionError(f'could not find {name} in {SRS_JS}')
    out = []
    for part in m.group(1).split(','):
        part = part.strip()
        if not part:
            continue
        ref = re.fullmatch(r'INTERVAL_DAYS\[(\d+)\]', part)
        # Resolve the reference rather than rejecting it. srs.js writes the
        # graduation ladder's first rung AS a reference precisely so that
        # changing the weekly interval cannot leave it claiming 7; demanding a
        # literal here would push the JS toward the coupling it is avoiding.
        out.append(_js_list('INTERVAL_DAYS')[int(ref.group(1))] if ref else int(part))
    return out


class SrsLadderParityTests(unittest.TestCase):

    def test_the_learning_ladder_matches(self):
        self.assertEqual(INTERVAL_DAYS, _js_list('INTERVAL_DAYS'))

    def test_the_graduation_ladder_matches(self):
        self.assertEqual(GRADUATED_DAYS, _js_list('GRADUATED_DAYS'))

    def test_the_graduation_ladder_starts_where_the_learning_one_does(self):
        """Pinned because srs.js writes it as a REFERENCE and a future editor
        could 'simplify' it to a literal 7 — after which changing the weekly
        interval would silently leave the graduation ladder behind."""
        js = SRS_JS.read_text()
        self.assertRegex(js, r'GRADUATED_DAYS\s*=\s*\[INTERVAL_DAYS\[0\]')
        self.assertEqual(GRADUATED_DAYS[0], INTERVAL_DAYS[0])

    def test_both_sides_saturate_at_the_same_place(self):
        """The subtle divergence: the ladders could match rung for rung while
        one side kept indexing past the clamp and the other did not."""
        self.assertEqual(interval_days(len(INTERVAL_DAYS) + 50), INTERVAL_DAYS[-1])
        self.assertEqual(interval_days(-(len(GRADUATED_DAYS) + 50)), GRADUATED_DAYS[-1])


if __name__ == '__main__':
    unittest.main()
