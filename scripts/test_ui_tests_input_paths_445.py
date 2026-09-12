#!/usr/bin/env python3
"""lexitrail#445: a path-filtered job must list the paths of its INPUTS.

`ui-tests.yml` was filtered to `ui/**`. The test that guards committed-page ↔
sentence-bank consistency lives there, but its input does not:
`generate-word-pages.js` resolves `path.resolve(UI, '..', 'sentences')`.

So #443 — a bank-only PR — ran ZERO checks and broke main, and the reviewer saw
a PR with no failing checks. 🔴 The failure direction is the reassuring one: zero
check-runs renders as "nothing to run", not as "unverified", and on the PR
surface that is indistinguishable from green. Sister to ensemble#9082's
`skipping`-vs-`pass`.

This pins the PROPERTY, not the spelling (same philosophy as #450): the input
directory is DERIVED from the generator source, so pointing the generator at a
different directory reds this test rather than silently re-opening the hole.

Run: python3 -m pytest -q scripts/test_ui_tests_input_paths_445.py
"""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows" / "ui-tests.yml"
GEN = ROOT / "ui" / "scripts" / "generate-word-pages.js"

# `on` is the YAML 1.1 boolean True — a plain d["on"] returns None and every
# assertion below would then pass vacuously against an empty filter.
def _triggers():
    d = yaml.safe_load(WF.read_text())
    on = d.get(True, d.get("on"))
    assert isinstance(on, dict), f"could not read the trigger block: {on!r}"
    return on


def _matches(path: str, pattern: str) -> bool:
    """GitHub path-filter semantics for the two shapes this workflow uses.

    🔴 Refuses an unrecognised shape rather than returning False. A matcher that
    silently says "no match" for a pattern it does not understand would make the
    negative controls below pass for the wrong reason — the exact vacuous-control
    shape this repo keeps finding.
    """
    if pattern.endswith("/**"):
        return path.startswith(pattern[: -len("**")])
    if "*" not in pattern:
        return path == pattern
    raise AssertionError(f"unhandled pattern shape: {pattern!r} — extend the matcher")


def _derived_inputs() -> set[str]:
    """Repo-relative paths the generator reads from OUTSIDE ui/, from its source.

    Captures every component after `'..'`, so a nested input like
    `terraform/csv/words.csv` is derived in full rather than truncated to its
    first segment. Truncating is not a cosmetic bug: `terraform` as a directory
    probe would be satisfied by a filter entry that does NOT cover the actual
    file, and the test would pass while the hole stayed open.
    """
    src = GEN.read_text()
    out = set()
    for args in re.findall(r"path\.resolve\(\s*UI\s*,\s*([^)]*)\)", src):
        parts = re.findall(r"['\"]([^'\"]+)['\"]", args)
        if not parts or parts[0] != "..":
            continue                      # resolves INSIDE ui/ -- covered by 'ui/**'
        out.add("/".join(parts[1:]))
    assert out, (
        "derived ZERO out-of-ui inputs from the generator -- the regex has drifted "
        "from the source, and an empty set makes every assertion below vacuous"
    )
    return out


def _probe_for(rel: str) -> str:
    """A concrete path under `rel`: the file itself, or a file inside the dir."""
    p = ROOT / rel
    return f"{rel}/any-file.json" if p.is_dir() else rel


def test_every_derived_input_is_in_both_path_filters():
    """AC1. A bank-only change must run the UI suite — on PR *and* on push."""
    on = _triggers()
    inputs = _derived_inputs()
    for event in ("pull_request", "push"):
        paths = on[event]["paths"]
        for rel in sorted(inputs):
            probe = _probe_for(rel)
            assert any(_matches(probe, p) for p in paths), (
                f"{event}: nothing in {paths} matches {probe!r}, which the "
                f"generator READS -- #443's exact hole"
            )


def test_the_bank_only_change_that_broke_main_would_now_run():
    """The concrete #443 file, not a synthetic one."""
    on = _triggers()
    probe = "sentences/sentences-hsk1-6-v1.json"
    for event in ("pull_request", "push"):
        assert any(_matches(probe, p) for p in on[event]["paths"]), event


def test_negative_control_unrelated_paths_still_do_NOT_run():
    """AC2. 🔴 The fix must not degrade into "run everything always" — that is how
    a filter gets deleted later for cost, taking the guard with it."""
    on = _triggers()
    for probe in ("README.md", "backend/app/models.py", "terraform/main.tf",
                  "docs/spec/anything.md", "sentences.md"):
        for event in ("pull_request", "push"):
            assert not any(_matches(probe, p) for p in on[event]["paths"]), (
                f"{event}: {probe!r} should NOT trigger the UI suite"
            )


def test_the_matcher_itself_discriminates():
    """A control on the control: these assertions mean nothing if `_matches`
    always returns False."""
    assert _matches("ui/src/x.js", "ui/**") is True
    assert _matches("sentences/a.json", "sentences/**") is True
    assert _matches(".github/workflows/ui-tests.yml", ".github/workflows/ui-tests.yml") is True
    assert _matches("README.md", "ui/**") is False
    # 🔴 `sentences.md` must NOT be matched by `sentences/**` — a prefix test
    # without the slash would pass it, and that is the classic substring bug.
    assert _matches("sentences.md", "sentences/**") is False
