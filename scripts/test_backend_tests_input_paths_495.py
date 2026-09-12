#!/usr/bin/env python3
"""lexitrail#495: the #445 rule applied to `backend-tests.yml`.

#445 established that a path-filtered CI job must list the paths of its INPUTS,
not just its own directory, and its AC3 said to check the same question of
`backend-tests.yml` **rather than assuming**. It was the same answer:

    backend/scripts/config.py   WORDSETS_CSV_PATH = '../terraform/csv/wordsets.csv'
                                WORDS_CSV_PATH    = '../terraform/csv/words.csv'

Neither was in the filter, so a change to either ran zero backend checks.

🔴 The filter widening is only half of it, and shipping it alone would have been
worse than leaving the hole. Nothing tested `load_word_data`, so `backend-tests`
would have fired on a CSV change, gone green, and asserted nothing about the
change that triggered it -- a check named for the defect, which stops the next
reader looking. `backend/tests/test_csv_inputs_495.py` is the coverage; this file
is the wiring. Coverage first, filter second.

Pins the PROPERTY, not the spelling (same philosophy as #445/#450): the paths are
DERIVED from `config.py`, so repointing the loader at a different file reds this
test rather than silently re-opening the hole.

Run: python3 -m pytest -q scripts/test_backend_tests_input_paths_495.py
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows" / "backend-tests.yml"
CONFIG = ROOT / "backend" / "scripts" / "config.py"


def _triggers():
    # `on` is the YAML 1.1 boolean True -- a plain d["on"] returns None and every
    # assertion below would then pass vacuously against an empty filter.
    d = yaml.safe_load(WF.read_text())
    on = d.get(True, d.get("on"))
    assert isinstance(on, dict), f"could not read the trigger block: {on!r}"
    return on


def _matches(path: str, pattern: str) -> bool:
    """GitHub path-filter semantics for the shapes this workflow uses.

    🔴 Refuses an unrecognised shape rather than returning False -- a matcher that
    silently says "no match" for a pattern it does not understand makes the
    negative controls below pass for the wrong reason.
    """
    if pattern.endswith("/**"):
        return path.startswith(pattern[: -len("**")])
    if "*" not in pattern:
        return path == pattern
    raise AssertionError(f"unhandled pattern shape: {pattern!r} -- extend the matcher")


def _derived_inputs() -> set[str]:
    """Repo-relative paths `backend/` reads from OUTSIDE backend/, from its source.

    `config.py` states them as paths relative to the backend working directory
    (`'../terraform/csv/words.csv'`), so the leading `../` is stripped to get a
    repo-relative path. Anything without `../` resolves inside `backend/` and is
    already covered by `backend/**`.
    """
    src = CONFIG.read_text()
    out = set()
    for value in re.findall(r"^[A-Z0-9_]+\s*=\s*['\"]([^'\"]+)['\"]", src, re.M):
        if not value.startswith("../"):
            continue
        out.add(value[len("../"):])
    assert out, (
        "issue-495: derived ZERO out-of-backend inputs from config.py -- the regex "
        "has drifted from the source, and an empty set makes every assertion below "
        "vacuous (a passing test that checks nothing)."
    )
    return out


def test_every_derived_input_is_in_both_path_filters_495():
    """AC3. A CSV-only change must run the backend suite -- on PR *and* on push."""
    on = _triggers()
    inputs = _derived_inputs()
    for event in ("pull_request", "push"):
        paths = on[event]["paths"]
        for rel in sorted(inputs):
            assert any(_matches(rel, p) for p in paths), (
                f"{event}: nothing in {paths} matches {rel!r}, which "
                f"backend/scripts/config.py READS -- the #445 hole, backend side"
            )


def test_the_two_concrete_csvs_are_covered_495():
    """The actual files, not only whatever the regex derived -- so a regex that
    drifts to deriving something else still reds here."""
    on = _triggers()
    for probe in ("terraform/csv/words.csv", "terraform/csv/wordsets.csv"):
        for event in ("pull_request", "push"):
            assert any(_matches(probe, p) for p in on[event]["paths"]), (
                f"{event}: {probe!r} is read by load_word_data and is not in the filter"
            )


def test_negative_control_unrelated_paths_still_do_NOT_run_495():
    """🔴 The fix must not degrade into "run everything always" -- that is how a
    filter gets deleted later for cost, taking the guard with it.

    Note `terraform/main.tf` and `terraform/csv/other.csv` are BOTH here on
    purpose: adding the two CSVs must not be done with a `terraform/**` or
    `terraform/csv/**` wildcard, which would pull in unrelated terraform churn.
    """
    on = _triggers()
    for probe in (
        "README.md",
        "ui/src/App.jsx",
        "terraform/main.tf",
        "terraform/csv/other.csv",
        "docs/spec/anything.md",
        "sentences/sentences-hsk1-6-v1.json",
    ):
        for event in ("pull_request", "push"):
            assert not any(_matches(probe, p) for p in on[event]["paths"]), (
                f"{event}: {probe!r} should NOT trigger the backend suite"
            )


def test_the_matcher_itself_discriminates_495():
    """A control on the control: the assertions above mean nothing if `_matches`
    always returns False, or always returns True."""
    assert _matches("backend/app/x.py", "backend/**") is True
    assert _matches("terraform/csv/words.csv", "terraform/csv/words.csv") is True
    assert _matches("terraform/csv/nope.csv", "terraform/csv/words.csv") is False
    assert _matches("ui/src/App.jsx", "backend/**") is False


def test_the_coverage_this_filter_buys_actually_exists_495():
    """🔴 The load-bearing pin, and the reason this issue was not a one-liner.

    Widening a filter ahead of coverage produces a job that fires and asserts
    nothing -- green, named for the defect, and worse than the open hole. If the
    CSV coverage is ever deleted, this filter entry stops meaning anything, and
    THAT is the moment someone needs to know."""
    cov = ROOT / "backend" / "tests" / "test_csv_inputs_495.py"
    assert cov.is_file(), (
        "issue-495: the backend CSV coverage is gone but the path filter still "
        "lists the CSVs. backend-tests now fires on a CSV change and covers none "
        "of the code that reads it -- restore the coverage or drop the filter "
        "entries, but do not leave the pair in this state."
    )
    src = cov.read_text()
    assert "load_word_data" in src, (
        "issue-495: the coverage file no longer calls load_word_data, so the "
        "filter entries buy nothing."
    )
