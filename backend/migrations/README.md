# `backend/migrations/` — additive schema changes (issue-300)

## Status: baseline + runner. The runner is wired into `cloudbuild.yaml`.

`000_baseline.sql` is a capture, **not a migration, and it is never applied** —
it describes tables that already hold 2050 users and 94244 recall rows. It is
the point `001` migrates *from*. `apply.sh` excludes it by name.

```bash
backend/migrations/apply.sh --plan    # what WOULD be applied; touches nothing
backend/migrations/apply.sh           # apply pending, in order, then record
```

## Why the runner is shaped this way

Two things had to be settled, and both now are.

**Settled — where the mechanism is delivered from.** Not `terraform-ys/`. That
root has no apply automation (#299), and a `terraform plan` on it produces 13
actions of which 12 are state-drift creates against objects that already exist,
so an apply aborts before reaching any real change (gated on the state import,
my-hermes#1338). A migration Job declared there would never run. The only path
that reaches this cluster today is the backend image: `backend/**` →
`cloudbuild.yaml` → build, push, `kubectl set image`, read back, smoke.

**Settled — where the step runs.** A one-shot `backend-migrate` step in
`cloudbuild.yaml`, between `backend-push` and `backend-deploy`:

| option | single-run? | covers every environment? |
|---|---|---|
| app startup (`entrypoint`) | ❌ two replicas race | ✅ anything that runs the image |
| one-shot step in `cloudbuild.yaml` | ✅ | ❌ skips anything the pipeline doesn't touch |

The objection to the second was **measured away**: there is exactly one
namespace, one MySQL StatefulSet, and `backend/app/config.py` connects to it by
in-cluster DNS, so there is nothing to skip.

⚠️ **Reversal condition:** if a second environment or a non-cluster database
appears, that column becomes false and the runner must move into the image with
a lock. This is the one assumption to re-check before adding an environment.

**Ordering:** migrations run BEFORE the new image goes live. An additive
migration must land before code that depends on the new column, and old code
tolerates a column it does not know about. The reverse order serves requests
against a schema that has not caught up.

## The convention

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
