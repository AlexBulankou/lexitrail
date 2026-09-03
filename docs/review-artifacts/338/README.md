# lexitrail#338 — landscape practice grid, before/after (PR #339)

Review artifacts for the `maxRows = 0` fix. Requested by hc2@ on #339: the numeric harness table
alone could not answer whether four cards actually *fit* — `visible == total` is a proxy for
"looks right", not a substitute.

Captured from **locally-served production builds**, both arms in the same session with the same
script, so the layout change is the only variable:

- **before** — `origin/main` at `c55d179`
- **after** — `issue-338-landscape-layout` rebased onto that same commit

Both dismiss the first-visit *"How it works"* modal before capture. ⚠️ The first pass did not,
and the modal covered the grid — the screenshots were of the modal. Worth knowing for the next
capture: `enter_practice` leaves it up.

## The change

| viewport | before | after |
|---|---|---|
| **landscape 844×390** | **1 card**, `layout1c1r` | **4 cards**, `layout4c1r` |
| portrait 390×844 | 2 cards, `layout1c2r` | 2 cards, `layout1c2r` — unchanged |
| desktop 1440×900 | 10 cards, `layout8c2r` | 10 cards, `layout8c2r` — unchanged |

The one-card state was not a choice: `maxRows = floor((390 − 200) / 280) = 0` emptied the layout
option list, so `setLayoutClass` was never called and the grid kept `useState('layout1c1r')`.

## Fit, measured — hc2@'s question

| | landscape after |
|---|---|
| horizontal overflow | **none** — `scrollWidth 844 == clientWidth 844` |
| cards clipped right | **0** — the row spans x=87…757 inside 844 |
| overlapping pairs | **0** — all pairs tested, none intersect |
| card rects | 4 × 160w at x = 87 / 257 / 427 / 597, uniform 10px gutters |

**Vertical clipping is pre-existing and unchanged.** Cards are `y=130 h=291 bottom=421` in a
390-tall viewport in **both** arms — identical geometry, and `scrollHeight/clientHeight` is
`513/390` before and after. The card is taller than the viewport either way; the page scrolls.
This PR changes how many cards sit in the row, not their size, so it neither introduces nor
worsens the clipping.

## Files

```
before-mobile_landscape-844x390.png   one card, centred, dead space both sides
after-mobile_landscape-844x390.png    four cards filling the row
before-mobile-390x844.png             \  unchanged pair, included as the control:
after-mobile-390x844.png              /  the floor touches the shared path
before-desktop-1440x900.png           \
after-desktop-1440x900.png            /
```

The portrait and desktop pairs are the point of including them — a change to the shared sizing
path could regress them silently, so they are shown to be identical rather than asserted to be.
