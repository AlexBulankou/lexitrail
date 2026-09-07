# `zz1-social-refill-lt.service` failed — what it costs, and what to do

**One line: LexiTrail's Instagram and Pinterest queues did not get topped up today.**
Posting does not stop immediately; it stops in about three days.

You are probably here because a `#7638` Slack alert named the unit. That alert reports a
**unit**, not a consequence — closing lexitrail#334's AC2, which observed that the page
says `` `zz1-social-refill-lt.service` `` and nobody had written down what its failure
means.

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
journalctl --user -u zz1-social-refill-lt.service --since "7 days ago" | grep -iE "fail|refus"
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
