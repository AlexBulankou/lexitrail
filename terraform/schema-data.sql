-- lex#513 — THIS FILE RUNS ON EVERY RESEED, AND A RESEED FIRES ON ANY EDIT
-- UNDER terraform/csv/ (sql.tf hashes fileset(csv, "**/*")). It used to begin by
-- truncating FOUR tables, two of which hold user data that no CSV can restore:
--
--     TRUNCATE recall_history;   <- 95,141 rows of user learning history
--     TRUNCATE userwords;        <- user state
--
-- Neither is reloaded below — only wordsets.csv and words.csv are. So their
-- truncation was never part of reseeding; it was collateral to it. A
-- one-character pinyin fix deleted every user's history.
--
-- The usual reason to clear children first is that you cannot truncate a
-- referenced parent — but FOREIGN_KEY_CHECKS = 0 is exactly what makes
-- truncating words/wordsets alone legal. The guard that would have justified
-- those two lines is the same guard that makes them unnecessary.

-- Disable foreign key checks so the reference tables can be truncated while
-- user rows still point at them.
SET FOREIGN_KEY_CHECKS = 0;

-- Reference data ONLY. Both are fully reloaded from CSV below.
-- 🔴 DO NOT ADD recall_history OR userwords HERE. They are not in any CSV.
TRUNCATE TABLE words;
TRUNCATE TABLE wordsets;

-- Re-enable before the loads. Note this arms ON DELETE CASCADE for anything
-- below, which is why the loads below must never use REPLACE — see
-- scripts/test_seed_path_cascade_513.py, which pins that trap: REPLACE is
-- DELETE + INSERT, and both user tables cascade off words(word_id), so it
-- would destroy the same rows with no TRUNCATE left in the file to notice.
SET FOREIGN_KEY_CHECKS = 1;

-- Load data into wordsets
LOAD DATA LOCAL INFILE '/mnt/csv/wordsets.csv'
INTO TABLE wordsets
FIELDS TERMINATED BY ',' 
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;

-- Load data into words
LOAD DATA LOCAL INFILE '/mnt/csv/words.csv'
INTO TABLE words
FIELDS TERMINATED BY ',' 
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;
