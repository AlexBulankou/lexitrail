#!/usr/bin/env python3
"""kubectl resolution for the SCHEDULED environment (lexitrail#547 follow-up).

The drift check hand-ran green and returned CANNOT-TELL on its first scheduled
run, because `kubectl` could not be executed there.

🔴 WHAT THIS FILE IS CAREFUL ABOUT. My first attempt to test the fix ran the
script with `PATH=/usr/bin:/bin` and watched it pass -- but `/usr/bin/kubectl`
exists on this host, so that reproduction passed on the UNFIXED code too. It
could not come out the other way, which means it was not evidence. These tests
drive `resolve_kubectl` directly with the filesystem and PATH both controlled,
so each one can actually fail.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "check_schema_drift", ROOT / "scripts" / "check_schema_drift.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["check_schema_drift"] = mod
spec.loader.exec_module(mod)


@pytest.fixture
def no_kubectl_anywhere(monkeypatch):
    """Nothing on PATH, nothing at any candidate, nothing in the snap glob."""
    monkeypatch.setattr(mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(mod.os, "access", lambda *_a, **_k: False)
    monkeypatch.setattr(mod.glob, "glob", lambda _p: [])


def test_path_wins_when_it_has_kubectl(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/from/path/kubectl")
    assert mod.resolve_kubectl() == "/from/path/kubectl"


def test_an_absolute_candidate_is_used_when_PATH_is_narrow(monkeypatch):
    """The case the scheduled failure plausibly is: the binary exists, the
    runner's PATH does not reach it."""
    monkeypatch.setattr(mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(mod.os, "access",
                        lambda p, _m: p == "/usr/bin/kubectl")
    monkeypatch.setattr(mod.glob, "glob", lambda _p: [])
    assert mod.resolve_kubectl() == "/usr/bin/kubectl"


def test_the_snap_glob_takes_the_NEWEST_not_the_first(monkeypatch):
    """🔴 The snap path carries a version. Sorting matters, and an unsorted
    implementation would pass a single-entry test while picking an old
    release once two are installed -- which is when it would matter."""
    monkeypatch.setattr(mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(mod.os, "access",
                        lambda p, _m: p.startswith("/snap/google-cloud-cli/"))
    monkeypatch.setattr(mod.glob, "glob", lambda _p: [
        "/snap/google-cloud-cli/499/bin/kubectl",
        "/snap/google-cloud-cli/1002/bin/kubectl",
    ])
    # 1002 > 499 NUMERICALLY. A reverse STRING sort returns 499 here, which is
    # the bug this test was written against and found on the first run.
    assert mod.resolve_kubectl() == "/snap/google-cloud-cli/1002/bin/kubectl"


def test_a_candidate_that_is_not_EXECUTABLE_is_not_used(monkeypatch):
    """Presence is not runnability. `os.access(X_OK)` is the question, and a
    test that only checked existence would accept an unrunnable file."""
    monkeypatch.setattr(mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(mod.os, "access", lambda *_a, **_k: False)
    monkeypatch.setattr(mod.glob, "glob",
                        lambda _p: ["/snap/google-cloud-cli/499/bin/kubectl"])
    assert mod.resolve_kubectl() is None


def test_nothing_anywhere_is_None(no_kubectl_anywhere):
    assert mod.resolve_kubectl() is None


def test_the_not_found_message_NAMES_every_location_tried(no_kubectl_anywhere):
    """An error that fits several causes is not evidence. The previous message
    said only that kubectl 'could not be run', which is equally consistent with
    a narrow PATH and with running somewhere else entirely -- and I spent real
    time on the wrong one of those."""
    msg = mod._kubectl_not_found_msg()
    for loc in ("PATH", "/usr/bin/kubectl", "/snap/google-cloud-cli/"):
        assert loc in msg, (loc, msg)


def test_the_message_says_MISSING_TOOL_and_not_drift(no_kubectl_anywhere):
    """🔴 The three-state discipline is the point. A missing tool reported as a
    finding sends someone hunting for schema damage that does not exist."""
    msg = mod._kubectl_not_found_msg().lower()
    assert "missing tool" in msg
    assert "did not happen" in msg
