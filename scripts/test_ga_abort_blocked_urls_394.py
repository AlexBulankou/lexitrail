"""issue-394: a COUNT is not evidence — `LeakReport` retains the blocked URLs.

Nine live prod navigations on 2026-09-12 each reported exactly `1 blocked`.
The reading that the one interception was `googletagmanager.com/gtag/js` — abort
the loader and no `collect` beacon can follow — was REASONING, because the
report carried no URL. These arms pin the field that makes it a measurement.

🔴 And the zero case gets its OWN sentence. `blocked == 0` is what an abort that
was never INSTALLED looks like, and it is indistinguishable from a page that
never beacons — issue-394's acceptance criterion names "a silent
zero-interception run" as the failure mode. Reporting it in the same shape as a
pass is what makes it silent.
"""
from __future__ import annotations

import pathlib
import sys

E2E = pathlib.Path(__file__).resolve().parents[1] / "e2e"
if str(E2E) not in sys.path:
    sys.path.insert(0, str(E2E))

from ga_abort import LeakReport, install_ga_abort  # noqa: E402

# 🔴 `_MAX_BLOCKED_URLS` is imported INSIDE the one arm that needs it, not at
# module scope. At module scope a pre-fix tree fails at COLLECTION, so every
# arm reports as one collection error — which cannot be told apart from a
# broken test file, and hides whether each arm would genuinely have failed.
# Deferring it lets the other six fail as real assertions against pre-fix code.


class _Req:
    def __init__(self, url): self.url = url


class _Route:
    def __init__(self, url): self.request = _Req(url); self.aborted = False
    def abort(self): self.aborted = True


class _Ctx:
    """Minimal stand-in: captures the handler `install_ga_abort` registers."""
    def __init__(self): self.handler = None
    def route(self, _pattern, handler): self.handler = handler


def _fire(ctx, *urls):
    routes = [_Route(u) for u in urls]
    for r in routes:
        ctx.handler(r)
    return routes


def test_blocked_urls_records_what_was_caught():
    ctx = _Ctx(); rep = install_ga_abort(ctx)
    _fire(ctx, "https://www.googletagmanager.com/gtag/js?id=G-XYZ")
    assert rep.blocked == 1
    assert rep.blocked_urls == ["https://www.googletagmanager.com/gtag/js?id=G-XYZ"], (
        "the count alone cannot say WHICH host matched — that is the gap this closes")


def test_the_summary_names_the_HOST_so_the_run_log_is_self_evidencing():
    ctx = _Ctx(); rep = install_ga_abort(ctx)
    _fire(ctx, "https://www.googletagmanager.com/gtag/js?id=G-XYZ")
    s = rep.summary()
    assert "1 analytics request(s) blocked, 0 leaked" in s
    assert "www.googletagmanager.com" in s, f"host missing from {s!r}"


def test_distinct_hosts_are_deduped_and_sorted():
    ctx = _Ctx(); rep = install_ga_abort(ctx)
    _fire(ctx,
          "https://www.google-analytics.com/g/collect?v=2",
          "https://www.googletagmanager.com/gtag/js?id=G-X",
          "https://www.google-analytics.com/g/collect?v=3")
    assert rep.blocked == 3
    s = rep.summary()
    assert "www.google-analytics.com, www.googletagmanager.com" in s, s


def test_ZERO_blocked_is_reported_as_CANNOT_TELL_not_as_a_pass():
    """🔴 The binding arm. A silent zero is issue-394's named failure mode.

    Negative control for the arms above: they prove the summary says the right
    thing when something WAS caught. This proves it says a DIFFERENT thing when
    nothing was — without which a run that never installed the abort reads
    exactly like a clean one.
    """
    rep = LeakReport()
    s = rep.summary()
    assert "CANNOT TELL" in s, f"a zero-interception run must not read as a pass: {s!r}"
    assert "0 leaked" not in s, (
        "'0 leaked' is the pass vocabulary; a zero-interception run has not "
        f"earned it: {s!r}")


def test_a_LEAK_still_wins_over_everything_else():
    """`completed` is non-empty: that verdict must not be softened by hosts."""
    rep = LeakReport(blocked=2,
                     blocked_urls=["https://www.googletagmanager.com/gtag/js"],
                     completed=["https://www.google-analytics.com/g/collect"])
    s = rep.summary()
    assert "GA4 LEAK" in s and rep.leaked is True


def test_blocked_urls_is_capped_but_the_COUNT_is_not():
    """The cap must never make the count wrong — that would be a worse trade."""
    from ga_abort import _MAX_BLOCKED_URLS  # noqa: PLC0415 — see the import note
    ctx = _Ctx(); rep = install_ga_abort(ctx)
    n = _MAX_BLOCKED_URLS + 5
    _fire(ctx, *[f"https://www.google-analytics.com/g/collect?n={i}" for i in range(n)])
    assert rep.blocked == n, "the cap must bound the LIST, never the count"
    assert len(rep.blocked_urls) == _MAX_BLOCKED_URLS


def test_every_route_is_still_aborted():
    """The whole point of the module — retaining a URL must not skip the abort."""
    from ga_abort import _MAX_BLOCKED_URLS  # noqa: PLC0415 — see the import note
    ctx = _Ctx(); rep = install_ga_abort(ctx)
    routes = _fire(ctx, *[f"https://www.google-analytics.com/g/collect?n={i}"
                          for i in range(_MAX_BLOCKED_URLS + 3)])
    assert all(r.aborted for r in routes), "a route past the cap was not aborted"
    assert rep.leaked is False
