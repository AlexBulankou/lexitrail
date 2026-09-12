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


# --- the same question, asked of backend-tests.yml (AC3) ---------------------
# 🔴 My first answer to AC3 was "already complete", reached by READING the two
# inputs I happened to notice. hc2 asked whether I had run the derive-from-source
# method backend-side instead, "the same way the words.csv hole was missed by
# inspection here". I had not. It found two more:
#
#   test_probe_wiring_301.py       -> terraform-ys/workloads.tf
#   test_srs_ladder_parity_384.py  -> ui/src/utils/srs.js
#
# The second asserts backend<->UI SRS parity, so the UI half could change and the
# parity test would not run. Inspection missed both, in the PR whose whole finding
# is that inspection misses things.

BACKEND_WF = ROOT / ".github" / "workflows" / "backend-tests.yml"
BACKEND = ROOT / "backend"

# Runtime config, not a committed CI input: `Path('..') / '.env'` is read at
# process start and `.env` is not in the repo. Named explicitly so the exclusion
# is a decision on the record rather than a silent gap in the regex.
_RUNTIME_ONLY = {".env"}


def _derived_backend_inputs() -> set[str]:
    """Repo-relative paths backend code reads from OUTSIDE backend/.

    Derived from `parents[N]` escapes: for `backend/tests/x.py` the directory
    depth inside backend/ is 1, so `parents[2]` and up leave the tree. The
    literal path components joined onto it are the input.
    """
    out = set()
    for f in sorted(BACKEND.rglob("*.py")):
        if "__pycache__" in str(f):
            continue
        src = f.read_text(errors="ignore")
        depth = len(f.relative_to(BACKEND).parts) - 1
        for m in re.finditer(
            r"parents\[(\d+)\]((?:\s*/\s*['\"][^'\"]+['\"])+)", src
        ):
            if int(m.group(1)) <= depth:
                continue                      # stays inside backend/
            parts = re.findall(r"['\"]([^'\"]+)['\"]", m.group(2))
            rel = "/".join(parts)
            if rel and rel not in _RUNTIME_ONLY:
                out.add(rel)
    assert out, (
        "derived ZERO out-of-backend inputs -- the regex has drifted from the "
        "source and every assertion below would be vacuous"
    )
    return out


def test_backend_out_of_tree_inputs_are_in_its_path_filters():
    """AC3, answered by DERIVATION rather than by reading.

    🔴 This is the assertion that would have caught my own wrong answer. It is
    written against backend-tests.yml for the same reason the ui one is written
    against ui-tests.yml: the property is 'a filter lists what its job READS',
    and it has to hold per workflow, not per author's attention."""
    d = yaml.safe_load(BACKEND_WF.read_text())
    on = d.get(True, d.get("on"))
    assert isinstance(on, dict), f"could not read the trigger block: {on!r}"
    inputs = _derived_backend_inputs()
    for event in ("pull_request", "push"):
        paths = on[event]["paths"]
        for rel in sorted(inputs):
            probe = _probe_for(rel)
            assert any(_matches(probe, p) for p in paths), (
                f"{event}: nothing in {paths} matches {probe!r}, which "
                f"backend/tests READS from outside backend/"
            )


def test_the_two_holes_hc2_asked_about_are_named_concretely():
    """Not synthetic: the exact files, so a filter edit that drops either reds."""
    d = yaml.safe_load(BACKEND_WF.read_text())
    on = d.get(True, d.get("on"))
    for probe in ("terraform-ys/workloads.tf", "ui/src/utils/srs.js"):
        for event in ("pull_request", "push"):
            assert any(_matches(probe, p) for p in on[event]["paths"]), (
                f"{event}: {probe!r} is read by a backend test and must trigger it"
            )


def test_backend_negative_control_still_holds():
    """The backend filter must not have degraded into run-everything either.

    ⚠️ `terraform-ys/` and `terraform/` are DIFFERENT directories, and the probe
    below pins that distinction: adding `terraform-ys/workloads.tf` must not drag
    in unrelated terraform-ys files."""
    d = yaml.safe_load(BACKEND_WF.read_text())
    on = d.get(True, d.get("on"))
    for probe in ("README.md", "sentences/sentences-hsk1-6-v1.json",
                  "terraform-ys/unrelated.tf", "ui/src/App.js"):
        for event in ("pull_request", "push"):
            assert not any(_matches(probe, p) for p in on[event]["paths"]), (
                f"{event}: {probe!r} should NOT trigger the backend suite"
            )
