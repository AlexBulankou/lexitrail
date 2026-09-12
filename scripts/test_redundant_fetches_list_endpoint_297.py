"""issue-297: the wordset LIST endpoint is counted, and kept OUT of DATA_RE.

`redundant_fetches.py` is the harness for the redundant-fetch class and it
reported PASS while three identical `GET /wordsets` fired inside one forward
arrival. Not a bug in it — `DATA_RE` excludes the list endpoint **by
construction**, for a documented reason (it is refetched on every
back-navigation and counting it swamped the loader signal). But a duplicate a
detector never looks at is not a duplicate it cleared.

🔴 THESE ARMS EXIST BECAUSE THE FILE'S OWN `--self-test` IS NOT WIRED INTO CI.
`grep` over `.github/workflows/` and `cloudbuild*.yaml` finds no invocation, so
its arms run only when a human types the flag. Adding arms there and stopping
would have been a correct detector with no reader. These call the same pure
cores, from pytest, which CI does run.

Measured live on 2026-09-12 (12 views, 3 wordsets x 4 modes, nav=click):

    data requests: 7 | distinct: 7 | redundant: 0     <- DATA_RE: PASS
    wordset LIST endpoint: 15 fetch(es), 1 distinct   <- the excluded signal
"""
from __future__ import annotations

import pathlib
import sys

E2E = pathlib.Path(__file__).resolve().parents[1] / "e2e"
if str(E2E) not in sys.path:
    sys.path.insert(0, str(E2E))

from redundant_fetches import DATA_RE, redundant  # noqa: E402

# 🔴 `LIST_RE` / `list_endpoint` are imported INSIDE each arm, not here.
# They are the names this change ADDS, so a module-scope import makes a
# pre-fix tree fail at COLLECTION — one error for the whole file, which
# cannot be told apart from a broken test and hides whether each arm would
# genuinely have failed. Deferring gives four real assertion reds instead.

LIST = "https://api.lexitrail.com/wordsets"
LIST_Q = "https://api.lexitrail.com/wordsets?x=1"
WORDS = "https://api.lexitrail.com/wordsets/1/words"
USERWORDS = "https://api.lexitrail.com/userwords/query?user_id=a&wordset_id=1"
STATIC = "https://lexitrail.com/static/js/main.abc.js"


def test_it_counts_repeat_fetches_of_the_list_endpoint():
    from redundant_fetches import list_endpoint  # noqa: PLC0415 — see import note
    assert list_endpoint([LIST, LIST, LIST_Q]) == {"list_total": 3, "list_distinct": 2}


def test_it_ignores_the_per_wordset_payload_and_static_assets():
    """The negative arm. A matcher that catches everything IS the widening
    `DATA_RE`'s comment rejects, so this is the half that keeps them apart."""
    from redundant_fetches import list_endpoint  # noqa: PLC0415
    assert list_endpoint([WORDS, USERWORDS, STATIC]) == {
        "list_total": 0, "list_distinct": 0}


def test_the_two_matchers_do_not_OVERLAP():
    """🔴 The binding arm — separation, not detection.

    `/wordsets/1/words` must belong to DATA_RE alone. If LIST_RE also claimed
    it, the list count would inherit the loader traffic and the two signals
    would stop being readable independently, which is the whole reason #297
    asked for a separate counter rather than a wider one.
    """
    from redundant_fetches import LIST_RE  # noqa: PLC0415
    assert DATA_RE.search(WORDS) and not LIST_RE.search(WORDS)
    assert LIST_RE.search(LIST) and not DATA_RE.search(LIST)


def test_the_live_shape_that_motivated_this_reproduces():
    """DATA_RE says PASS on the exact trace where the list endpoint repeats.

    This is the issue in one assertion: the existing verdict is clean and
    silent about 3 identical list fetches. Without this arm the pair of
    counters looks like tidiness rather than a fix.
    """
    from redundant_fetches import list_endpoint  # noqa: PLC0415
    trace = [LIST, LIST, LIST, WORDS, USERWORDS]
    assert redundant(trace)["redundant"] == 0, "DATA_RE must still report clean"
    assert list_endpoint(trace)["list_total"] == 3, "and the list count must see it"


def test_the_pure_cores_import_WITHOUT_playwright():
    """🔴 The arm that would have caught this PR's own first version.

    CI installs `pytest pyyaml` only (`.github/workflows/repo-checks.yml`) and
    no workflow installs playwright — but a dev host has it, so importing
    `redundant_fetches` for its pure cores passed locally and went red in CI
    with `ModuleNotFoundError: No module named 'playwright'`. The module
    imported `lt_routes` (which imports playwright) at module scope; it is
    deferred into `measure()` now.

    This arm reproduces the CI shape rather than trusting it: it BLOCKS
    playwright, asserts the block actually took (a blocker that silently fails
    makes the arm vacuous — the first version of this control used the legacy
    `find_module` API that 3.12 ignores and reported itself broken), then
    imports the cores.
    """
    import importlib
    import sys as _sys

    class _Block:
        def find_spec(self, name, path=None, target=None):
            if name == "playwright" or name.startswith("playwright."):
                raise ImportError(f"No module named {name!r}")
            return None

    blocker = _Block()
    saved = {k: v for k, v in _sys.modules.items()
             if k == "playwright" or k.startswith("playwright.")
             or k in ("redundant_fetches", "lt_routes")}
    for k in saved:
        _sys.modules.pop(k, None)
    _sys.meta_path.insert(0, blocker)
    try:
        try:
            importlib.import_module("playwright")
            raise AssertionError(
                "CONTROL FAILED: playwright still importable, so this arm "
                "proves nothing about the CI environment")
        except ImportError:
            pass
        mod = importlib.import_module("redundant_fetches")
        assert mod.list_endpoint([LIST, LIST]) == {"list_total": 2, "list_distinct": 1}
    finally:
        _sys.meta_path.remove(blocker)
        for k in list(_sys.modules):
            if k in ("redundant_fetches", "lt_routes"):
                _sys.modules.pop(k, None)
        _sys.modules.update(saved)
