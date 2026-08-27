# Social / OG creative generator

Generates Lexitrail's per-platform social creatives. Closes lexitrail#63.

```bash
cd tools/og
npm install
npm run generate            # all presets
npm run generate -- --preset ig-portrait
npm test                    # the AC2 artifact guard
```

Output lands in `ui/public/images/og/generated/` and is committed, so the app
and the marketing publisher can reference stable URLs without a build step.

## Why this exists

Every impression on every channel used **one byte-identical 1200×630 file**,
`ui/public/images/og/hsk2-practice.png`, which was a raw screenshot of a live
practice session. (That file no longer exists in the tree — it and 17 sibling
demo captures were deleted in issue-172; this paragraph is history, not a path
you can open.) Two separate problems were bundled in that:

**Aspect.** 1.905:1 is *correct* for a link-preview card and wrong for all three
feed platforms we post to, in the expensive direction — landscape letterboxes
inside a vertical feed. So the fix is not "stop using landscape", it is one asset
per surface, landscape included.

**Provenance.** Because it was a capture, it shipped the capture environment:
a demo-account email (`4usvy@lexitrail.demo`), `recalled 0 out of 149`, two
zeroed score counters, a running `0:17` timer, the nav bar, and one card that
hadn't finished loading. The dominant message of the whole organic surface was a
user who had learned none of the deck, seventeen seconds in — the picture argued
the product doesn't work.

The design language here follows FamilyLore's `og-image.png`, which had already
solved the same problem: badge, wordmark, headline, one-line mechanism, coverage
list, and a panel showing a real sample of the actual artifact. FL's is a static
hand-made file with no generator, so this is the mechanism FL doesn't have.

## Layout

| preset | size | ratio | surface |
|---|---|---|---|
| `og-landscape` | 1200×630 | 1.91:1 | `og:image` / `twitter:image` link previews |
| `ig-square` | 1080×1080 | 1:1 | Instagram feed |
| `ig-portrait` | 1080×1350 | 4:5 | Instagram feed (largest slice IG allows) |
| `pinterest` | 1000×1500 | 2:3 | Pinterest standard |
| `tiktok` | 1080×1920 | 9:16 | TikTok / Reels / Stories |

`template.html` has two arrangements, chosen per preset: `split` (pitch beside
the sample — only readable in landscape) and `stack` (pitch above).

## The three gates

Generation refuses rather than writing a bad asset. Each gate exists because the
corresponding failure actually happened.

**1. Artifact gate (`forbidden.mjs`, AC2).** Scans the *resolved text* — copy plus
every sample card — for capture-environment artifacts: demo addresses, `N of M`
counters, score chrome, timers. It checks resolved data rather than the template
because that is the path the artifacts took the first time. `npm test` asserts it
**fires** on each real artifact read off the old asset, and separately that it
stays quiet on the approved copy and on real vocabulary rows — a guard stuck in
the firing position blocks everything and still looks like it works.

*Limitation, stated plainly:* it reads text, not pixels. It cannot catch an
artifact baked into an embedded raster. Look at the PNGs.

**2. Canvas-overflow gate.** Fails if any box escapes the canvas. Caught the
first render of `ig-portrait` and `ig-square` slicing their bottom card row.

**3. Card-clip gate.** Fails if content escapes its own card. This one exists
because of a mistake worth recording: `.card` was given `overflow: hidden` to
make gate 2 pass, which converted a visible overflow into a *silent clip* —
glyphs spilling over the card top and glosses sliced off, while
`document.scrollHeight` came back exactly equal to the canvas and gate 2
reported clean. Suppressing the symptom the detector measured made the detector
blind. Gate 3 measures the right population: per-card `scrollHeight` vs
`clientHeight`, plus each child's rect against its card's.

## Shrink-to-fit

Hand-tuning `vmin` values until five aspect ratios happen to fit is not a
generator — it is a human re-cropping one file with extra steps, and it silently
re-breaks the next time the copy or card count changes. So the generator finds
its own scale: it shrinks card type (`--fit`, floor 0.6) until gate 3 is
satisfied, reports the value it settled on, and fails loudly if the floor isn't
enough. That last case means the design genuinely can't hold that much content at
that aspect, which is a decision for a person, not a scale factor.

Current run: everything sits at `fit=1` except `ig-square` at `0.98`.

## Copy

`copy.json`, separate from template and generator so wording can change without
touching the mechanism. Each string carries its provenance; all of them derive
from what the site already says about itself except the headline, which is
flagged there as an open question for review.

## Regenerating

Deterministic — same inputs give byte-comparable output, because the sample words
are picked by a fixed stride rather than at random. A reviewer can therefore tell
a copy change from a reshuffle.

Two caveats:

- **Fonts.** Glyphs render with whatever CJK font the machine has (here
  WenQuanYi Zen Hei). A machine with different fonts installed produces
  visibly different output, so regenerate deliberately rather than incidentally.
- **Chromium build.** If playwright's bundled browser isn't the one installed,
  point `PLAYWRIGHT_CHROMIUM_EXECUTABLE` at the binary. That error reads like a
  missing browser and is not one — misreading it that way cost real time.

## Not done here

Pointing the app and the publisher at these files is deliberately **not** in this
change:

- `ui/public/index.html` and `ui/src/components/SEO.js` still reference
  `hsk2-practice.png`.
- The marketing publisher's `LT_IMG` (`~/.ensemble/marketing/refill_horizon.py`)
  still points at the old URL, and lives outside this repo.

Switching those is a live-traffic change that wants the copy signed off first,
and the publisher edit isn't a lexitrail commit. The assets exist and are
verified; the cutover is its own step.
