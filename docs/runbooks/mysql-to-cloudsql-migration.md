# Migrating lexitrail's DB off spot GKE onto managed Cloud SQL

**Author: mcl@** (lexitrail#358, Alex's assignment 2026-09-04). **Committed by hcl@**, who
holds the write access mcl@ does not: their App returns *Resource not accessible by
integration* on `addComment` and `push:false` on this repo, and adm@ confirmed their own
App has every permission false too — so it is an access boundary rather than an
mcl-specific gap.

This is a **straight copy** of the canonical entry in `p/lead-inbox/MCL.md` (2026-09-04
05:38Z), not a transcription from chat. That distinction is load-bearing: mcl@'s Slack
delivery of this runbook lost six spans to bash command substitution — including
`SUM(LENGTH(hint_img))`, the check that catches silent blob truncation — and the damaged
message stayed grammatical, so I read it without noticing. The lead-inbox copy was written
with a single-quoted heredoc straight to file and never went through that path.

## Sizing — measured 2026-09-04 by hcl@, not estimated

```
mysqldump --single-transaction --routines --triggers lexitraildb | wc -c
  111,649,898 B  = 106 MiB   <- what MIGRATES; the number the tier follows from

PVC used (df -B1 /var/lib/mysql)
  438,132,736 B  = 418 MiB of a 5Gi PVC (9%)   <- what the DISK holds
  ...lexitraildb 170 MB; the rest is binlogs (~49 MB each), #innodb_redo 101 MB, undo 2x16 MB
```

⚠️ These differ by 4x and both are "the database size". **#358's text says *check the PVC
used bytes* — that is the misleading one**, and sizing off it over-provisions 4x.

```
userwords   75.5 MB   29,354 rows   hint_img blob, ONE ROW PER (user, word)
words       53.8 MB    4,472 rows   hint_img blob, bounded by the catalogue
recall_history 13.5 MB 95,135 rows
users        0.2 MB    2,294 rows
=> 85% of the dump is hint_img BLOBs
```

---

Sized from HCL's measurement: **dump 106 MiB**, not the 418 MiB PVC figure #358 points at.

**Instance:** Cloud SQL for MySQL 8, smallest shared-core tier, **10 GB SSD** (the floor — at 106
MiB the tier decision is not close), **single-zone / no HA**, automated daily backups 7d, same
region as the GKE app, in `yojowa-claw`.

### The gate at every step: what makes this reversible, and how do I know it worked?

```
STEP                       REVERSIBLE BY                    VERIFY BEFORE PROCEEDING
1 provision instance       delete it (nothing points at it) RUNNABLE; connect as the app user
2 dump -> import           re-import; mysql-0 untouched     PER-TABLE row counts AND blob sums
3 repoint DATABASE_URL     revert env/secret, restart       /wordsets returns wordset_id, plus a
                                                            live Practice + Test round
4 soak 48h                 revert as step 3                 no errors; capacity alarm ARMED
5 decommission mysql-0     PVC snapshot taken BEFORE        only after 48h clean; keep snapshot 7d
```

🔴 **Step 2 verifies row counts AND blob lengths, never exit status.** `mysqldump` piped into
`mysql` exits 0 on a partial import more readily than people expect, and 85% of the dump is
`hint_img` blobs — so a row-count match with truncated blobs passes a count check and silently
loses user data.

```sql
SELECT 'userwords' t, COUNT(*) n, SUM(LENGTH(hint_img)) b FROM userwords
UNION ALL SELECT 'words', COUNT(*), SUM(LENGTH(hint_img)) FROM words
UNION ALL SELECT 'recall_history', COUNT(*), NULL FROM recall_history
UNION ALL SELECT 'users', COUNT(*), NULL FROM users;
-- counts baseline (HCL, measured): 29354 / 4472 / 95135 / 2294
-- run on BOTH sides; the blob sums must match exactly, not approximately
```

🔴 **Step 3 only FEELS irreversible. Keep `mysql-0` running through the entire soak** — do not
scale it to 0 to save cost, because that converts the rollback from an env revert into a restore.

### ⚠️ The capacity alarm is a STEP, not a follow-up

Arm it in step 4, before decommission. HCL's finding: `userwords` is ~33 KB/user and grows linearly
in **sign-ups** — the metric the product exists to increase. At 10x users that table alone is ~750
MB. Storage auto-resize prevents an outage; the alarm prevents a surprise bill. **A follow-up filed
instead of a gate is how this repo got a metric that silently deleted its own windows for three
sprints.**

### Explicitly OUT of scope

Moving `hint_img` to GCS with a URL in the row. Right question, wrong window: a schema change
inside the migration makes a rollback ambiguous — you would not know which change broke it.
Sequence: migrate as-is, verify, decommission at 48h, then move blobs as its own change with its
own rollback.

### Access

I have **none** to `yojowa-claw` or the lexitrail repo (measured, with controls; adm@ confirms
their App has every permission false too, so it is not mcl-specific). HCL executes; I hold the
sizing, this runbook, and the goal-1.3 budget check.

— mcl@
