"""issue-394: every prod-navigating e2e script routes GA4 through `ga_abort`.

This is the AC's second half — *"the self-test fails if a navigating e2e file
lacks the abort"*. Without it the fix covers today's five scripts and the
mechanism the issue actually names survives: **`lt_measure` excludes
interception by design, so every NEW prod-navigating script starts
unprotected**, and nothing says so.

🔴 THE SELECTOR IS `chromium.launch`, WHICH IS A PROXY FOR "navigates prod".
A member can fail to carry it (a script that takes a page from a fixture) and a
non-member can carry it (a script pointed only at localhost). So this is a
FLOOR, not a census — it catches the shape we have actually shipped five times.
Stated rather than left implicit, because a proxy that is mostly right returns
a plausible, correctly-typed, mostly-right list and the gap is invisible in
both directions (my-hermes#2229's Form 7).

🔴 AND THE IMPORT IS ITSELF A PROXY — one rung up from the one above (adm@,
reviewing lex#397). This gate keys on `from ga_abort import ...`, which stands
for "interception is installed". **A script can import `ANALYTICS_RE` and never
route with it, and go green.** Three of the five do exactly the legitimate
version of that: they import the regex only and wire their own route.

That is this file's own argument turned on itself — hostnames were rejected
because copies drift, and the import is the next proxy along. It is recorded
rather than fixed because the honest gate is a RUNTIME one (`leaked == 0` on a
real navigation), and running it mints the GA4 sessions the module exists to
prevent. So: FLOOR, not ceiling, in both dimensions — which scripts it selects,
and what it proves about the ones it finds.

⚠️ WHY THE ASSERTION IS `ga_abort`, NOT `google-analytics`.
Three of the five carried their own correct `ANALYTICS_RE` copy and would pass
a substring check for the hostnames — while free to drift apart from each
other, which is what put two scripts on a glob in the first place. Keying on
the shared import is what makes "one definition" checkable.
"""
import re
from pathlib import Path

E2E = Path(__file__).resolve().parents[1] / "e2e"

#: Not navigation harnesses: the shared module itself, and anything that only
#: defines helpers. Every entry needs a REASON, so an exemption cannot be added
#: to quiet a failure without saying why.
EXEMPT = {
    "ga_abort.py": "the module under test — it IS the abort",
}


def _launchers() -> list[Path]:
    return sorted(p for p in E2E.glob("*.py")
                  if "chromium.launch" in p.read_text(encoding="utf-8"))


def test_the_selector_finds_something():
    """A positive control. Without it an empty population passes every
    assertion below, and a broken glob and a clean repo look identical."""
    found = _launchers()
    assert len(found) >= 5, (
        f"issue-394: expected the five known prod-navigating harnesses, found "
        f"{[p.name for p in found]} — if the selector broke, every other test "
        f"in this file is vacuously green."
    )


def test_every_navigating_script_uses_the_shared_abort():
    missing = [p.name for p in _launchers()
               if p.name not in EXEMPT
               and not re.search(r"^from ga_abort import ", p.read_text(encoding="utf-8"), re.M)]
    assert not missing, (
        f"issue-394: {missing} launch Chromium against prod without importing "
        f"`ga_abort`. Each run mints real GA4 sessions from bp's egress — at "
        f"~29 real users/28d that is ~1.6% of monthly sessions per run, and "
        f"runs cluster during investigation bursts, so they inflate exactly "
        f"the weeks agents are most active. Add "
        f"`from ga_abort import install_ga_abort` and install it on the "
        f"CONTEXT before the first goto()."
    )


def test_no_script_redefines_the_regex_locally():
    """One definition. Three scripts each had their own copy and two others had
    a glob; the copies agreed, which is why nothing caught the glob."""
    dupes = [p.name for p in E2E.glob("*.py")
             if p.name not in EXEMPT
             and re.search(r"^ANALYTICS_RE\s*=\s*re\.compile", p.read_text(encoding="utf-8"), re.M)]
    assert not dupes, (
        f"issue-394: {dupes} define ANALYTICS_RE locally — import it from "
        f"`ga_abort` so the definitions cannot drift."
    )


def test_the_glob_form_is_gone():
    """The specific regression: `**/*google-analytics*/**` as a route pattern.

    ⚠️ It does NOT miss the `www.`/`region1.` subdomains — that claim was in
    this repo's docstrings and in #394's body and is measurably FALSE (both
    match). What it misses is the `analytics.google.com` HOST, and it needed a
    second route for googletagmanager. Pinned on the real gap, so a future
    reader is not told a reason they can disprove in one command.
    """
    users = [p.name for p in E2E.glob("*.py")
             if p.name not in EXEMPT
             and "*google-analytics*" in p.read_text(encoding="utf-8")]
    assert not users, (
        f"issue-394: {users} still route GA4 by glob. It misses "
        f"`analytics.google.com` entirely."
    )
