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
import shutil
import subprocess
import sys
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


def test_REGENERATING_words_csv_WOULD_RENUMBER_PRODUCTION(tmp_path):
    """🔴 A guard against a helpful-looking action, not a description of health.

    `generate_words_wordsets.py` sits in `terraform/csv/` and is the only
    generator there, so it reads as the source of truth for `words.csv`. It is
    not, and running it is destructive: it renumbers contiguously from 1 while
    the committed ids are gapped, and it knows only HSK1-6.

    If this test ever FAILS because the two now agree, somebody has regenerated
    the file — check what happened to `recall_history` before assuming that was
    a cleanup.
    """
    gen, com = _regen(tmp_path), _idmap(CSV_DIR / "words.csv")
    shared = set(gen) & set(com)
    moved = [i for i in shared if gen[i] != com[i]]
    dropped = set(com) - set(gen)
    assert moved, ("the generator's ids now MATCH the committed file — see the "
                   "docstring: verify a regen has not just happened")
    assert len(moved) > 0.9 * len(shared), f"only {len(moved)} of {len(shared)} ids moved"
    assert dropped, "the generator now covers every committed word — re-read this file's premise"


def test_the_generator_does_not_know_about_every_committed_WORDSET():
    """The 617 dropped words are not scattered — they are whole wordsets the
    generator has never heard of, which is why 'just regenerate' looks safe."""
    with (CSV_DIR / "words.csv").open(encoding="utf-8", newline="") as fh:
        committed_sets = {r["wordset_id"] for r in csv.DictReader(fh)}
    known = {str(i) for i in range(1, len(list(CSV_DIR.glob("HSK*.csv"))) + 1)}
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


def test_an_INSERTION_SHIFTS_ids_onto_different_words(tmp_path):
    """🔴 The hazard, executable — and the positive control for the test above.

    Without it, that test passing would read as "ids are stable" full stop, and
    the fix would ship without its precondition. Ids are stable under content
    edits ONLY, because the counter is positional.
    """
    def insert(rows):
        new = dict(rows[0])
        new["Chinese"] = "〇"
        rows.insert(0, new)

    base = _regen(tmp_path / "a")
    after = _regen(tmp_path / "b", _mutate_hsk1(insert))
    moved = [i for i in set(base) & set(after) if base[i] != after[i]]
    assert len(moved) > 0.9 * len(base), (
        f"a head insertion shifted only {len(moved)} of {len(base)} ids — if the "
        "generator became content-addressed, REPLACE this test rather than "
        "deleting it: the precondition it guards would then be free")


def test_user_tables_have_NO_csv_so_their_truncate_cannot_be_a_reload():
    """The asymmetry the truncate list hides: two of its four tables have a
    source in this directory and two do not."""
    names = {p.stem for p in CSV_DIR.glob("*.csv")}
    assert {"words", "wordsets"} <= names
    assert not ({"recall_history", "userwords"} & names), (
        "a CSV appeared for a user table — re-read schema-data.sql before "
        "trusting this file's premise")
