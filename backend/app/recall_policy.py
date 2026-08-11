"""Pure policy for the recall-update endpoint (#111).

Separate from `routes/userwords.py` for the same reason `cache_warm_policy.py`
is separate from `routes/wordsets.py`: that module imports Flask and the app
package, and the backend suite cannot even collect outside a provisioned
environment (it needs a live MySQL and `MYSQL_FILES_BUCKET`; the pre-existing
tests fail identically). lexitrail has no CI triggers (#77), so a decision left
in the route would ship with no executable test of any kind.

The rule here is one line of code and several lines of reason, which is
precisely the kind of thing that gets quietly inverted later by someone who has
only the line.
"""
from __future__ import annotations


def is_recall_event(data) -> bool:
    """Should this recall-endpoint call append a RecallHistory row? (#111)

    `toggleExclusion` reuses this endpoint and passes `recall=False`, because
    the signature demands a value. The row was written unconditionally, and
    `historyTiles.js` renders every row as `correct: Boolean(r.recall)` — so
    excluding a word painted a RED tile on its history, indistinguishable from
    a wrong answer, on the surface whose whole job is to show the learner how
    they are doing.

    DEFAULTS TO TRUE, and that direction is load-bearing. An older UI sends no
    flag at all, and a backend deployed ahead of the frontend must behave
    exactly as it does today — so the absent case degrades to the CURRENT bug,
    never to silently dropping real recalls. Getting this backwards would turn
    a cosmetic defect into data loss.

    WHY THE CALLER DECLARES IT rather than the server inferring it: the server
    could guess from "recall_state did not move", but a genuine recall on a
    word already floored at 0 and answered correctly leaves the state unchanged
    — identical to an inclusion toggle under that heuristic. It would silently
    drop real recalls, which is worse than the bug being fixed. Intent is not
    recoverable from the state diff, so it has to be sent.
    """
    if not isinstance(data, dict):
        return True
    return not bool(data.get("inclusion_only", False))
