#!/usr/bin/env python3
"""Pins lexitrail's cloudbuild quota-gate wiring (issue-77).

Every assertion here guards a failure that is INVISIBLE IN A GREEN BUILD: the
step runs, python exits 0, the build goes green, and the gate enforces nothing.
There is no output that distinguishes a working gate from an inert one, which is
why these are mechanical rather than a comment asking the next author to check.

Run:  python3 -m pytest scripts/build_budget/test_cloudbuild_wiring_77.py
"""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ROOT = Path(__file__).resolve().parents[2]

# EVERY gated build config in the repo, with the id of its docker build step.
# issue-216 added the second one; the wiring below was written for the first and
# would have passed unchanged while the new file gated nothing, because the
# tests named a single file rather than the class of files.
#
# 🔴 A config added here and NOT added to this list is the failure this list
# exists to stop, so the last test in the yaml block asserts the list is the
# whole set rather than trusting whoever adds the next one to remember.
# `build_id` is the docker build step to check `--cache-from` on, or None for a
# config that builds no image (the jest one runs npm, so a layer cache is not a
# thing it can have — skipping that ONE assertion is right, silently excluding
# the whole file from the other six would not be).
CONFIGS = [
    (_ROOT / "cloudbuild.yaml", "backend-build"),
    (_ROOT / "cloudbuild-ui.yaml", "ui-build"),
    (_ROOT / "cloudbuild-ui-test.yaml", None),
]
_IDS = [p.name for p, _ in CONFIGS]

# Kept so the module still names the original file explicitly.
CB = CONFIGS[0][0]

gated = pytest.mark.parametrize("path,build_id", CONFIGS, ids=_IDS)


def _cfg(path=CB):
    return yaml.safe_load(path.read_text())


def _step(cfg, sid):
    for s in cfg["steps"]:
        if s.get("id") == sid:
            return s
    raise AssertionError(f"no step {sid!r}; ids={[s.get('id') for s in cfg['steps']]}")


@gated
def test_quota_gate_exists_and_starts_first(path, build_id):
    gate = _step(_cfg(path), "quota-gate")
    assert gate["waitFor"] == ["-"], "the gate itself must start at t=0"


@gated
def test_every_other_step_waits_on_the_gate_transitively(path, build_id):
    """🔴 The largest bypass measured in the fleet.

    `waitFor: ['-']` means START AT t=0 REGARDLESS OF FILE POSITION. A gate
    placed at the top of a file whose steps all say `['-']` gates ZERO of them —
    present, correctly placed, enforcing nothing. Transitive because chaining
    (`a -> gate`, `b -> a`) is legitimate and still gated; only a `['-']` or a
    chain that never reaches the gate is a bypass.
    """
    cfg = _cfg(path)
    by_id = {s.get("id"): s for s in cfg["steps"]}

    def reaches_gate(sid, seen=()):
        if sid == "quota-gate":
            return True
        if sid in seen:
            return False
        wf = by_id[sid].get("waitFor")
        assert wf is not None, (
            f"step {sid!r} has NO waitFor. That waits for the step ABOVE it, "
            "which is position-dependent and silently serialises the build. "
            "Point it at 'quota-gate' explicitly.")
        assert wf != ["-"], (
            f"step {sid!r} declares waitFor ['-'] — it starts at t=0 and "
            "BYPASSES the quota gate entirely (issue-77).")
        return all(reaches_gate(p, seen + (sid,)) for p in wf)

    for sid in by_id:
        if sid != "quota-gate":
            assert reaches_gate(sid), f"step {sid!r} never reaches the quota gate"


@gated
def test_gate_passes_trigger_name(path, build_id):
    """issue-8237: without it the trigger name reads EMPTY, empty is treated as
    ungated, and inbuild.py's per-trigger downgrade turns enforcement off while
    leaving counting on. Fails toward 'never gate anything'."""
    args = _step(_cfg(path), "quota-gate")["args"]
    assert "--trigger-name=$TRIGGER_NAME" in args


@gated
def test_gate_wires_the_break_glass_var_its_own_message_names(path, build_id):
    """The refusal message tells a blocked engineer to re-run with
    _BREAK_GLASS=1. A Cloud Build step gets no ambient environment, so without
    this the hatch the message names does not exist — worse than none, because
    it is specific and reads as actionable."""
    cfg = _cfg(path)
    env = _step(cfg, "quota-gate").get("env") or []
    assert any("ENSEMBLE_BUILD_QUOTA_BREAK_GLASS" in e for e in env)
    assert "_BREAK_GLASS" in (cfg.get("substitutions") or {}), \
        "_BREAK_GLASS must default to empty, or every ordinary build overrides"


@gated
def test_gate_reads_lexitrails_own_repo_and_state(path, build_id):
    args = _step(_cfg(path), "quota-gate")["args"]
    assert "--repo=lexitrail" in args
    assert any(a.startswith("--state-uri=gs://") for a in args), \
        "a file:// store cannot compare-and-swap and degrades the gate open"


@gated
def test_no_machine_type_anywhere(path, build_id):
    """Constraint 4 of the authorization: default machine type. A larger one is
    a silent cost increase no later reviewer would think to look for.

    Asserted against the PARSED yaml, not the text — the file's own prose says
    'No machineType anywhere in this file', so a substring search matches the
    comment SAYING it is absent and passes even if a real key is added.
    """
    cfg = _cfg(path)
    assert "machineType" not in (cfg.get("options") or {})
    for s in cfg["steps"]:
        assert "machineType" not in s, f"step {s.get('id')} sets machineType"


@gated
def test_layer_cache_is_wired_and_tolerates_a_cold_start(path, build_id):
    """Constraint 3. An uncached rebuild is the most expensive thing this file
    can do; a missing cache on the FIRST build must not fail the build."""
    if build_id is None:
        pytest.skip(f"{path.name} builds no image -- no layer cache to wire")
    cfg = _cfg(path)
    pull = _step(cfg, "pull-cache")
    assert "|| true" in " ".join(pull["args"]), "first build has nothing to pull"
    assert "--cache-from" in _step(cfg, build_id)["args"]


@gated
def test_logging_destination_is_set_because_these_run_under_a_service_account(path, build_id):
    """issue-228. Cloud Build REJECTS a service-account build with no logging
    destination -- and it rejects it at VALIDATION, before step 0.

    🔴 That is why this is pinned rather than left to review. The rejection means
    `quota-gate` never runs, so the build is invisible to the budget: the first one
    (2026-08-28T16:00:31Z) left `used` at 1. Every other test in this module guards
    a gate that runs and enforces nothing; this one guards a gate that never runs at
    all, and the two are indistinguishable downstream -- both leave the counter
    untouched.

    Pinned for EVERY config, not just the one that failed. `cloudbuild-ui.yaml` had
    the identical omission and no trigger yet, so nothing would have failed until
    issue-216 created one and its first build was rejected the same way -- the same
    bug, rediscovered at the same cost, one issue later.
    """
    cfg = _cfg(path)
    opts = cfg.get("options") or {}
    assert opts.get("logging") in ("CLOUD_LOGGING_ONLY", "NONE") or opts.get(
        "defaultLogsBucketBehavior") == "REGIONAL_USER_OWNED_BUCKET" or cfg.get(
        "logsBucket"), (
        f"{path.name} sets no logging destination. A trigger running it under a "
        "service account is rejected before step 0 -- see issue-228."
    )


def test_configs_list_covers_every_gated_build_config_in_the_repo():
    """🔴 The guard on the list itself.

    Every assertion above names files through CONFIGS, so a NEW `cloudbuild*.yaml`
    that nobody adds to that list is unpinned -- and unpinned is invisible,
    because an inert gate produces a green build exactly like a live one. That is
    the same shape the gate tests guard inside a file, one level out.

    Keyed on "declares a step with id `quota-gate`", not on the filename, so a
    config that genuinely has no gate (nothing to enforce) is correctly ignored
    rather than needing an exclusion entry.
    """
    listed = {p.name for p, _ in CONFIGS}
    found = set()
    for f in sorted(_ROOT.glob("cloudbuild*.yaml")):
        cfg = yaml.safe_load(f.read_text()) or {}
        if any(s.get("id") == "quota-gate" for s in (cfg.get("steps") or [])):
            found.add(f.name)
    assert found == listed, (
        f"gated configs on disk {sorted(found)} != CONFIGS {sorted(listed)}. "
        "A gated config missing from CONFIGS is checked by nothing; a name in "
        "CONFIGS with no gate on disk means the gate was removed."
    )


# ── the trap that is NOT in cloudbuild.yaml ──────────────────────────────────
CFG = Path(__file__).resolve().parents[2] / "config" / "build-budget.json"


def _lexitrail_cfg():
    import json
    return json.loads(CFG.read_text())["projects"]["lexitrail"]


def test_gate_triggers_is_not_empty_while_enforcing():
    """The second inert-gate trap, and the only one this repo's yaml cannot show.

    `gate.py`: "a trigger not in `gate_triggers` is never touched, whatever the
    balance." So `enforcing: true` beside an empty list is enforcement in NAME
    ONLY -- the build is counted and can never be refused, and a green build is
    byte-identical either way. lexitrail shipped exactly that pair (gate.py names
    it as the live instance), which is why this is mechanical rather than a note.

    Pinned as the PAIR, not as two facts: either is individually legitimate
    (enforcing=false with no triggers is an honest shadow config), and it is
    only their combination that claims a property the config cannot deliver.
    """
    c = _lexitrail_cfg()
    if not c.get("enforcing", False):
        pytest.skip("enforcing=false -- an empty gate_triggers is honest here")
    assert c.get("gate_triggers"), (
        "lexitrail declares enforcing=true with an empty `gate_triggers` -- "
        "nothing can ever be refused. Either list the deploy trigger's name or "
        "set enforcing=false; it DEBITS either way, so what is lost is the "
        "refusal, not the accounting."
    )


def test_gated_trigger_name_matches_the_state_bucket_project():
    """A name in `gate_triggers` that no real trigger carries is inert in the
    quiet direction: `gate.py` fails open on every ambiguity, so a typo here
    disables enforcement and reports nothing. Nothing in this repo can see the
    live trigger list, so this pins the weaker invariant that IS checkable --
    the gated name is lexitrail's, not a copy-paste from a sibling project."""
    names = _lexitrail_cfg().get("gate_triggers") or []
    assert names, "covered by the test above; this one assumes non-empty"
    for n in names:
        assert n.startswith("lexitrail-"), (
            f"gated trigger {n!r} is not a lexitrail trigger -- the vendored "
            "config was copied from a sibling project and gates someone else's "
            "builds while lexitrail's own run ungated."
        )
