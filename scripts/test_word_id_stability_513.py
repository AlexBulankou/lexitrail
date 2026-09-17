"""lex#513 — `word_id` stability, the precondition for NOT truncating user data.

`terraform/schema-data.sql` truncates four tables before reloading:

    TRUNCATE recall_history;   <- USER data. In no CSV. 95,141 rows. Unrecoverable.
    TRUNCATE userwords;        <- USER data. In no CSV.
    TRUNCATE words;            <- reference data, reloaded from words.csv
    TRUNCATE wordsets;         <- reference data, reloaded from wordsets.csv

and the Job re-runs on ANY edit under `terraform/csv/`, because its manifest
carries a `sha1` over that whole fileset (`terraform/sql.tf`). So a one-character
pinyin fix deletes every user's learning history.

🔴 THE OBVIOUS FIX HAS A PRECONDITION, AND THE PRECONDITION DOES NOT HOLD TODAY.

Dropping the two user-table truncates is only safe if `word_id` keeps meaning the
same word across a reload. Measured, and it does not:

    generator emits          5000 ids
    committed words.csv      5615 ids, range 1..7599 (GAPPED, not sequential)
    shared ids               4998
      ...word DIFFERS on     4893   <- 98%
    committed-only ids        617   <- a regen would DELETE these words

The committed file has the same words in the same ORDER as the generator for the
first 5000, but under DIFFERENT ids — gapped ones, the shape live ids take after
deletions. `generate_words_wordsets.py` renumbers contiguously from 1.

⇒ Removing the truncates WITHOUT fixing this is worse than the bug. Today the
user rows are deleted: bad, and honest. Then they would survive and silently
re-point — 98% of a user's history attached to the wrong words. Wrong data reads
as real; missing data does not.

These tests pin the parts that are checkable from the repo, so the fix has a
stated precondition and the dangerous case is executable rather than a paragraph.
"""
from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

CSV_DIR = Path(__file__).resolve().parents[1] / "terraform" / "csv"
GENERATOR = CSV_DIR / "generate_words_wordsets.py"


def _idmap(path: Path) -> dict[int, str]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {int(r["word_id"]): r["word"] for r in csv.DictReader(fh)}


def _regen(tmp: Path, mutate=None) -> dict[int, str]:
    """Run the REAL generator in a COPY of terraform/csv.

    A copy, because it writes `words.csv` into its own cwd — running it in place
    would rewrite the committed file as a side effect of testing it, which is the
    very destruction these tests exist to describe.
    """
    tmp.mkdir(parents=True, exist_ok=True)
    for f in sorted(CSV_DIR.glob("*.csv")):
        shutil.copy2(f, tmp / f.name)
    shutil.copy2(GENERATOR, tmp / GENERATOR.name)
    if mutate:
        mutate(tmp)
    r = subprocess.run([sys.executable, GENERATOR.name], cwd=tmp,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"generator failed: {r.stderr[-400:]}"
    out = _idmap(tmp / "words.csv")
    assert out, "CONTROL: generator produced no rows — every assertion would be vacuous"
    return out


def _mutate_hsk1(fn):
    def apply(d: Path):
        p = d / "HSK1.csv"
        rows = list(csv.DictReader(p.open(encoding="utf-8", newline="")))
        fn(rows)
        with p.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    return apply


def test_REGENERATING_words_csv_PRESERVES_every_shared_id(tmp_path):
    """Replaces `test_REGENERATING_words_csv_WOULD_RENUMBER_PRODUCTION` (lex#513).

    That test asserted the hazard: the generator renumbered contiguously from 1,
    so 4,893 of 4,998 shared ids (98%) named a DIFFERENT word than the committed
    file. It was a guard against a helpful-looking action, and its own text said
    to REPLACE it rather than delete it once the generator became
    content-addressed — because the precondition it guarded would then be free,
    and a deleted test cannot notice it stopping being free.

    This is that replacement, asserting the same property in the other
    direction. It is NOT a description of health either: it is the precondition
    for dropping the two user-table truncates, and it must keep holding.
    """
    gen, com = _regen(tmp_path), _idmap(CSV_DIR / "words.csv")
    shared = set(gen) & set(com)
    assert shared, "CONTROL: no shared ids — the assertions below would be vacuous"
    moved = [i for i in shared if gen[i] != com[i]]
    assert not moved, (
        f"{len(moved)} of {len(shared)} committed ids now name a DIFFERENT word. "
        "This is the 98% re-pointing hazard returning; user history keyed on "
        "those ids would silently attach to the wrong words.")
    assert not set(gen) - set(com), (
        "the generator invented ids the committed file does not have — it must "
        "reuse or extend, never renumber")


def test_a_regen_still_DROPS_words_the_generator_cannot_see(tmp_path):
    """🔴 The half of the precondition that is NOT satisfied. Do not delete this.

    Id stability is fixed; COVERAGE is not. The generator knows only HSK1-6, so
    regenerating still drops the committed words belonging to wordsets it has
    never heard of — 615 of them as measured 2026-09-17.

    ⇒ `schema-data.sql`'s truncates cannot be dropped on the strength of
    `test_REGENERATING_words_csv_PRESERVES_every_shared_id` alone. Those 615
    words would vanish from `words`, and user rows referencing them would fail
    their foreign key (or cascade away) — a smaller version of exactly the data
    loss lex#513 is about.
    """
    gen, com = _regen(tmp_path), _idmap(CSV_DIR / "words.csv")
    dropped = set(com) - set(gen)
    assert dropped, (
        "the generator now covers every committed word — if a source for the "
        "remaining wordsets was added, this precondition is finally met: "
        "re-read lex#513 before removing any truncate.")


def test_the_generator_EMITS_NO_DUPLICATE_word_id(tmp_path):
    """🔴 Regression, lex#542. `word_id` is the PRIMARY KEY; a repeat is corrupt.

    `(word, wordset_id)` is the DB's own UNIQUE constraint, which is why the
    generator keys identity on it — but the committed data VIOLATES that
    constraint (`对` twice in HSK2, ids 301 and 302). A one-id-per-key lookup
    therefore answered both source rows with the same id and emitted
    `302, 302`, turning a pre-existing UNIQUE violation into a new PRIMARY KEY
    violation on the reseed path.

    Asserted on the emitted ROWS, not on a dict built from them — keying a dict
    by `word_id` is what hid this: it silently collapses the duplicate to one
    entry, so `_idmap` above cannot see it and neither could any test built on
    it.
    """
    _regen(tmp_path)
    with (tmp_path / "words.csv").open(encoding="utf-8", newline="") as fh:
        ids = [r["word_id"] for r in csv.DictReader(fh)]
    assert ids, "CONTROL: generator emitted no rows"
    dupes = {i: n for i, n in Counter(ids).items() if n > 1}
    assert not dupes, f"duplicate word_id in generated words.csv: {dupes}"


def test_the_generator_does_not_know_about_every_committed_WORDSET():
    """The 617 dropped words are not scattered — they are whole wordsets the
    generator has never heard of, which is why 'just regenerate' looks safe."""
    with (CSV_DIR / "words.csv").open(encoding="utf-8", newline="") as fh:
        committed_sets = {r["wordset_id"] for r in csv.DictReader(fh)}
    # PARSE the number out of each filename rather than counting files and
    # assuming 1..N. hc2@ on lex#522: with a non-contiguous set (HSK1,2,3,5 —
    # four files) the count form derives {1,2,3,4}, silently calling wordset 5
    # unknown while claiming 4 is known. Measured:
    #     count form  -> ['1','2','3','4']   <- wrong on both ends
    #     parse form  -> ['1','2','3','5']
    # It is right today only because the files are HSK1-6 with no gaps — a
    # property of the DIRECTORY, not of this test, which is the exact shape the
    # rest of this file is about.
    known = {m.group(1) for m in
             (re.match(r"HSK(\d+)", p.name) for p in CSV_DIR.glob("HSK*.csv")) if m}
    assert known, "CONTROL: parsed no HSK numbers — the assertion below would be vacuous"
    assert committed_sets - known, (
        "every committed wordset has an HSK source — the drop-on-regen hazard "
        "may be gone; re-measure before deleting this test")


def test_a_CONTENT_edit_does_not_move_any_word_id(tmp_path):
    """The case lex#513 is about: a pinyin fix.

    Scoped honestly — this is stability WITHIN the generator's own output, which
    is the property the fix needs once the generator and production agree. It
    says nothing about today's committed ids, which already disagree.
    """
    base = _regen(tmp_path / "a")
    edited = _regen(tmp_path / "b", _mutate_hsk1(
        lambda rows: rows[0].__setitem__("Pinyin", rows[0]["Pinyin"] + "X")))
    moved = [i for i in set(base) & set(edited) if base[i] != edited[i]]
    assert not moved, f"a content-only edit moved {len(moved)} word_ids"


def test_an_INSERTION_does_not_move_any_EXISTING_id(tmp_path):
    """Replaces `test_an_INSERTION_SHIFTS_ids_onto_different_words` (lex#513).

    A head insertion was the hazard made executable: under a positional counter
    it shifted >90% of ids onto different words, which is why a content-only
    edit being safe did NOT mean ids were stable. Now the inserted word takes a
    fresh id and every existing word keeps its own.
    """
    def insert(rows):
        new = dict(rows[0])
        new["Chinese"] = "\u3007"
        rows.insert(0, new)

    base = _regen(tmp_path / "a")
    after = _regen(tmp_path / "b", _mutate_hsk1(insert))
    assert base, "CONTROL: empty baseline"
    moved = [i for i in set(base) & set(after) if base[i] != after[i]]
    assert not moved, f"a head insertion moved {len(moved)} of {len(base)} word_ids"
    assert set(after) - set(base), "the inserted word did not receive a new id"


def test_CONTROL_the_harness_still_DETECTS_movement_when_history_is_absent(tmp_path):
    """🔴 THE POSITIVE CONTROL. Without it the two tests above are unfalsifiable.

    The deleted `..._SHIFTS_ids_onto_different_words` was not only a hazard
    description — it was the control for
    `test_a_CONTENT_edit_does_not_move_any_word_id`, whose own docstring says
    so. Inverting both stability tests leaves every assertion in this file
    pointing the same way ("nothing moved"), which is also what a harness that
    can no longer SEE movement reports. A comparison that cannot fail proves
    nothing about the property it is named for.

    So exercise the real generator down a path where ids legitimately DO move:
    delete `words.csv` in the copy, which is its documented no-history path, and
    it numbers contiguously from 1. Measured 2026-09-17: 4,892 of 4,997 shared
    ids move (97.9%), reproducing the historical 4,893/98% almost exactly.

    ⚠️ This asserts the INSTRUMENT, not the product. If it ever fails, the two
    tests above are the ones that have stopped meaning anything — fix this first.
    """
    base = _regen(tmp_path / "a")
    nohist = _regen(tmp_path / "b", lambda d: (d / "words.csv").unlink())
    shared = set(base) & set(nohist)
    assert shared, "CONTROL: no shared ids"
    moved = [i for i in shared if base[i] != nohist[i]]
    assert len(moved) > 0.9 * len(shared), (
        f"the no-history path moved only {len(moved)} of {len(shared)} ids. The "
        "harness may no longer detect movement, which would make the stability "
        "tests in this file vacuous.")


def test_user_tables_have_NO_csv_so_their_truncate_cannot_be_a_reload():
    """The asymmetry the truncate list hides: two of its four tables have a
    source in this directory and two do not."""
    names = {p.stem for p in CSV_DIR.glob("*.csv")}
    assert {"words", "wordsets"} <= names
    assert not ({"recall_history", "userwords"} & names), (
        "a CSV appeared for a user table — re-read schema-data.sql before "
        "trusting this file's premise")
