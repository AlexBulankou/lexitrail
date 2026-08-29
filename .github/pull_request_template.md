<!-- Keep this short. A long template gets deleted wholesale, which is worse
     than no template: it trains people to clear the box rather than answer it. -->

<!-- `closes #N` auto-closes on merge; `refs #N` does not. The walker matches the
     TEXT, so "doesn't close #N" and "closes #N partially" BOTH close it. -->
refs #

## What

<!-- One or two sentences: what merging this does, not how it is implemented. -->

## Deploy reach — answer this, do not delete it

<!-- 🔴 THE ONE SECTION THIS TEMPLATE EXISTS FOR (lexitrail#77).
     `lexitrail-backend-deploy-main` is NAMED "deploy" and does NOT deploy: it
     builds and pushes, while the Deployment is pinned BY DIGEST, so
     imagePullPolicy: Always is inert and nothing rolls. On 2026-08-29 a
     backend PR merged, the build went SUCCESS, and the deployment had not
     moved four minutes later -- approved by two reviewers, neither of whom
     asked. A green build after a merge looks identical either way, so the
     thing that did not happen leaves no artifact. -->

- [ ] **Nothing to deploy** — no `ui/**` or `backend/**` change.
- [ ] **UI** (`ui/**`) — merging builds *and rolls*. Verify at the wire after merge.
- [ ] **Backend** (`backend/**`) — merging builds but **does NOT roll**. The manual
      `kubectl set image` + digest read-back + `scripts/smoke_served_content.py`
      in `cloudbuild.yaml`'s header is required, by me, after merge.

## Test plan

<!-- What you RAN, with its output. If a check could only have returned the
     answer you wanted, say so -- a control that cannot fail is not a control. -->

## Cost

<!-- Both triggers use includedFiles (an ALLOWLIST): a path outside them does
     not build. `ui/**` + `cloudbuild-ui.yaml`, `backend/**` + `cloudbuild.yaml`.
     Everything else -- scripts/**, e2e/**, terraform/**, .github/**, README --
     merges for 0 units. There is no PR-event trigger, so OPENING a PR and
     pushing to it are always free; only the merge can cost.

     Spendable now is `accrued - used`, NOT `daily_total`. Walk accrued() per
     minute; never read refills_at_ts, which has been measured hours early. -->

- Merging this costs: **0 / 1** unit
