#!/usr/bin/env python3
"""lexitrail#450: the repo-root checkers must stay RUN, and stay run by a GLOB.

Nine test files (218 tests) were invoked by nothing until `repo-checks.yml`
landed — including `scripts/build_budget/`'s own, i.e. the quota gate that
decides whether a build may run had 44 tests that never executed. One of the
nine was already red and had been for an unknown span, because nothing ran it.

This pins the two properties that FIX it rather than the fix's spelling:

  1. the file list is DERIVED, not enumerated — a hardcoded list is exactly how
     the nine were stranded, and decipher#3411 is the same defect in that repo,
     where a comment asking each author to add a line was not followed by the
     very next file the SAME issue added;
  2. the workflow has NO `paths:` filter — #445 is the sibling defect (a check
     scoped to its consumer's directory, blind to the input that breaks it),
     and these nine have cross-cutting inputs by nature.

🔴 It also self-enrolls: this file lives under `scripts/` so the glob picks it
up. That is deliberate. Anywhere the glob does not reach would reproduce the
defect it is about.

Run: python3 -m pytest -q scripts/test_repo_checks_workflow_450.py
"""
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows" / "repo-checks.yml"


def _step():
    d = yaml.safe_load(WF.read_text())
    steps = d["jobs"]["checkers"]["steps"]
    matching = [s for s in steps if s.get("name") == "repo-root checkers"]
    assert matching, "the 'repo-root checkers' step is gone — nothing runs the nine"
    return d, matching[0]["run"]


def test_the_workflow_exists_at_all():
    assert WF.is_file(), f"{WF} is missing — the nine are stranded again"


def test_the_list_is_DERIVED_not_enumerated():
    """A hardcoded list is how this happened. If someone converts the glob back
    to named files, this reds — which is the whole point of the fix."""
    _, run = _step()
    assert "find scripts tools" in run, "the derivation is gone"
    # A named .py in the runner line means someone started listing them again.
    body = run.split("\n")
    named = [l for l in body
             if "test_" in l and ".py" in l and not l.lstrip().startswith("#")
             and "find " not in l and "'test_*.py'" not in l]
    assert not named, f"looks enumerated rather than derived: {named}"


def test_there_is_NO_paths_filter():
    """#445: a path filter scoped to the consumer's directory is blind to the
    input that breaks the consumer, and renders as 'no checks to run' — which
    on the PR surface is indistinguishable from 'checks passed'."""
    d, _ = _step()
    on = d[True] if True in d else d["on"]   # PyYAML parses bare `on:` as True
    for event in ("pull_request", "push"):
        cfg = on.get(event) or {}
        assert "paths" in cfg is False or "paths" not in cfg, (
            f"{event} gained a `paths:` filter — see #445 before adding one")


def test_the_count_guard_can_PRINT_and_is_not_the_echo_0_trap():
    """decipher#3389: `grep -c` exits 1 on zero while printing '0', so under
    `-eo pipefail` the assignment dies before the refusal can speak. `|| true`
    keeps the '0'. `|| echo 0` CONCATENATES to '0\\n0' and leaves the step
    exiting 0 — the vacuous green the guard exists to refuse."""
    _, run = _step()
    # 🔴 Strip comments FIRST. The step's comment block EXPLAINS the `|| echo 0`
    # trap, so a whole-body `in` check matches the MENTION and not a use — this
    # assertion failed on its own first run for exactly that reason, in a test
    # about a construct whose comment names it. Same class as the defect it
    # guards: a matcher sees characters, not intent.
    code = "\n".join(l for l in run.split("\n") if not l.lstrip().startswith("#"))
    assert "grep -c . || true" in code, "the count guard lost its `|| true`"
    assert "|| echo 0" not in code, "the `|| echo 0` trap — this makes the step exit 0 on an empty derivation"
    assert "refusing vacuous-green" in code, "the guard no longer explains itself"


def test_e_is_NOT_dropped_from_the_runner():
    """`-e` is what fails the step when pytest exits non-zero. Dropping it to
    quieten something would make every failing checker pass silently."""
    _, run = _step()
    assert "set -euo pipefail" in run, "`-e` was dropped — failing checkers would go green"


def test_the_derivation_is_NOT_VACUOUS_on_this_checkout():
    """Non-vacuity, and it is the arm that matters: every assertion above is
    satisfied by a glob that matches nothing. Run the real derivation."""
    out = subprocess.run(
        ["bash", "-c", "find scripts tools -name 'test_*.py' -type f | sort"],
        capture_output=True, text=True, cwd=ROOT,
    )
    files = [l for l in out.stdout.split("\n") if l.strip()]
    assert len(files) >= 5, f"the derivation found {len(files)} files — expected the repo-root checkers"
    assert any("build_budget" in f for f in files), (
        "build_budget's tests are not in the derived set — they are the ones "
        "that guard whether a build may run at all")


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", "-q", __file__]))
