# `e2e/` — render-level checks, deliberately outside the product tree

Nothing in here is a dependency of the app. `ui/package.json`,
`ui/package-lock.json`, `ui/src/**` and `backend/app/**` are untouched by
design, per `docs/itp-playwright-usability.md` §2.4.

## `tap_targets.py` — the 44px floor, measured rather than declared

```bash
python3 e2e/tap_targets.py --self-test      # validate the detector itself
python3 e2e/tap_targets.py                  # measure prod, mobile + desktop
python3 e2e/tap_targets.py --url http://localhost:3000 --viewport mobile
```

`ui/src/styles/tapTargets.test.js` checks that the CSS *declares* a ≥44px floor
and says in its own docstring that it cannot speak to the rendered box. It was
green throughout the period when 23 of 33 controls on the live mobile site
rendered under 44px. This measures the rendered box.

**Read the module docstring before changing it** — the three-state exit, the
regex-form analytics block, and the self-test are each there for a stated
reason, and each has a failure mode that looks like success if removed.

### Exit codes are three-state on purpose

| exit | meaning |
|---|---|
| 0 | `PASS` — every visible control measured at or above the floor |
| 1 | `FAIL` — at least one measured under it, or an analytics beacon completed |
| 2 | `BLIND` — could not measure (navigation failed, or zero controls found) |

`BLIND` exists so that "I could not look" can never be reported as "the page is
clean", which is the most likely way for a check like this to start lying.

### Why it is not a PR gate yet

Prod currently **fails** it (23 undersized on mobile, 16 on desktop). Turning it
into a blocking gate before the fix lands would red every PR, and a gate people
routinely override stops being a gate — the override becomes the habit. Order:
harness (this) → fix the controls → then gate.

### Scope today

The public landing page only, which needs no session and already reproduces the
defect. The authenticated/guest journeys in
`docs/itp-playwright-usability.md` are not covered yet. **Never** click
"Sign in with Google" when extending this; use the guest path, and keep the
analytics abort installed on the context before the first navigation.
