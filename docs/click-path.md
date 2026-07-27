# How traffic is meant to reach Lexitrail from social

Written for lexitrail#64 AC3: *"Decide + document how IG/TikTok traffic is meant to
reach the destination given non-tappable caption URLs."*

## The short version

The redirects work. The click path from Instagram and TikTok does not, and no
redirect can fix it, because **neither platform makes a URL in a caption tappable**.
Every Lexitrail caption on those two channels currently prints a ~78-character URL
that a reader would have to retype by hand.

Per-channel, as of 2026-07-27:

| channel | can a post link out? | current state |
|---|---|---|
| Instagram feed | **no** — captions are not linkified | prints an untappable URL |
| TikTok | **no** — captions are not linkified | prints an untappable URL, and has no `/go/` route at all |
| Pinterest | **yes** — each pin carries a destination URL | the only channel that can click |
| X | yes — links are tappable | `/go/x-*` routes exist and work |

## What was verified, and how

Browser navigation from a clean context, not curl and not a status code
(`tools/clickpath/verify.mjs`):

- All six `/go/*` routes in `ui/public/serve.json` redirect properly: real 302, one
  hop, UTM preserved, real page rendered.
- **So #64's premise is wrong.** "SPA-served with no server-side redirect" was
  based on an assumption that prod runs nginx. It runs `serve -s build`
  (`ui/Dockerfile`), which is the package that reads `serve.json`.
- The genuine trap is the opposite one: prod rewrites `**` → `/index.html`, so a
  dead path returns **200** and renders the 404 component. `/hsk2` does exactly
  that today.

## The gap the redirects can't close

`make_link()` in the publisher (`~/.ensemble/marketing/refill_horizon.py`, outside
this repo) builds:

```
https://lexitrail.com/?utm_source=instagram&utm_medium=social&utm_campaign=lt_hsk
```

and the captions inline it — `"Try HSK practice free → {link}"` on Instagram, and on
TikTok the caption is the bare `{link}` on its own line. On both platforms that
string is plain text. It is not merely useless; a long query-string URL in a caption
reads as spam and costs credibility.

Two further gaps in the same area:

1. **`/go/*` is wired to nothing.** `make_link()` never emits a `/go/` path, so the
   short links exist and are correct and are used by nobody. Tracked as
   lexitrail#66. Attribution is *not* lost by this — the UTM is identical either
   way — so it is a cleanup, not an outage.
2. **No TikTok or Pinterest routes exist.** `serve.json` has `ig-*` and `x-*` only.

## The decision

**For Instagram and TikTok, the caption stops carrying a URL, and the profile bio
carries the link.** That is the only tappable affordance either platform offers a
feed post.

Concretely:

1. Add `/go/ig-bio` and `/go/tt-bio` to `serve.json`, each redirecting to the root
   with `utm_medium=social` and a per-platform `utm_source`.
2. Set each profile's bio link to the short URL. Operator step — it is a change in
   the Instagram and TikTok apps, not in this repo.
3. Change the IG and TikTok captions to say *"link in bio"* and stop interpolating
   `{link}`. Publisher change, so it lands in `refill_horizon.py`, not here.
4. Leave Pinterest and X as they are. Both can link out; Pinterest should use the
   destination URL field rather than the caption.

**Accepted cost:** a bio link is one URL for the whole profile, so attribution drops
from per-campaign to per-platform on those two channels. That is the correct trade —
per-campaign attribution on a link nobody can tap is worth nothing, and the platform
offers no alternative. X and Pinterest keep per-campaign granularity.

**Not done here, deliberately:** steps 1–3 are a live-traffic change spanning two
repos plus two operator actions in the platform apps. This document is the decision
and the rationale; the implementation wants a lead/Alex sign-off first, because
step 3 changes what every future post says.

## Why this matters more than it looks

Zero click-through from Instagram and TikTok is the *expected output of this
configuration*, not a verdict on the copy or the creative. Any read of channel
performance that treats IG/TikTok CTR as a signal about content is measuring
something that was never physically possible.
