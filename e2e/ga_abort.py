"""Shared GA4 request abort for prod-navigating e2e harnesses (issue-394).

Every script here that navigates live prod pollutes the property: at ~29 real
users / 28d, one harness run is ~1.6% of monthly LT sessions, and runs cluster
during investigation bursts — so they inflate exactly the weeks an agent is most
active. `w/o 07-20: 43 sessions` is that signature.

🔴 REGEX, NOT A GLOB. `**/*google-analytics*/**` silently misses the real
`www.` and `region1.` subdomains GA4 actually beacons to. The repo's own
docstrings already said so; two scripts still used the glob, which is the
worse of the two failure modes — it *looks* installed and passes review while
letting the traffic through.

🔴 WHY THIS IS ITS OWN MODULE AND NOT IN `lt_measure`. `lt_measure` excludes
interception BY DESIGN ("harness/interception, not measurement"), and that
purity seam is worth keeping. The consequence, which is this issue's actual
mechanism, is that **every new prod-navigating script starts unprotected by
default** — the abort lived inside `tap_targets.py`, so it protected exactly
one caller and nothing else inherited it. A tiny shared module respects the
seam and makes the safe thing importable.

Usage — install on the CONTEXT, BEFORE new_page()/goto():

    from ga_abort import install_ga_abort, report_leaks
    ctx = browser.new_context(...)
    leaks = install_ga_abort(ctx)          # returns a live LeakReport
    page = ctx.new_page()
    page.goto(url)
    ...
    print(leaks.summary())                 # 0 completed == nothing reached GA4

⚠️ ORDER IS LOAD-BEARING and is why `install_ga_abort` takes a context rather
than a page: a route installed after navigation lets the first beacons through,
and the first beacons are the `page_view` — the one that creates the session
this exists to prevent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Substring-matches the FULL request URL. Kept identical to the value that was
#: living in tap_targets.py so this extraction changes no behaviour for its
#: existing caller — only its address.
ANALYTICS_RE = re.compile(
    r"googletagmanager\.com|google-analytics\.com|analytics\.google\.com")


@dataclass
class LeakReport:
    """What the abort caught, and what it did not.

    `blocked` alone cannot tell a working abort from a page that never beacons:
    both give 0 leaked. `completed` is the arm that makes `blocked` mean
    something — it records analytics requests that FINISHED despite the route,
    which is the only direct evidence the interception failed.
    """

    blocked: int = 0
    completed: list[str] = field(default_factory=list)

    @property
    def leaked(self) -> bool:
        return bool(self.completed)

    def summary(self) -> str:
        if self.completed:
            return (f"🔴 GA4 LEAK: {len(self.completed)} analytics request(s) "
                    f"COMPLETED despite the abort — {self.completed[:3]}")
        return f"ga-abort: {self.blocked} analytics request(s) blocked, 0 leaked"


def install_ga_abort(ctx) -> LeakReport:
    """Abort analytics on `ctx`. Call BEFORE new_page()/goto(). Returns a live
    LeakReport that fills in as the run proceeds."""
    rep = LeakReport()

    def _abort(route):
        rep.blocked += 1
        route.abort()

    ctx.route(ANALYTICS_RE, _abort)
    return rep


def watch_page(page, rep: LeakReport) -> None:
    """Record analytics requests that COMPLETED — i.e. the abort missed them.

    Separate from install_ga_abort because Playwright's `requestfinished` is a
    PAGE event while `route` is a CONTEXT one, and a caller with several pages
    needs to attach this to each.
    """
    page.on(
        "requestfinished",
        lambda r: rep.completed.append(r.url) if ANALYTICS_RE.search(r.url) else None,
    )
