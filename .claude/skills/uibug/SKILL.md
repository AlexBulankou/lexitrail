---
name: uibug
description: Find and fix UI/logic bugs on the live Lexitrail site. Use when asked to run /uibug, hunt for UI bugs, layout breaks, overlapping elements or broken logic on a deployed URL, or to produce bug-fix PRs backed by live-site screenshot evidence. Drives Playwright against a public URL across desktop and mobile viewports, maps each defect to its source file, fixes it, and opens a PR per bug.
---

# uibug — live-site bug hunt → source map → fix → PR

`/uibug <count> <environment>` finds exactly `<count>` bugs on the live site for
`<environment>` (`desktop` | `mobile` | `both`), maps each to source, fixes it,
and opens a PR per bug carrying the live URL and a before-screenshot.

Default URL is `https://lexitrail.com`; override with `--url <url>`.

## The one rule that makes this skill worth running

**A finding must be measured on a rendered page, never inferred from source.**
Reading `Game.css` and reasoning "that probably overflows" is not a finding. A
finding is a number the harness read off a live DOM box, or a pixel a vision
pass saw in a screenshot. `e2e/tap_targets.py` in this repo exists precisely
because `ui/src/styles/tapTargets.test.js` was green for the whole period that
23 of 33 live controls rendered under 44px — the source *declared* a floor the
render did not honor. Keep that asymmetry in mind: source lies, the box does not.

Corollary: **never report a bug you could not measure.** The harness is
three-state (`PASS` / `FAIL` / `BLIND`) for this reason — see
`references/harness.md`. If a route failed to load, say BLIND and find a
different bug; do not fill the quota with a source-read guess.

## Workflow

### 0. Preflight (do this before promising anything)

```bash
bash .claude/skills/uibug/harness/setup.sh            # idempotent; installs @playwright/test
node .claude/skills/uibug/harness/reach.js <url>      # is the target actually reachable?
```

This skill needs outbound network access to **both** `lexitrail.com` and
`api.lexitrail.com` — the SPA is served by the first and gets every word from the
second, so a session allowed only the first reaches the app and then measures its
error state. Check both.

`reach.js` exits 2 (BLIND) when egress policy blocks the host. **If the public
URL is unreachable, stop and tell the user** — name the blocked host and that
the environment's network policy governs it. Do not silently substitute a local
build for the live site: the whole premise is that the deployed artifact is what
gets graded. If the user then asks for a local surrogate, see
`references/local-surrogate.md` and label every finding as surrogate-measured.

### 1. Sweep — measure, don't guess

```bash
node .claude/skills/uibug/harness/run.js --url <url> --env <desktop|mobile|both> --out <dir>
```

One sweep walks every route in `references/source-map.md` on each requested
viewport, and per route emits into `<dir>`:

- `screens/<viewport>/<NN>-<route>-<state>.png` — full-page screenshot
- `dom/<viewport>/<NN>-<route>.json` — every visible element's box, computed
  style, text and class list
- `findings.json` — what the geometric detectors flagged, with measurements

The detectors (`harness/lib/detectors.js`) cover what arithmetic can settle on
its own: **overlap** (two interactive boxes intersecting), **overflow**
(content past the viewport or past its own container), **clipping** (scrollWidth
> clientWidth on an `overflow:hidden` box), **tap targets** (< 44px), **contrast**
(WCAG AA on text), and **dead controls** (a handler-less `<button>`, an `href="#"`).

Then read the screenshots yourself. The detectors find geometry; **you** find
aesthetics and broken logic — misalignment, inconsistent spacing, a wrong label,
a state that renders the wrong screen. Both sources count as findings; a
vision-only finding still needs a screenshot and a DOM box to anchor it.

### 2. Triage to exactly `<count>`

Rank by user impact, then take the top `<count>` **for the requested
environment**. A bug is "desktop" or "mobile" by where it *reproduces*, not
where you happened to look — the harness records both viewports for every route
so you can tell the difference. Prefer, in order: broken logic > layout break >
overlap > aesthetic flaw. Drop duplicates of the same root cause; two symptoms
of one CSS rule are one bug.

### 3. Source-map each bug

Work from the rendered element back to the file — see
`references/source-mapping.md` for the full procedure. In short: take the
element's class list from `dom/`, grep it in `ui/src/styles/**`, grep the JSX
that emits it in `ui/src/components/**`, and confirm the declaration that
produces the measured box. **Name the exact rule**, e.g.
`ui/src/styles/Game.css:212 — .cards-area { height: calc(100vh - 252px) }`.
If you cannot land on a specific declaration, you have not mapped it; keep
digging or drop the bug.

### 4. Fix — one branch and one PR per bug

**One PR per bug, always.** Bundling the fixes into one PR forces a reviewer to
take all of them or none, and the first disagreement stalls the rest.


Each bug is independent, so keep them independent — a reviewer can take one and
leave another. Branch from the current default branch each time.

Fix the cause, not the symptom. Keep the diff minimal and in the product tree
(`ui/src/**`); the harness is not the deliverable.

### 5. Verify before you push

```bash
cd ui && CI=true npm test -- --watchAll=false     # existing suite must stay green
cd ui && npm run build                            # build must succeed
```

Add a regression test when the bug is expressible as one (`ui/src/**/*.test.js`
is jsdom + Testing Library — good for logic and for CSS *declarations*, blind to
rendered boxes). For a purely geometric fix, re-run the sweep against a local
build of the patched tree and show the measurement moving — `references/local-surrogate.md`.

### 6. PR body — evidence, not assertion

**The deliverable of this skill is pull requests.** Not a findings table, not a
markdown report, not a summary in chat. `<count>` bugs means `<count>` PRs, each
with a fix in it. A bug you can describe but did not fix and file is not output —
either land it or drop it from the count and say which.

Every PR body must carry all five, in this order:

1. **Where** — the public URL and route the bug was found on, plus viewport and
   the measurement (`measured 390×844: .card-footer bottom 912 > viewport 844`).
2. **Before screenshot — required, rendered inline, in every PR.** A reviewer must
   see the defect without leaving the page.
3. **Source mapping** — rendered class → file:line → the declaration at fault,
   and why that declaration produces the measured box.
4. **The fix** — what changed and why it is the cause and not the symptom.
5. **Verification** — test and build results, plus the re-measured number.

#### Getting the screenshot to actually render

A PR body cannot reference a path in a scratch directory, and the API has no
attachment upload. So **commit the evidence onto the bug's own branch** and embed
it by raw URL:

```
docs/uibug/<YYYY-MM-DD>/<bug-slug>-<viewport>-before.png   # committed with the fix
```

```markdown
![before](https://raw.githubusercontent.com/<owner>/<repo>/<branch>/docs/uibug/<date>/<slug>-<viewport>-before.png)
```

Use the **branch** in the raw URL, not a commit sha, so the image survives a
rebase. Crop or annotate to the defect where a full page would bury it, and keep
the uncropped original beside it. After opening the PR, **re-read the rendered
body and confirm the image loads** — a broken image is the same as no evidence.
An after-shot alongside the before is worth the extra commit for anything visual.

Use the repo's PR template if one exists. End GitHub comment bodies with the
Claude Code attribution footer.

## Guardrails (from `docs/itp-playwright-usability.md` §6 — these are not optional)

- **Analytics beacons must be aborted** before the first navigation, installed on
  the *context* via the regex form. `harness/lib/analytics.js` does this; it also
  counts completed beacons and **fails the run if any completed**. Never use the
  bare-glob form — `**/google-analytics.com/**` misses the real `www.` and
  `region1.` hosts and quietly poisons the GA4 funnel.
- **Guest auth only.** Enter via "Try without signing in"
  (`harness/lib/session.js`). **Never** complete a real Google sign-in, never
  create a real account, never attempt account deletion. Guest writes land under
  an isolated `@lexitrail.demo` identity — acceptable, but minimize them.
- **Never log, screenshot or commit a token**, including `sessionStorage.access_token`.
- **Keep Playwright out of the product tree.** It lives in this skill's
  `harness/` (and the repo's `e2e/`), never in `ui/package.json`.
- **Read-only against prod.** The only writes are the guest-session marks the
  journeys inherently make.

## References

| File | Read it when |
|---|---|
| `references/source-map.md` | routes, components, styles, live wordsets |
| `references/source-mapping.md` | step 3 — rendered element → file:line |
| `references/harness.md` | harness flags, exit codes, detector semantics |
| `references/local-surrogate.md` | the live URL is blocked, or you need to re-measure a fix |
