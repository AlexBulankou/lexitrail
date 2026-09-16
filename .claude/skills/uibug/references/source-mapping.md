# Step 3 — rendered element → `file:line`

The goal is a sentence like:

> `.cards-area` measured 592px tall on 390×844 because
> `ui/src/styles/Game.css:212` sets `height: calc(100vh - 252px)` and the navbar
> is 48px, not the 44px that constant assumes.

Anything vaguer than that is not a source mapping, and a fix built on it is a guess.

## Procedure

1. **Start from the DOM record, not the screenshot.** Open
   `dom/<viewport>/<NN>-<route>.json`, find the element the detector flagged, and
   copy its `cls` and `box`.

2. **Find the rule that produces the box.** The class list is the search key:
   ```bash
   grep -rn "\.cards-area" ui/src/styles/
   grep -rn "cards-area" ui/src/components/   # who emits it
   ```
   Match on the *specific* property the measurement is about (`height`, `padding`,
   `overflow`, `min-width`), not on the first hit for the class.

3. **Check JS layout before concluding it is CSS.** `Game.js` `updateLayout()` and
   `utils/cardLayout.js` compute columns, rows and font size from `window` size, so
   a box can be wrong with every CSS rule correct. Symptom that points here: the
   value is right on one viewport and wrong on the other, with no media query
   between them.

4. **Confirm the direction of causation.** Change the suspected declaration
   locally, re-measure with the surrogate (`references/local-surrogate.md`), and
   check the measured number moves the way you predicted. If it does not, you have
   the wrong rule — a fix that happens to hide a symptom will resurface.

5. **Write down the chain** for the PR body: rendered class → file:line →
   declaration → why it produces the measured box.

## Traps this repo has already fallen into

- **A declared floor is not a rendered box.** `ui/src/styles/tapTargets.test.js`
  asserts the CSS declares ≥44px and stayed green while 23 of 33 live controls
  rendered under it. Never close a geometric bug on a source-only check.
- **The class you see may not be the one that wins.** Check specificity and later
  overrides, especially `Global.css` vs component CSS.
- **`overflow:hidden` + `flex-end` clips the *oldest* item**, not the newest —
  the `.mastery-indicator` tile row is built this way. Measure `scrollWidth` vs
  `clientWidth`; the screenshot shows only what survived.
- **One rule, many symptoms.** Two flagged elements that share a parent rule are
  one bug. File it once, at the cause.
