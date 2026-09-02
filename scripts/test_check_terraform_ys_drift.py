"""Pins the THREE-state contract of the terraform-ys drift check (lexitrail#299 AC4).

The instrument was shown to discriminate on live inputs before this file existed,
which is the only reason the assertions below mean anything:

    PASS         real cluster, deploy/lexitrail-backend after the 2026-09-02 apply
                 -> exit 0, HashiCorp write 04:06:18Z >= newest commit 22:21Z
    FAIL         real cluster, kube-system/deploy/konnectivity-agent
                 -> exit 1, "no HashiCorp manager has ever written this object"
    CANNOT-TELL  real cluster, a namespace/object that does not exist
                 -> exit 3, and it says kubectl exited 1, not that the object is unmanaged

🔴 The load-bearing assertions are the two CANNOT-TELL ones. Every other test here
would still pass if someone collapsed "we could not look" into either PASS or FAIL,
and both collapses are silently catastrophic in opposite directions: into PASS and
the check reports a healthy stack for the rest of its life without ever reading one
(the exact failure #299 was filed about); into FAIL and it alarms on every run,
gets muted, and is then absent on the day the stack actually drifts.

The second load-bearing pair is `test_absent_managedfields_key_is_cannot_tell` vs
`test_present_list_with_no_hashicorp_entry_is_fail`. Those two inputs look almost
identical -- in both, no HashiCorp timestamp comes back -- and they mean opposite
things. `kubectl get -o json` strips `managedFields` unless you pass
`--show-managed-fields`, so forgetting the flag produces the first while looking
exactly like the second.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_terraform_ys_drift",
    Path(__file__).with_name("check_terraform_ys_drift.py"),
)
mod = importlib.util.module_from_spec(_SPEC)
sys.modules["check_terraform_ys_drift"] = mod
_SPEC.loader.exec_module(mod)

PASS, FAIL, CANNOT_TELL = mod.PASS, mod.FAIL, mod.CANNOT_TELL


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# The two real timestamps from the incident, so the fixture is not invented.
JUNE_APPLY = _t("2026-06-30T07:05:40Z")
NEWEST_COMMIT = _t("2026-09-01T22:21:48Z")
SEP_APPLY = _t("2026-09-02T04:06:18Z")


def test_the_incident_state_is_a_fail():
    """The exact inputs of #299: applied in June, source moved through September."""
    code, msg = mod.verdict(NEWEST_COMMIT, JUNE_APPLY, commits_behind=14)
    assert code == FAIL, msg
    assert "63." in msg or "63" in msg, f"should name the gap in days: {msg}"
    assert "14 commit" in msg, f"should name how many are unapplied: {msg}"


def test_after_the_apply_it_is_a_pass():
    code, msg = mod.verdict(NEWEST_COMMIT, SEP_APPLY)
    assert code == PASS, msg


def test_exactly_equal_timestamps_pass():
    """B >= A, not B > A. An apply in the same second as the commit is applied."""
    code, msg = mod.verdict(NEWEST_COMMIT, NEWEST_COMMIT)
    assert code == PASS, msg


def test_one_second_behind_is_a_fail():
    """The boundary on the failing side -- a bound is only tested AT its boundary."""
    behind = _t("2026-09-01T22:21:47Z")
    code, msg = mod.verdict(NEWEST_COMMIT, behind)
    assert code == FAIL, msg


def test_present_list_with_no_hashicorp_entry_is_fail():
    """terraform has genuinely never written this object. That is real drift."""
    code, msg = mod.verdict(NEWEST_COMMIT, None, manager_field_present=True)
    assert code == FAIL, msg
    assert "ever written" in msg, msg


def test_absent_managedfields_key_is_cannot_tell():
    """🔴 The opposite fact, one flag away. Must NOT read as the FAIL above."""
    code, msg = mod.verdict(
        NEWEST_COMMIT, None, manager_field_present=False,
        cannot_tell_reason="the response carried no `managedFields` key at all",
    )
    assert code == CANNOT_TELL, msg
    assert "NOT the manager being absent" in msg, msg


def test_unreadable_git_is_cannot_tell_not_pass():
    """🔴 If git does not answer, the check did not run. Silence is not health."""
    code, msg = mod.verdict(None, SEP_APPLY)
    assert code == CANNOT_TELL, msg
    assert "not a pass" in msg, msg


def test_cannot_tell_beats_a_would_be_pass():
    """Order matters: an unreadable git input must not be rescued by a fresh apply."""
    code, _ = mod.verdict(None, SEP_APPLY)
    assert code == CANNOT_TELL


def test_cannot_tell_reason_is_carried_into_the_message():
    """A verdict that cannot say WHY it could not look is not actionable."""
    _, msg = mod.verdict(
        NEWEST_COMMIT, None, manager_field_present=False,
        cannot_tell_reason="kubectl exited 1 for lexitrail/deploy/nope",
    )
    assert "kubectl exited 1" in msg, msg


def test_the_three_exit_codes_are_distinct():
    """0/1/3 -- a caller must be able to branch on all three."""
    assert len({PASS, FAIL, CANNOT_TELL}) == 3
    assert (PASS, FAIL, CANNOT_TELL) == (0, 1, 3)


def test_parse_ts_returns_none_rather_than_raising():
    """Every input here comes from a subprocess; a raise would crash the check."""
    for bad in (None, "", "   ", "not-a-time", "2026-13-45T99:99:99Z"):
        assert mod._parse_ts(bad) is None, bad
    assert mod._parse_ts("2026-09-02T04:06:18Z") == SEP_APPLY


def test_the_fail_message_warns_against_a_bare_apply():
    """my-hermes#1338: twelve live objects are absent from state, so `apply` is
    not a no-op and is owned/gated elsewhere. A drift alarm whose remedy is
    dangerous must say so at the point of alarm, not in a linked issue."""
    _, msg = mod.verdict(NEWEST_COMMIT, JUNE_APPLY)
    assert "my-hermes#1338" in msg, msg


# --- #313 review: the denominator ------------------------------------------
# hc2 caught that scoping "newest commit" to the whole directory makes the check
# FAIL on its own merge, and on every future README edit. Reproduced live on the
# PR branch before fixing (old scoping -> exit 1; new default -> exit 0), which
# is the only reason these two assertions mean anything.

def test_markdown_is_excluded_from_the_source_side():
    """🔴 Without this the check alarms because documentation moved. An alarm
    that fires on non-infra changes is muted within a week, which is the exact
    failure #299 is about."""
    assert ":(exclude,top)terraform-ys/*.md" in mod.DEFAULT_PATHSPECS


def test_pathspecs_are_top_anchored():
    """git pathspecs are CWD-relative: from a subdirectory a bare
    `terraform-ys/` narrows to nothing and a bare exclude excludes nothing."""
    for spec in mod.DEFAULT_PATHSPECS:
        assert spec.startswith(":(top)") or spec.startswith(":(exclude,top)"), spec


def test_several_objects_are_checked_not_one():
    """A terraform apply writes only what CHANGED, so a commit touching the UI
    deployment leaves the backend's timestamp untouched -- and a single-object
    check reports FAIL for a stack that was just applied (hc2, #313)."""
    assert len(mod.DEFAULT_OBJECTS) > 1
    assert "deploy/lexitrail-backend" in mod.DEFAULT_OBJECTS
    assert "deploy/lexitrail-ui-deployment" in mod.DEFAULT_OBJECTS


def test_the_path_label_names_tf_not_the_whole_directory():
    """The message a reader acts on must say which files counted."""
    assert mod.PATH_LABEL.endswith("*.tf")
