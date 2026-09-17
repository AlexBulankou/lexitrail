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
from collections import defaultdict, deque

hsk_files = ["HSK1.csv", "HSK2.csv", "HSK3.csv", "HSK4.csv", "HSK5.csv", "HSK6.csv"]
wordsets_output_file = "wordsets.csv"
words_output_file = "words.csv"


def load_existing_ids(path):
    """Map `(word, wordset_id) -> deque of word_ids`, in committed file order.

    Returns `({}, 0)` when the file is absent — a first run on a clean tree
    numbers from 1, which is correct precisely because there is no history to
    protect. ⚠️ It is NOT correct if the file is merely unreadable or was
    deleted by accident: that case is indistinguishable here and would silently
    renumber everything. The caller is a human running a generator in a git
    checkout, so a missing file is recoverable with `git checkout`; an empty map
    reached any other way is not this function's to detect.

    🔴 A DEQUE PER KEY, NOT ONE ID PER KEY, AND THE DIFFERENCE IS A CORRUPT FILE.
    `(word, wordset_id)` is the DB's `UNIQUE(word, wordset_id)` constraint, which
    is why it is the identity key here — but **the committed data violates that
    constraint**, so the key is not actually unique and a plain dict is wrong in
    two directions at once:

        `对` appears TWICE in HSK2, committed as ids 301 and 302.

      - reading:  `existing[key] = wid` is last-wins, so **301 is silently lost**
                  and its id looks retired while the word is still present.
      - writing:  both source rows then look that one id up and get the SAME
                  answer, emitting two rows with `word_id = 302` against
                  `word_id INT AUTO_INCREMENT PRIMARY KEY`.

    That converts a pre-existing UNIQUE violation into a **new PRIMARY KEY**
    violation, on the reseed path this whole issue exists to make safe. Measured
    2026-09-17: committed `301,302` and the old positional generator `299,300`
    are both distinct; the dict version emitted `302,302`.

    Consuming a deque in file order gives the Nth occurrence of a key the Nth
    committed id, so the pair round-trips as `301,302` unchanged. Ordering
    *within* a duplicate group is immaterial precisely because its members are
    the same word in the same wordset — there is no fact that could distinguish
    them, which is what makes this safe rather than merely positional.
    """
    if not os.path.exists(path):
        return {}, 0
    existing, max_id = defaultdict(deque), 0
    with open(path, newline='', encoding='utf-8') as fh:
        for row in csv.DictReader(fh):
            wid = int(row['word_id'])
            existing[(row['word'], int(row['wordset_id']))].append(wid)
            max_id = max(max_id, wid)
    return existing, max_id


existing_ids, max_existing_id = load_existing_ids(words_output_file)
# Count BEFORE the loop consumes the deques — `len(existing_ids)` is a count of
# distinct keys, and after consumption it no longer reflects the ids either.
total_existing_ids = sum(len(v) for v in existing_ids.values())
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
            if existing_ids.get(key):
                # popleft, not lookup: a key can carry more than one committed
                # id (see load_existing_ids). Consuming makes the second
                # occurrence of a duplicated word take the second id rather
                # than re-issuing the first.
                word_id = existing_ids[key].popleft()
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
dropped = total_existing_ids - reused
print(f"Generated {wordsets_output_file} and {words_output_file}: "
      f"{reused} ids reused, {assigned} newly assigned, {dropped} committed "
      f"ids no longer present (their ids are retired, not reissued).")
