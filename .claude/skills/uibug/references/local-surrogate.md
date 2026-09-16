# The local surrogate — when, and what it costs

A surrogate is a local build of the repo served over HTTP and swept as if it were
the site. It is legitimate for exactly two jobs:

1. **Re-measuring a fix.** A geometric bug needs its number to move, and jsdom
   unit tests cannot render a box. Measure the patched tree here.
2. **Working while the public URL is unreachable** — but only after telling the
   user the live target is blocked and getting a go-ahead.

## What it is not

It is **not** evidence about production. The deployed bundle can differ from
`HEAD` (different commit, different build flags, a CDN transform), and the live
API is replaced by whatever the local build talks to. A finding measured here is
a finding about *this tree*, and every PR that rests on one must say so in the
same sentence as the measurement — "measured on a local build of `<sha>`, not on
the live site, because `<host>` is blocked by the environment's egress policy".

Never present a surrogate measurement as a live-site measurement. The premise of
this skill is that the deployed artifact is what gets graded; quietly swapping in
a local build removes the only thing that made the report worth reading.

## Running one

```bash
cd ui && npm ci && npm run build
npx serve -s build -l 3000        # or: python3 -m http.server 3000 -d build
```

`-s`/SPA-rewrite matters: without it every client route 404s and the sweep goes
BLIND on everything except `/`. With `python3 -m http.server` you only get `/`,
so prefer a rewriting server.

Then:

```bash
node harness/run.js --url http://localhost:3000 --env both --out /tmp/uibug/local --skip-reach
```

`--skip-reach` is required because the preflight expects a public origin.

## Before/after discipline

Measure the SAME route on the SAME viewport, unpatched then patched, and quote
both numbers. A fix with only an "after" number has not been shown to have done
anything.
