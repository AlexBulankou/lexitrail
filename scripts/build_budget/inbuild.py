"""issue-7947 / goal 1.1 — THE IN-BUILD QUOTA STEP. Item 1.

The first step of a build. It charges the build against its repo's daily count
and, when the count is spent, prints why and exits NON-ZERO so the build stops.

    steps:
      - name: 'gcr.io/cloud-builders/gcloud'
        id: 'quota-gate'
        entrypoint: 'python3'
        args: ['scripts/build_budget/inbuild.py', '--repo', 'ensemble',
               '--state-uri', 'gs://yojowa-ensemble-state/build-budget/count-ensemble.json',
               '--build-id', '$BUILD_ID']

🔴 EXIT 0 ON A REFUSAL WOULD BE A CORRECTNESS BUG, not a softer option. A green
check on a build that never ran is a false pass, and it is worse than the
overspend it was avoiding (Alex + zz1 both, 2026-08-09). Hence exit 1 and a
message naming the refill time — a refusal an engineer cannot act on becomes a
ticket, and the ticket becomes the habit of disabling the gate.

⚠️ WHAT THIS STEP DOES NOT COVER, stated here because the gap is invisible from
inside the file and every reader of this module will assume otherwise:

    it refuses at BUILD TIME, not at ADMISSION — the build is already running
    and already billing when this step speaks, so it caps the EXPENSIVE tail
    (image builds, long test matrices), not the per-build floor.

    it gates only steps that TRANSITIVELY DEPEND ON IT. A step declaring
    `waitFor: ['-']` starts at build start and runs regardless. That is the
    whole reason for the root-repointing work (9 edits measured across three
    repos, decipher and my-hermes unmeasured) and mpl@'s land-time lint. Without
    those, wiring this step in gates NOTHING while looking like enforcement —
    ensemble's `cloudbuild-build-orch.yaml` was 0-of-4 gated for exactly this
    reason.

    it does not see `gcloud builds submit` or terraform-submitted builds at all.
    Those are counted by `reconcile.py` as observed-vs-counted residue; they are
    not refusable here. Measuring that residue is the point of stage (b).

FAIL OPEN, BUT LOUD AND COUNTED — constraint 1, unchanged from `bucket`/`counter`.
An instrument glitch that blocks every build in the fleet is worse than a day of
overspend. But a silent override becomes the habit within a week, so every
degraded path prints a banner and increments `lifetime_degraded` wherever it can
still be written. The one case that cannot self-count is a dead store: with no
writable state there is nowhere to put the increment, and this module says so
rather than implying a count that does not exist.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import random
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.build_budget import counter  # noqa: E402
from scripts.build_budget import store as store_mod  # noqa: E402

EXIT_OK = 0
EXIT_REFUSED = 1

# Bounded: a build that spends a minute losing CAS races has already cost more
# than the build it was policing. Six attempts over ~2s covers realistic
# same-repo concurrency (a handful of builds), and exhaustion is a loud
# fail-open rather than a block.
MAX_CAS_ATTEMPTS = 6

BREAK_GLASS_ENV = "ENSEMBLE_BUILD_QUOTA_BREAK_GLASS"
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "build-budget.json"


# A Cloud Build substitution that was referenced but never DECLARED can arrive
# as its own literal text. `"${_BREAK_GLASS}"` is non-empty, so a plain
# truthiness test reads it as an override and pins break-glass ON — the gate then
# refuses nothing while looking present and printing a healthy banner.
# 🔴 Surfaced by #8205, which added this step to the DEPLOY path referencing
# `${_BREAK_GLASS}` without declaring it. mcl@ found the missing declaration; the
# silent-override consequence is a hole in THIS parser, not in that yaml, so it
# is fixed here rather than defended against per-caller. An escape hatch that
# turns itself on is worse than one that does not work.
_PLACEHOLDER = re.compile(r"^\$\{?_[A-Z0-9_]+\}?$")


def _break_glass_from_env() -> bool:
    """True only for a DELIBERATE override. Loud about a misconfigured one."""
    raw = os.environ.get(BREAK_GLASS_ENV, "").strip()
    if not raw or raw == "0":
        return False
    if _PLACEHOLDER.match(raw):
        # Not silent: the yaml is wrong and somebody has to learn that. But it
        # must not grant the override — failing toward "quota enforced" is the
        # safe direction for a flag whose whole job is to disable enforcement.
        print(f"BUILD QUOTA: ignoring {BREAK_GLASS_ENV}={raw!r} — that is an "
              f"UNSUBSTITUTED Cloud Build placeholder, not an override. Declare "
              f"the substitution in the build config. Treating as NOT set.")
        return False
    return True


def load_repo_config(config_path: Path, repo: str) -> tuple[Optional[dict], Optional[str]]:
    """Returns (repo_config, degraded_reason). Never raises.

    A missing key here is a DEPLOYMENT error, not a quota verdict, so it takes
    the degraded path rather than either extreme: failing closed would let one
    config typo stop every build in the fleet, and inventing a default count
    would be the "fallback that is also a legitimate value" this config file's
    own comment forbids — hcl@ caught exactly that on #8199, where lexitrail
    claimed `enforcing: true` with no count at all.
    """
    try:
        cfg = json.loads(Path(config_path).read_text())
    except Exception as e:
        return None, f"config unreadable ({config_path}): {e}"
    proj = (cfg.get("projects") or {}).get(repo)
    if not isinstance(proj, dict):
        return None, f"no config entry for repo {repo!r} in {config_path}"
    if not isinstance(proj.get("daily_build_count"), int):
        return None, (f"{repo} has no integer daily_build_count in "
                      f"{config_path} — refusing to invent one")
    return proj, None


def charge(st, *, repo: str, daily_total: int, enforcing: bool,
           break_glass: bool, now_ts: float,
           attempts: int = MAX_CAS_ATTEMPTS, sleep=time.sleep):
    """The CAS loop. Returns (decision, persisted: bool, degraded_reason).

    On a lost race we re-run `counter.decide` against the FRESHLY READ state
    rather than re-applying our own delta — `decide` is pure over state, so
    re-deciding is both correct and the only thing that stays correct when the
    winner's write changed the day, the accrual, or crossed the reset boundary.
    """
    last: Any = None
    for attempt in range(attempts):
        try:
            state, gen = st.load()
        except store_mod.StoreUnreadable as e:
            return None, False, f"state unreadable: {e}"
        if state is None:
            state = counter.new_state(now_ts)
        new_state, decision = counter.decide(
            state, repo=repo, now_ts=now_ts, daily_total=daily_total,
            enforcing=enforcing, break_glass=break_glass)
        try:
            st.save(new_state, gen)
            return decision, True, None
        except store_mod.StoreConflict as e:
            last = e
            # Jittered so N racing builds do not re-collide in lockstep.
            sleep(min(0.05 * (2 ** attempt), 0.8) * (0.5 + random.random()))
            continue
        except store_mod.StoreUnreadable as e:
            return None, False, f"state unwritable: {e}"
    return None, False, f"lost {attempts} CAS races on the counter ({last})"


def _degraded(repo: str, reason: str, st: Any = None) -> tuple:
    """Returns (decision, persisted). Counts the degraded build WHERE IT CAN.

    🔴 "Fail open, but LOUD and COUNTED" was only two-thirds implemented: every
    degraded path built a decision whose `lifetime_degraded` was incremented and
    then threw the state away, so the field was structurally always 0 — and I
    published that 0 as evidence the gate was not failing open. It could not have
    read anything else.

    The two sub-cases are genuinely different and only one is defensible:

        store DEAD      nowhere to write. Cannot self-count, and the banner says
                        so rather than implying a count that does not exist.
        config MISSING  the store is FINE. Countable, and now counted.

    Without this, "how many builds ran uncounted while a config was broken?" has
    no answer — which is the question an override-nobody-counts is supposed to
    make answerable.
    """
    state = {}
    gen = None
    if st is not None:
        try:
            loaded, gen = st.load()
            state = loaded if loaded is not None else counter.new_state(time.time())
        except store_mod.StoreUnreadable:
            st = None
    new_state, d = counter.decide(state, repo=repo, now_ts=time.time(),
                                  daily_total=0, degraded=True,
                                  degraded_reason=reason)
    if st is None:
        return d, False
    try:
        st.save(new_state, gen)
        return d, True
    except (store_mod.StoreUnreadable, store_mod.StoreConflict):
        # Best-effort: a degraded build must never be BLOCKED by a failure to
        # record that it was degraded.
        return d, False


def emit(decision, *, build_id: str, store_uri: str, persisted: bool,
         ungated_trigger: Optional[str] = None) -> None:
    """One human banner and one JSON row. Both, deliberately.

    The banner is what an engineer reads in the Cloud Build log when their build
    stops; the JSON row is what `reconcile` reads to compare counted against
    billing-observed. Neither substitutes for the other.
    """
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kind": "inbuild-quota",
        "build_id": build_id,
        "state_uri": store_uri,
        "persisted": persisted,
        "repo": decision.repo,
        "day": decision.day,
        "used_before": decision.used_before,
        "used_after": decision.used_after,
        "accrued": decision.accrued,
        "daily_total": decision.daily_total,
        "would_refuse": decision.would_refuse,
        "enforcing": decision.enforcing,
        "refused": decision.refused,
        "break_glass": decision.break_glass,
        "degraded": decision.degraded,
        "degraded_reason": decision.degraded_reason,
        "notes": list(decision.notes),
        # issue-8237: which trigger, if any, took this build out of enforcement.
        # `enforcing:false` in the row has TWO causes now — the repo is not
        # enforcing at all, or this trigger is not one the gate may close — and
        # a reader cannot tell them apart from the boolean alone.
        "ungated_trigger": ungated_trigger,
    }
    if decision.degraded:
        print("=" * 72)
        print(f"BUILD QUOTA DEGRADED — allowing this build WITHOUT a count check.")
        print(f"  reason: {decision.degraded_reason}")
        if not persisted:
            # 🔴 States the FACT, never a cause. This line used to read "the
            # state was unwritable", which is only one of the four ways we get
            # here — the live CI run on #8203 printed it for a MISSING CONFIG,
            # directly contradicting the correct `reason:` line above it. A
            # wrong cause is worse than no cause: it is specific, it reads as
            # diagnosis, and it sends whoever debugs this at the GCS object
            # when nothing was ever wrong with the GCS object.
            print("  NOT COUNTED: this build is absent from the day's total. "
                  "Not a silent zero — this line is the record. The cause is "
                  "the `reason` above, and only that.")
        print("=" * 72)
    elif decision.refused:
        print("=" * 72)
        print(counter.refusal_message(decision))
        for n in decision.notes:
            print(f"  note: {n}")
        # Names the ACTUAL invocation, not "set an env var". The step gets no
        # ambient environment, so the var only arrives via the substitution the
        # yaml maps onto it — telling a blocked engineer to "export" it would
        # send them somewhere that cannot work.
        print(f"  break-glass: re-run this build with "
              f"--substitutions=_BREAK_GLASS=1 (sets {BREAK_GLASS_ENV}). "
              f"The build is still COUNTED — an override nobody counts "
              f"becomes the habit.")
        print("=" * 72)
    else:
        state = ("BREAK-GLASS" if decision.break_glass else
                 "SHADOW (would refuse)" if decision.would_refuse else "OK")
        print(f"BUILD QUOTA {state}: {decision.repo} "
              f"{decision.used_after}/{decision.accrued} used of "
              f"{decision.daily_total}/day — {decision.remaining} left now.")
        if ungated_trigger:
            print(f"  NOT GATEABLE: trigger {ungated_trigger!r} is absent from "
                  f"this repo's `gate_triggers`, so quota can never refuse it "
                  f"(issue-8237). Counted, never blocked.")
    print(json.dumps(row, sort_keys=True))


def main(argv: Optional[list] = None) -> int:
    """Fail-open wrapper. THE UNANTICIPATED failure is the one that matters.

    🔴 MEASURED, 2026-08-10 (adm@), and it would have blocked every ensemble
    build the moment this landed: `gcr.io/cloud-builders/gcloud` ships no
    tzdata, so `ZoneInfo("America/Los_Angeles")` raised, the step crashed, and
    a crash exits NON-ZERO — which this gate defines as REFUSED. The fleet-wide
    outage would have arrived through the code path designed to prevent one.

    The hole was not the timezone. It was that `_main` degraded open only for
    the failures it NAMED — unreadable store, missing count, bad URI — so
    fail-open held exactly where someone had already thought of the failure,
    and inverted everywhere else. An unhandled exception is by definition the
    case nobody thought of, so it is precisely the case that must not decide
    the fleet's build policy by accident.

    Hence: ANY escape becomes a loud degraded ALLOW. A refusal is now reachable
    only by the one `return EXIT_REFUSED` that a quota decision produces
    deliberately — never by a stack trace.
    """
    try:
        return _main(argv)
    except SystemExit as e:            # argparse and friends
        if not e.code:
            raise
        reason = f"the step could not start (exit {e.code}) — check its args"
    except BaseException as e:         # noqa: BLE001 — deliberate, see above
        reason = f"{type(e).__name__}: {e}"
    print("=" * 72)
    print("BUILD QUOTA DEGRADED — allowing this build WITHOUT a count check.")
    print(f"  reason: unhandled failure in the quota step — {reason}")
    print("  NOT COUNTED: this build is absent from the day's total.")
    print("  The gate failed OPEN by design; a crash must never refuse a build.")
    print("=" * 72)
    print(json.dumps({"kind": "inbuild-quota", "degraded": True,
                      "persisted": False, "refused": False,
                      "degraded_reason": reason}, sort_keys=True))
    return EXIT_OK


def _main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True,
                    help="key under `projects` in config/build-budget.json")
    ap.add_argument("--state-uri", required=True,
                    help="gs://bucket/object (production) or file:///path (dev)")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), type=Path)
    ap.add_argument("--build-id", default=os.environ.get("BUILD_ID", "unknown"))
    ap.add_argument("--allow-nonatomic-store", action="store_true",
                    help="permit a non-CAS store while enforcing (dev only)")
    ap.add_argument("--trigger-name",
                    default=os.environ.get("TRIGGER_NAME", ""),
                    help="the Cloud Build trigger that started this build "
                         "($TRIGGER_NAME). Decides gateability against the "
                         "SAME `gate_triggers` list the hourly gate reads "
                         "(issue-8237).")
    ap.add_argument("--now", type=float, default=None,
                    help="override the clock (tests)")
    a = ap.parse_args(argv)

    now_ts = a.now if a.now is not None else time.time()
    break_glass = _break_glass_from_env()

    # Build the store FIRST so a config failure can still be COUNTED — the
    # store is fine in that case, and an uncounted degraded build is exactly the
    # override-nobody-counts this design refuses to allow.
    try:
        st = store_mod.from_uri(a.state_uri)
    except ValueError as e:
        d, persisted = _degraded(a.repo, str(e))
        emit(d, build_id=a.build_id, store_uri=a.state_uri, persisted=persisted)
        return EXIT_OK

    pcfg, why = load_repo_config(a.config, a.repo)
    if pcfg is None:
        d, persisted = _degraded(a.repo, why or "config", st)
        emit(d, build_id=a.build_id, store_uri=a.state_uri, persisted=persisted)
        return EXIT_OK

    enforcing = bool(pcfg.get("enforcing"))
    # The REPO's declared setting, kept separate from the per-trigger downgrade
    # below. The store guard further down needs this one: its subject is
    # COUNTING accuracy, and an ungated build is still counted.
    repo_enforcing = enforcing
    daily_total = int(pcfg["daily_build_count"])

    # 🔴 issue-8237 — THE DEPLOY PATH IS NOT REFUSABLE, and it reads the SAME
    # list the hourly gate reads rather than a second one.
    #
    # `gate_triggers` says which triggers the hourly gate MAY close, and its
    # exclusions are the safety property: `gate.py`'s docstring states outright
    # that "deploy triggers are never gated", because closing them breaks
    # shipping rather than saving money. This step had no exclusion vocabulary
    # at all — it keyed only on WHICH CONFIG carries it — and both
    # `ensemble-build-orch-push` (deploy) and `-pr` (test) run one config, so it
    # could not tell them apart. It refused a deploy build 13 seconds after the
    # very PR that added the step, and the fix for that would have been trapped
    # behind the same counter.
    #
    # Shadow, not skip: `enforcing=False` still DEBITS and still reports
    # `would_refuse`, so the deploy build stays in the count it genuinely
    # consumed. Skipping the charge would make the counter drift optimistic in
    # exactly the direction that hides overspend.
    #
    # UNKNOWN TRIGGER FAILS OPEN. An empty `$TRIGGER_NAME` is a manual
    # `builds submit` — a deliberate human act — and per this subsystem's
    # standing rule a budget that fails closed converts every bug in it into an
    # outage. It is still counted, and the banner names it.
    ungated_trigger: Optional[str] = None
    if enforcing:
        gateable = pcfg.get("gate_triggers") or []
        if a.trigger_name not in gateable:
            ungated_trigger = a.trigger_name or "(no TRIGGER_NAME — manual build)"
            enforcing = False

    # 🔴 A non-atomic store under enforcement silently under-counts, and an
    # under-count looks exactly like a quiet day. Refusing the COMBINATION (not
    # the store) keeps `file://` useful for local runs while making the unsafe
    # pairing something a human had to type.
    # 🔴 `repo_enforcing`, NOT `enforcing` — issue-8237. The per-trigger
    # downgrade above turns enforcement off while leaving COUNTING on, and this
    # guard is about counting: a non-CAS store silently under-counts, and an
    # under-count looks exactly like a quiet day. Keying it on the downgraded
    # flag would have exempted the deploy path — the highest-value build there
    # is — from the very check that keeps its charge honest.
    if repo_enforcing and not getattr(st, "atomic", False) and not a.allow_nonatomic_store:
        d, persisted = _degraded(
            a.repo, f"{st} cannot compare-and-swap and {a.repo} is enforcing; "
                    f"pass --allow-nonatomic-store if that is intended", st)
        emit(d, build_id=a.build_id, store_uri=a.state_uri, persisted=persisted)
        return EXIT_OK

    decision, persisted, why = charge(
        st, repo=a.repo, daily_total=daily_total, enforcing=enforcing,
        break_glass=break_glass, now_ts=now_ts)
    if decision is None:
        d, persisted = _degraded(a.repo, why or "unknown", st)
        emit(d, build_id=a.build_id, store_uri=a.state_uri, persisted=persisted)
        return EXIT_OK

    emit(decision, build_id=a.build_id, store_uri=a.state_uri,
         persisted=persisted, ungated_trigger=ungated_trigger)
    return EXIT_REFUSED if decision.refused else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
