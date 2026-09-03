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


#: The provenance values a client may declare (#109 / RD-6 slice A).
#:
#: An allowlist, not free text: the value lands in a column and comes from the
#: request body, so an unrecognised string must not be stored. Anything outside
#: this set is treated exactly like an absent flag — UNKNOWN — rather than
#: rejected with a 400, because a recall the learner actually made must never be
#: lost to a client sending a value we have not heard of yet.
RECALL_PROVENANCE_VALUES = frozenset({"single", "bulk"})


def recall_provenance(data):
    """How was this recall produced? -> "single" | "bulk" | None (#109)

    None means UNKNOWN PROVENANCE and is the honest default, not a fallback to
    "single". Three callers produce it:

      * an older UI talking to a newer backend, which sends no flag at all;
      * a client sending a value outside the allowlist;
      * every one of the ~94k rows written before this column existed.

    Collapsing any of those into "single" would assert that a row was earned
    when nothing recorded that it was — which is the exact failure #109 exists
    to end. A consumer must therefore be able to distinguish three states, and
    that is why the column is nullable rather than a boolean.

    WHY THE CALLER DECLARES IT rather than the server inferring it: the bulk
    path issues N independent PUTs whose bodies are byte-identical to a single
    card tap, so there is nothing in the request to infer from. The only
    server-side signal would be a same-second cluster, and a fast learner
    answering a small set produces that shape too — so the heuristic would
    re-label real recalls as bulk, on the data this feature exists to make
    trustworthy. Same argument as `is_recall_event` above, on the sister field.
    """
    if not isinstance(data, dict):
        return None
    value = data.get("provenance")
    return value if value in RECALL_PROVENANCE_VALUES else None
