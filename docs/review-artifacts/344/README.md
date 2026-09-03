# lexitrail#344 — Test-mode answer reveal (PR #346)

Requested by hc2@ on review: a UI-significant PR with only a timing table. They were right, and
the screenshots caught a defect no number in that table could.

Captured from a locally-served production build of this branch, Test mode, after a **wrong** pick.

## 🔴 What the screenshots caught that the measurements did not

The first build set only `background-color` on the highlighted option. The quiz buttons inherit
**white** text from the blue default, so the correct answer rendered **white on pale green** —
nearly unreadable, i.e. exactly the thing the feature exists to show. Every geometry and timing
assertion was green at the time.

Fixed by setting `color: #1b5e20` explicitly. Measured after:

```
correct option   color rgb(27,94,32)   bg rgb(232,245,233)   font-weight 400
other options    color rgb(255,255,255) bg rgb(44,108,211)    unchanged
```

`font-weight: bold` was also dropped: the pinyin already fills these buttons, so bolding widens it
and the highlight would clip the text it is highlighting.

## Fit, all three viewports, on the reveal frame

```
viewport             reveal visible   card flipped   cards   overlaps   clipped right   h-overflow
desktop 1440x900           1               1          16         0           0              0
mobile   390x844           1               1           1         0           0              0
landscape 844x390          1               1           4         0           0              0
```

Landscape shows four cards because of #339 — hc2@ asked specifically about that grid, since #346
lands on top of it.

## Files

```
before-{desktop,mobile,mobile_landscape}.png      Test mode, nothing answered
after-reveal-{desktop,mobile,mobile_landscape}.png  immediately after a wrong pick
```

⚠️ In the landscape frame the highlighted option sits **below the fold** — the card is taller than
a 390px-tall viewport, so its option row is cut off. That is **#341**, pre-existing and unchanged
by this PR (identical card geometry before and after, measured on #339). It is visible here because
this is the first artifact set that shows the option row at all.
