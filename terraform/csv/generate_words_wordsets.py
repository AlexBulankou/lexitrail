"""Regenerate `words.csv` / `wordsets.csv` from the HSK source files.

🔴 THIS SCRIPT DECIDES WHETHER USER HISTORY CAN SURVIVE A RESEED (lex#513).

`terraform/schema-data.sql` truncates `recall_history` (95,141 rows) and
`userwords` on every reseed, and the Job reseeds on ANY edit under
`terraform/csv/`. The fix everyone reaches for is to drop those two truncates so
user rows survive. **That fix is only safe if `word_id` keeps meaning the same
word across a regeneration**, because both user tables key on `words(word_id)`:

    userwords       FOREIGN KEY (word_id) REFERENCES words(word_id)
    recall_history  FOREIGN KEY (word_id) REFERENCES words(word_id)

The previous version of this script numbered contiguously from 1 on every run,
so ids were positional. `scripts/test_word_id_stability_513.py` measured what
that costs against the committed file:

    shared ids 4,998  ->  the WORD DIFFERS on 4,893 of them  (98%)

⇒ Under the old script, dropping the truncates would have been **worse than the
bug it fixes**: instead of a user's history being deleted (bad, and obvious), 98%
of it would silently re-point to different words. Wrong data reads as real;
missing data does not.

## What this version does

`word_id` is now ASSIGNED ONCE AND KEPT. On each run it reads the committed
`words.csv`, reuses the existing id for any word it still contains, and hands out
fresh ids only to genuinely new words.

The identity key is `(word, wordset_id)` — chosen because it is the DB's OWN
uniqueness constraint (`UNIQUE(word, wordset_id)` in `schema-tables.sql`), not
because it looked reasonable here. A generator that invented its own notion of
sameness could disagree with the schema and would be a second source of truth.

🔴 RETIRED IDS ARE NEVER REUSED. New ids continue from `max(existing) + 1` and
gaps are left as gaps. Refilling a gap would hand a retired word's id to an
unrelated new word — which is the exact re-pointing failure above, arriving one
release later and affecting only the users who had studied the retired word.
The gaps in the committed file (5,615 ids spanning 1..7,599) are the normal shape
of an id space that has seen deletions, and they are load-bearing, not untidiness.

⚠️ THIS IS THE PRECONDITION, NOT THE FIX. Removing the truncates from
`schema-data.sql` is a separate change and must come after this one is in the
committed CSV. Sequencing matters: this script's own output changes `files_hash`
and therefore re-fires the seed Job, which today is still destructive.
"""
import csv
import os

hsk_files = ["HSK1.csv", "HSK2.csv", "HSK3.csv", "HSK4.csv", "HSK5.csv", "HSK6.csv"]
wordsets_output_file = "wordsets.csv"
words_output_file = "words.csv"


def load_existing_ids(path):
    """Map `(word, wordset_id) -> word_id` from an existing words.csv.

    Returns `({}, 0)` when the file is absent — a first run on a clean tree
    numbers from 1, which is correct precisely because there is no history to
    protect. ⚠️ It is NOT correct if the file is merely unreadable or was
    deleted by accident: that case is indistinguishable here and would silently
    renumber everything. The caller is a human running a generator in a git
    checkout, so a missing file is recoverable with `git checkout`; an empty map
    reached any other way is not this function's to detect.
    """
    if not os.path.exists(path):
        return {}, 0
    existing, max_id = {}, 0
    with open(path, newline='', encoding='utf-8') as fh:
        for row in csv.DictReader(fh):
            wid = int(row['word_id'])
            existing[(row['word'], int(row['wordset_id']))] = wid
            max_id = max(max_id, wid)
    return existing, max_id


existing_ids, max_existing_id = load_existing_ids(words_output_file)
next_id = max_existing_id + 1

wordsets_data = []
words_data = []
reused = 0
assigned = 0

for idx, hsk_file in enumerate(hsk_files, start=1):
    wordset_name = f"HSK{idx}"
    wordsets_data.append([idx, wordset_name])

    with open(hsk_file, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            word = row['Chinese']
            def1 = row['Pinyin']
            def2 = row['English']
            key = (word, idx)
            if key in existing_ids:
                word_id = existing_ids[key]
                reused += 1
            else:
                word_id = next_id
                next_id += 1
                assigned += 1
            words_data.append([word_id, word, idx, def1, def2])

with open(wordsets_output_file, mode='w', newline='', encoding='utf-8') as wordsets_file:
    writer = csv.writer(wordsets_file)
    writer.writerow(['wordset_id', 'description'])
    writer.writerows(wordsets_data)

with open(words_output_file, mode='w', newline='', encoding='utf-8') as words_file:
    writer = csv.writer(words_file)
    writer.writerow(['word_id', 'word', 'wordset_id', 'def1', 'def2'])
    writer.writerows(words_data)

# Report the split rather than a bare success line: "generated successfully" is
# true of the old destructive behaviour too, so it cannot tell the operator
# which one just ran. A large `assigned` count on a routine edit is the signal
# that identity was lost -- e.g. a changed `word` string is a NEW word here.
dropped = len(existing_ids) - reused
print(f"Generated {wordsets_output_file} and {words_output_file}: "
      f"{reused} ids reused, {assigned} newly assigned, {dropped} committed "
      f"ids no longer present (their ids are retired, not reissued).")
