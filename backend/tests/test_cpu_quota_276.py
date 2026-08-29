"""lexitrail#276 — the worker count must come from the CGROUP QUOTA, not nproc.

The defect this pins is silent: `multiprocessing.cpu_count()` returns a real,
plausible integer describing a real machine — just not the one the process may
use. Nothing raises. So every test here drives a value the WRONG answer could
not produce, rather than asserting the function "works".
"""
import os
from unittest import mock

import pytest

from app.cpu_quota import effective_cpus, quota_cpus


def _v2(tmp_path, text):
    (tmp_path / "cpu.max").write_text(text)
    return str(tmp_path)


def _v1(tmp_path, quota, period):
    d = tmp_path / "cpu"
    d.mkdir(parents=True, exist_ok=True)
    (d / "cpu.cfs_quota_us").write_text(str(quota))
    (d / "cpu.cfs_period_us").write_text(str(period))
    return str(tmp_path)


# ---------------------------------------------------------------- cgroup v2

def test_the_live_pod_shape_yields_one_worker_not_two(tmp_path):
    """The production case, verbatim: `cpu.max` = "20000 100000" (0.2 CPU).

    This is the whole bug. nproc says 2; the honest answer is 1.
    """
    assert quota_cpus(_v2(tmp_path, "20000 100000")) == 1


@pytest.mark.parametrize("text,expected", [
    ("20000 100000", 1),    # 0.2 CPU  -> floor to 1, never 0
    ("50000 100000", 1),    # 0.5 CPU
    ("100000 100000", 1),   # 1 CPU
    ("250000 100000", 2),   # 2.5 CPU  -> rounds DOWN
    ("400000 100000", 4),
    ("100000 50000", 2),    # a non-default PERIOD must be honoured, not assumed
])
def test_quota_is_derived_not_hardcoded(tmp_path, text, expected):
    assert quota_cpus(_v2(tmp_path, text)) == expected


def test_zero_workers_is_never_returned(tmp_path):
    """A sub-1.0 grant must floor at 1. You cannot schedule 0 workers, and
    `ThreadPoolExecutor(max_workers=0)` raises."""
    assert quota_cpus(_v2(tmp_path, "1000 100000")) == 1


def test_unlimited_is_None_and_not_confused_with_unreadable(tmp_path):
    """`max` means "no quota" — a DIFFERENT fact from "I could not read it",
    and both must be None-but-for-a-reason rather than a number."""
    assert quota_cpus(_v2(tmp_path, "max 100000")) is None


# ---------------------------------------------------------------- cgroup v1

def test_v1_quota_is_read_when_v2_is_absent(tmp_path):
    assert quota_cpus(_v1(tmp_path / "a", 20000, 100000)) == 1
    assert quota_cpus(_v1(tmp_path / "b", 300000, 100000)) == 3


def test_v1_minus_one_means_unlimited(tmp_path):
    assert quota_cpus(_v1(tmp_path, -1, 100000)) is None


# ------------------------------------------------------- absence / garbage

def test_absent_cgroup_reads_as_no_quota_not_as_a_number(tmp_path):
    """A missing cgroup tree is CANNOT TELL. It must not become 1 — that would
    silently pin every non-container run to a single worker."""
    assert quota_cpus(str(tmp_path / "nope")) is None


@pytest.mark.parametrize("garbage", ["", "banana", "20000", "a b", "0 100000"])
def test_garbage_never_yields_a_confident_number(tmp_path, garbage):
    assert quota_cpus(_v2(tmp_path, garbage)) is None


# ------------------------------------------------------- effective_cpus

def test_effective_falls_back_to_cpu_count_with_no_quota(tmp_path):
    with mock.patch("multiprocessing.cpu_count", return_value=8):
        assert effective_cpus(str(tmp_path / "nope")) == 8


def test_effective_prefers_the_quota_over_a_larger_host(tmp_path):
    """The production shape: host 2, quota 0.2 -> 1. If this ever returns 2
    again the bug is back."""
    with mock.patch("multiprocessing.cpu_count", return_value=2):
        assert effective_cpus(_v2(tmp_path, "20000 100000")) == 1


def test_effective_is_capped_by_the_HOST_when_the_quota_exceeds_it(tmp_path):
    """A limit of 4 on a 2-core node grants 4, but only 2 can run. Taking the
    quota alone would over-spawn — the same class of error, mirrored."""
    with mock.patch("multiprocessing.cpu_count", return_value=2):
        assert effective_cpus(_v2(tmp_path, "400000 100000")) == 2


def test_effective_never_returns_zero(tmp_path):
    with mock.patch("multiprocessing.cpu_count", return_value=1):
        assert effective_cpus(_v2(tmp_path, "1000 100000")) == 1
