# `zz1-social-refill-lt.service` failed — what it costs, and what to do

You are probably here because a `#7638` Slack alert named the unit. That alert reports a
**unit**, not a consequence — closing lexitrail#334's AC2, which observed that the page
says `` `zz1-social-refill-lt.service` `` and nobody had written down what its failure
means.

## 🔴 STEP 0 — which fire failed? The two answers are opposite.

**Do not skip this.** The modal page is the *harmless* case, so a reader who assumes the
alarming one and acts on it is wrong most of the time.

```bash
journalctl --user -u zz1-social-refill-lt.service --since "7 days ago" -o short-iso \
  | grep -E "Finished|Failed with result|refusing"
```

⚠️ **7 days, not 36 hours, and the window is load-bearing.** Step 3 below escalates on
*"failing for three or more days"* — a 36h window **structurally cannot see that case**, so
the recipe would be blind to the exact condition the rule exists for. And because the
alerter is delta-gated (below), a run of consecutive failures pages **once**: you can
arrive days after the page, get only `Finished` lines in a short window, and match neither
row of the table. The 7-day output is ten lines.

🔴 **Use those exact tokens.** systemd logs a success as **`Finished`** — *not* `Succeeded`,
*not* `Started` (which a failed run prints too). A grep for the wrong word returns the
failure and no success, which reads as *"it never recovered"* and sends you down the wrong
branch. This is not hypothetical: the first draft of this section shipped
`grep -iE "Started|Succeeded|fail|refus"`, and against the real journal it hid all six
successes below.

| what you see | what it means | do |
|---|---|---|
| a failure, **then a later `Finished`** | a **boot replay** failed; the scheduled fire did its job | nothing — record it and stop |
| the most recent line is a failure, **no `Finished` after it** | the refill genuinely did not happen | continue below |

⚠️ **The first row is the common one, and it is what a page usually means.** A second
discriminator that needs no success line at all: **scheduled fires land at ~02:0x PDT
(~09:0xZ); a boot replay lands at an odd hour.** Measured on bp:

```
08-31 02:05:04 PDT  Finished          <- scheduled
09-01 00:08:42 PDT  Failed             <- replay #1
09-01 02:02:13 PDT  Finished          <- recovered ~2h later, same pattern
09-02 02:05:45 PDT  Finished          <- scheduled
09-02 22:20:42 PDT  Failed  "refusing to run a refill off a checkout of unknown age"
09-03 02:01:00 PDT  Finished          <- replay #2 recovered, next morning
09-04 / 09-05 / 09-06 / 09-07 02:0x   Finished, Finished, Finished, Finished
```

The 22:20 PDT timestamp alone tells you it was a replay. Measured at filing: **12 of 12**
on-schedule fires finished, **0 of 4** `Persistent=true` boot replays did.

📌 This section exists because the first version of this runbook opened with *"LexiTrail's
queues did not get topped up today"* — which contradicted its own 12/12-vs-0/4 split for
the modal case (adm@, reviewing lex#399). The body was right and the headline was the part
a reader acts on first. Left as a note rather than a silent rewrite: **a one-liner that
disagrees with the evidence three paragraphs below it is not a wording problem, it is the
only sentence most readers will use.**

## If the refill genuinely did not run

**LexiTrail's Instagram and Pinterest queues did not get topped up.** Posting does not stop
immediately; it stops in about three days.

## What the unit does

`zz1-social-refill-lt.timer` fires on bp (user scope, ~09:00Z) and tops `lt_ig` and
`lt_pin` up to **3 posts ahead**. It is the only thing that refills them.

## 🔴 Why one failure looks like nothing

The buffer absorbs it. A skipped day drops depth 3 → 2 and **posting continues normally**.

⚠️ That is also why `check_organic_queue_depth.py` does **not** cover this: it fails loud
on an *empty* channel, which is roughly three consecutive skips away — by which point
posting has already stopped. Two observers, two different questions:

```
did the refill RUN?     zz1-social-refill-lt.service  -> the failed-units audit (~15 min)
is the queue EMPTY?     check_organic_queue_depth      -> ~3 skips too late for this
```

## ⚠️ You will not get one page per skipped day

The failed-units audit is **delta-gated** (`new = failing - last_seen`, #7643). Consecutive
failures with no success between them page **once**. A unit that succeeds and then fails
again pages again — the normal daily shape — but a run of back-to-back failures is one
alert, not one per day.

⇒ **Do not count pages against skipped days.** Check the unit's own history:

```bash
systemctl --user status zz1-social-refill-lt.service
journalctl --user -u zz1-social-refill-lt.service --since "7 days ago" -o short-iso \
  | grep -E "Finished|Failed with result|refusing"    # BOTH outcomes — see step 0
```

## The two known failure messages, and what they mean

Both are `git` on the shared canonical clone, not anything LexiTrail-side:

```
git reset --hard origin/main failed in ~/.ensemble/decipher-refill
git fetch failed — refusing to run a refill off a checkout of unknown age
  error: cannot lock ref 'refs/remotes/origin/main':
         is at 9cbbdce9 but expected c67513df
```

The second is a **compare-and-swap loss**: git read the ref and something else moved it
underneath. ⚠️ The other writer is **not identified** (lexitrail#334 says so explicitly) —
it is outside the set of user units that fetch `CANON`. Do not assume it is a second copy
of this script.

📌 Measured shape at filing: **12 of 12** on-schedule fires finished; **0 of 4**
`Persistent=true` boot replays did. If that split still holds, the fault is in the replay
path, not the schedule.

## What to do

1. Re-run it: `systemctl --user start zz1-social-refill-lt.service`, then check the queue
   depth for `lt_ig` and `lt_pin`.
2. If it fails again on a git message, the clone is the problem, not the refill — this is a
   zz1-owned unit on bp and the clone is shared.
3. If it has been failing for **three or more days**, treat posting as stopped rather than
   degraded and say so, because the depth check will not have fired yet either.

Refs lexitrail#334, lexitrail#71, ensemble#7638, ensemble#7643.
