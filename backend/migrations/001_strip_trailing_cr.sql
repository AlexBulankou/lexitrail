-- 001_strip_trailing_cr.sql — issue-310
--
-- Strips trailing carriage returns (and any trailing whitespace) from the three
-- text columns that carry them. Measured on the live lexitraildb 2026-09-01:
--
--     wordsets.description :     7 rows  (of 9)
--     words.def2           : 4,910 rows
--     words.def1           :     0 rows   <- see note below
--
-- Reported by Alex as BUG-3 on 2026-07-19 and re-validated by him as "still
-- present" on 07-20. The definitions half was an aside in that report; it is
-- the 4,910 rows. Almost certainly a CRLF-terminated seed loaded via
-- terraform/schema-data.sql -- see the issue's AC4, which is deliberately
-- allowed to close as unproven. A reseed would reintroduce this.
--
-- 🔴 THIS IS THE FIRST REAL MIGRATION through the mechanism added in #300/#307.
-- Merging it APPLIES IT TO PRODUCTION DATA: the backend-migrate step runs on
-- the backend/** trigger, before the deploy.
--
-- Safety properties, stated because this writes 4,910 live rows:
--   * ADDITIVE-ONLY in the sense that matters: no DROP, no schema change, no
--     row deleted. Only trailing whitespace is removed from three columns.
--   * IDEMPOTENT -- VERIFIED, not asserted. Running the transform twice over
--     the live data changes 0 rows on the second pass (checked read-only for
--     both columns). Safe if the ledger is ever lost.
--   * COMPLETE for this data: after the transform, 0 rows carry any residual
--     trailing whitespace, and 0 rows have leading whitespace. So the
--     TRIM-then-strip-CR order is sufficient here.
--   * NARROW: the WHERE clauses restrict each UPDATE to rows that actually
--     carry trailing whitespace, so the row count in the result IS the
--     before/after evidence rather than "every row was rewritten".
--   * NOT REVERSIBLE in the strict sense -- the original values are not
--     recorded anywhere. Restoring a trailing CR is not a state anyone wants,
--     but say so rather than imply a rollback exists.
--
-- ⚠️ The def1 statement currently matches ZERO rows. It is kept so the three
-- text columns are handled uniformly, but do not read this migration as
-- evidence that def1 was polluted -- it was not. Only def2 and the wordset
-- descriptions carry the CR.
--
-- ⚠️ Backslash escapes are ENABLED on this server (sql_mode does not contain
-- NO_BACKSLASH_ESCAPES), so '\r' is a real CR here -- verified directly rather
-- than assumed: ASCII('\r')=13. Under NO_BACKSLASH_ESCAPES these statements
-- would silently match nothing.
--
-- ⚠️ It does NOT need a matching UI change. An earlier version of the issue
-- claimed the test/HSK7 filter depends on the dirty strings; that was true when
-- Alex wrote it and has since been fixed -- ui/src/services/wordsService.js
-- already `.trim()`s before matching. Verified before writing this.

UPDATE wordsets
   SET description = TRIM(TRAILING '\r' FROM TRIM(description))
 WHERE description <> TRIM(TRAILING '\r' FROM TRIM(description));

UPDATE words
   SET def1 = TRIM(TRAILING '\r' FROM TRIM(def1))
 WHERE def1 <> TRIM(TRAILING '\r' FROM TRIM(def1));

UPDATE words
   SET def2 = TRIM(TRAILING '\r' FROM TRIM(def2))
 WHERE def2 <> TRIM(TRAILING '\r' FROM TRIM(def2));
