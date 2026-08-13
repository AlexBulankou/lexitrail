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

CB = Path(__file__).resolve().parents[2] / "cloudbuild.yaml"


def _cfg():
    return yaml.safe_load(CB.read_text())


def _step(cfg, sid):
    for s in cfg["steps"]:
        if s.get("id") == sid:
            return s
    raise AssertionError(f"no step {sid!r}; ids={[s.get('id') for s in cfg['steps']]}")


def test_quota_gate_exists_and_starts_first():
    gate = _step(_cfg(), "quota-gate")
    assert gate["waitFor"] == ["-"], "the gate itself must start at t=0"


def test_every_other_step_waits_on_the_gate_transitively():
    """🔴 The largest bypass measured in the fleet.

    `waitFor: ['-']` means START AT t=0 REGARDLESS OF FILE POSITION. A gate
    placed at the top of a file whose steps all say `['-']` gates ZERO of them —
    present, correctly placed, enforcing nothing. Transitive because chaining
    (`a -> gate`, `b -> a`) is legitimate and still gated; only a `['-']` or a
    chain that never reaches the gate is a bypass.
    """
    cfg = _cfg()
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


def test_gate_passes_trigger_name():
    """issue-8237: without it the trigger name reads EMPTY, empty is treated as
    ungated, and inbuild.py's per-trigger downgrade turns enforcement off while
    leaving counting on. Fails toward 'never gate anything'."""
    args = _step(_cfg(), "quota-gate")["args"]
    assert "--trigger-name=$TRIGGER_NAME" in args


def test_gate_wires_the_break_glass_var_its_own_message_names():
    """The refusal message tells a blocked engineer to re-run with
    _BREAK_GLASS=1. A Cloud Build step gets no ambient environment, so without
    this the hatch the message names does not exist — worse than none, because
    it is specific and reads as actionable."""
    cfg = _cfg()
    env = _step(cfg, "quota-gate").get("env") or []
    assert any("ENSEMBLE_BUILD_QUOTA_BREAK_GLASS" in e for e in env)
    assert "_BREAK_GLASS" in (cfg.get("substitutions") or {}), \
        "_BREAK_GLASS must default to empty, or every ordinary build overrides"


def test_gate_reads_lexitrails_own_repo_and_state():
    args = _step(_cfg(), "quota-gate")["args"]
    assert "--repo=lexitrail" in args
    assert any(a.startswith("--state-uri=gs://") for a in args), \
        "a file:// store cannot compare-and-swap and degrades the gate open"


def test_no_machine_type_anywhere():
    """Constraint 4 of the authorization: default machine type. A larger one is
    a silent cost increase no later reviewer would think to look for.

    Asserted against the PARSED yaml, not the text — the file's own prose says
    'No machineType anywhere in this file', so a substring search matches the
    comment SAYING it is absent and passes even if a real key is added.
    """
    cfg = _cfg()
    assert "machineType" not in (cfg.get("options") or {})
    for s in cfg["steps"]:
        assert "machineType" not in s, f"step {s.get('id')} sets machineType"


def test_layer_cache_is_wired_and_tolerates_a_cold_start():
    """Constraint 3. An uncached rebuild is the most expensive thing this file
    can do; a missing cache on the FIRST build must not fail the build."""
    cfg = _cfg()
    pull = _step(cfg, "pull-cache")
    assert "|| true" in " ".join(pull["args"]), "first build has nothing to pull"
    assert "--cache-from" in _step(cfg, "backend-build")["args"]
