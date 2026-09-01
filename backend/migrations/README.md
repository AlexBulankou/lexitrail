# `backend/migrations/` — additive schema changes (issue-300)

## Status: BASELINE ONLY. There is no runner yet.

`000_baseline.sql` is a capture, not a migration. **Nothing in this directory is
executed by anything today.** Saying so explicitly because a `migrations/`
directory that looks operational and is not is the same defect #300 reports, one
layer up.

## Why the runner is not here yet

Two things had to be settled first, and only one of them is.

**Settled — where the mechanism is delivered from.** Not `terraform-ys/`. That
root has no apply automation (#299), and a `terraform plan` on it produces 13
actions of which 12 are state-drift creates against objects that already exist,
so an apply aborts before reaching any real change (gated on the state import,
my-hermes#1338). A migration Job declared there would never run. The only path
that reaches this cluster today is the backend image: `backend/**` →
`cloudbuild.yaml` → build, push, `kubectl set image`, read back, smoke.

**Open — where the step runs.** A correctness question, not a preference:

| option | single-run? | covers every environment? |
|---|---|---|
| app startup (`entrypoint`) | ❌ two replicas race | ✅ anything that runs the image |
| one-shot step in `cloudbuild.yaml` | ✅ | ❌ silently skips anything the pipeline doesn't touch |

Both failure modes are silent, which is why this is being written up rather than
picked quickly.

## The convention, once a runner exists

- Files are `NNN_<slug>.sql`, applied in lexical order, **additive only** — no
  `DROP`, no destructive `ALTER`. `000_baseline.sql` is never applied; it is the
  starting point `001` migrates *from*.
- Applied migrations are recorded in a `schema_migrations` table so a re-run is
  a no-op.
- `terraform/schema-tables.sql` is the retired root's seed and **DROPs all five
  tables** whenever `mysql_schema_and_data_job` runs. It is not the live
  schema's source of truth and must not be treated as one.

## The check that would have caught the divergence

Two values, one comparison — the live column set against the baseline:

```bash
PW=$(kubectl -n lexitrail get secret mysql-root -o jsonpath='{.data.MYSQL_ROOT_PASSWORD}' | base64 -d)
kubectl -n lexitrail exec mysql-0 -- sh -c \
  "mysql -uroot -p'$PW' -N -B -e \"SELECT CONCAT(TABLE_NAME,'.',COLUMN_NAME) \
   FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='lexitraildb' \
   AND TABLE_NAME<>'daily_recall_stats'\"" | LC_ALL=C sort
```

⚠️ The schema is **`lexitraildb`**, not `lexitrail`. A filter on the wrong name
returns zero rows and reads as an empty database rather than as a bad query.

⚠️ `LC_ALL=C` on both sides is load-bearing: without it `comm` reports the same
entries as present-only-on-the-left *and* present-only-on-the-right, which reads
as a diff and is a collation mismatch.
