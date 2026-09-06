"""The spaced-repetition interval ladder — the SERVER's copy.

## Why a second copy exists at all

`ui/src/utils/srs.js` is the system of record for what "due" means, and it stays
that way: the practice loop, the session binding and the wordset picker all read
it, and a word's due-ness must be decided in exactly one place or the headline
count and the session it opens can disagree — the failure `dueByWordset`'s own
comments were written to prevent.

This module exists only so the DUE COUNT can be computed in SQL. The Today home
needs one number per wordset; computing it in the browser meant downloading
every word in every set (~5,600 rows plus recall history across 7 concurrent
requests) to display seven integers. That is what made the screen take 10s and
then fail outright.

## Why this is not the drift hazard it looks like

A second definition of "due" would normally be exactly the mistake this repo
keeps warning about. Three things make it safe here, and if any of them stops
being true this module should be deleted rather than maintained:

1. `test_srs_ladder_parity.py` reads the ACTUAL arrays out of `srs.js` and
   asserts this ladder equals them, rung for rung. A change to either side that
   is not mirrored reds — the same shape as `designTokens.test.js` pinning the
   two copies of the token layer.
2. The ladder is the ONLY thing duplicated. The rest of `isDue` — never
   practised means due, an unparseable timestamp means due — is expressed in the
   SQL rather than re-implemented in prose.
3. It is data, not logic: two short lists and an index clamp.
"""

from __future__ import annotations

# state >= 0 -- the learning ladder. Index is min(state, len-1), so a word
# answered wrong repeatedly saturates at 0 days, i.e. always due.
INTERVAL_DAYS = [7, 3, 1, 0, 0]

# state < 0 -- the graduation ladder (issue-188). Index is min(-state, len-1).
# The first rung is INTERVAL_DAYS[0] BY DERIVATION, not by coincidence: srs.js
# builds it as `[INTERVAL_DAYS[0], 14, 30, 90]` so that changing the weekly
# interval cannot leave this array claiming the ladder still starts at 7.
GRADUATED_DAYS = [INTERVAL_DAYS[0], 14, 30, 90]


def interval_days(recall_state: int | None) -> int:
    """Days a word rests at `recall_state`. Mirrors `srsIntervalMs` in srs.js."""
    state = int(recall_state or 0)
    if state < 0:
        return GRADUATED_DAYS[min(-state, len(GRADUATED_DAYS) - 1)]
    return INTERVAL_DAYS[min(state, len(INTERVAL_DAYS) - 1)]


def distinct_state_intervals() -> list[tuple[int, int]]:
    """`(state, days)` for every state whose interval differs from its neighbour.

    The ladder saturates at both ends, so a handful of CASE arms covers every
    integer state a row can hold — including states beyond the clamp, which the
    caller must map with a catch-all rather than enumerating to infinity.
    """
    lo = -(len(GRADUATED_DAYS) - 1)
    hi = len(INTERVAL_DAYS) - 1
    return [(s, interval_days(s)) for s in range(lo, hi + 1)]
