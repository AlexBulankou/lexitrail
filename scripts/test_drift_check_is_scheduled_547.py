#!/usr/bin/env python3
"""The drift check has a CALLER (lexitrail#547 follow-up).

WHY THIS FILE EXISTS, SEPARATELY FROM THE OTHER TWO 547/308 TEST FILES.

`test_check_schema_drift.py` proves the script's verdicts are right.
`test_drift_check_targets_production_547.py` proves it asks the right SERVER.
Both passed in full while the script ran **nowhere** -- measured 2026-09-19,
`check_schema_drift` appeared in the tree only in those two files.

🔴 That is the shape the script's own docstring warns about, one level up: a
drift check that reports clean because it looked at nothing. A check nothing
invokes does not even report clean -- it reports NOTHING, and from outside the
two are indistinguishable. Correctness tests cannot see this, by construction:
every one of them calls the code themselves.

So this file asserts the COUPLING, which is the property no other test covers.
"""
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEDULES = ROOT / "ensemble.schedules.yaml"
SCRIPT = "scripts/check_schema_drift.py"


def _schedules():
    return yaml.safe_load(SCHEDULES.read_text())["schedules"]


def _entry():
    return next((s for s in _schedules() if SCRIPT in s.get("command", "")), None)


def test_the_drift_check_is_actually_scheduled():
    assert _entry() is not None, (
        f"{SCRIPT} is invoked by no schedule in {SCHEDULES.name}. It is a "
        "correct, well-tested detector that runs nowhere -- see this file's "
        "docstring."
    )


def test_the_control_shows_this_test_can_FAIL():
    """A membership test over a file that happens to contain everything would
    pass for the wrong reason. A script that is deliberately NOT scheduled must
    come back absent, or the assertion above proves nothing."""
    assert not any("scripts/check_sentence_bank.py" in s.get("command", "")
                   for s in _schedules())


def test_the_scheduled_command_names_a_script_that_EXISTS():
    """A schedule pointing at a moved or renamed file is a cron that fails every
    run for a reason no one reads. Cheap to assert, and it is the way this
    coupling is most likely to break later."""
    assert (ROOT / SCRIPT).is_file()


def test_the_budget_clears_the_measured_runtime():
    """The live hand-run took well under a minute against production. 180s is
    deliberate headroom: a `max_runtime` kill and a real CANNOT-TELL both
    surface as a non-zero exit, and telling them apart afterwards is exactly
    the forensics this repo keeps having to do."""
    assert _entry()["max_runtime"] >= 120


def test_the_entry_does_not_claim_two_exit_codes():
    """🔴 This script has THREE (0 PASS / 1 FAIL / 3 CANNOT-TELL). A description
    that says a non-zero means drift would send the next reader to look for
    schema damage when the comparison never happened."""
    assert "CANNOT-TELL" in _entry()["description"]
