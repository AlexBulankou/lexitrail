"""issue-495: `backend/` reads two CSVs from outside its own directory and nothing
tested the code that reads them.

    backend/scripts/config.py   WORDSETS_CSV_PATH = '../terraform/csv/wordsets.csv'
                                WORDS_CSV_PATH    = '../terraform/csv/words.csv'
      -> lexitrailcmd.py         load_word_data(WORDSETS_CSV_PATH, WORDS_CSV_PATH)

AC1 asks for assertions a corrupted or truncated CSV would break. The interesting
corruption here is NOT a crash -- it is silence:

    def1 = row.get('def1', '').strip()

A renamed or dropped column makes `load_word_data` return a fully-shaped result
with every definition empty. No exception, no short read, and the caller cannot
tell it from a legitimately sparse bank. So the load-bearing assertion is that
definitions actually ARRIVE, not merely that the call returns.

Deliberately NOT pinned: the exact word count (5613 today). Adding words to the
bank is the normal, desirable change, and a `== N` pin would red on it and be
deleted -- taking the truncation coverage with it. A floor catches truncation and
survives growth. (Same reasoning as `cloudbuild-ui.yaml`'s budget note: a number a
human chose must not drift, but a number the DATA chooses must not be frozen.)
"""

import csv
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))

from scripts.data_loader import load_word_data  # noqa: E402

WORDSETS = _ROOT / "terraform" / "csv" / "wordsets.csv"
WORDS = _ROOT / "terraform" / "csv" / "words.csv"

# A truncation to a handful of rows is the failure this guards. The real bank is
# ~5600 words across 8 wordsets; 1000 is far enough below to survive ordinary
# curation and far enough above to catch a head -20.
MIN_WORDS = 1000
MIN_WORDSETS = 6


def _load():
    return load_word_data(str(WORDSETS), str(WORDS))


def test_the_csvs_are_where_backend_config_says_they_are_495():
    """If this reds, `config.py`'s relative paths and the repo have diverged --
    which is the #445 class (an input outside the reader's own directory)."""
    assert WORDSETS.is_file(), f"issue-495: missing {WORDSETS}"
    assert WORDS.is_file(), f"issue-495: missing {WORDS}"


def test_load_word_data_returns_the_real_bank_495():
    """AC1: shape AND volume. A truncated CSV still returns a well-formed dict."""
    data = _load()
    assert isinstance(data, dict)
    assert len(data) >= MIN_WORDSETS, (
        f"issue-495: only {len(data)} wordsets loaded (floor {MIN_WORDSETS}). "
        "wordsets.csv is truncated, or its `wordset_id`/`description` headers moved."
    )
    total = sum(len(v) for v in data.values())
    assert total >= MIN_WORDS, (
        f"issue-495: only {total} words loaded (floor {MIN_WORDS}). words.csv is "
        "truncated, or its `wordset_id`/`word` headers moved -- note that a header "
        "rename does NOT raise here, it silently yields fewer or emptier rows."
    )


def test_definitions_actually_ARRIVE_not_just_the_keys_495():
    """🔴 The load-bearing one. `row.get('def1', '')` means a renamed or dropped
    `def1`/`def2` column returns a perfectly shaped result with every definition
    empty -- no exception, no short read. Only asserting that definitions are
    NON-EMPTY can see that."""
    data = _load()
    defined = sum(
        1
        for words in data.values()
        for d in words.values()
        if (d.get("def1") or "").strip() or (d.get("def2") or "").strip()
    )
    total = sum(len(v) for v in data.values())
    assert total, "issue-495: no words at all"
    assert defined / total > 0.9, (
        f"issue-495: only {defined}/{total} words carry a definition. `load_word_data` "
        "reads def1/def2 with `row.get(..., '')`, so a renamed or dropped column "
        "produces exactly this -- a full-shaped result with empty definitions, and "
        "no error anywhere."
    )


def test_every_word_maps_to_the_def1_def2_contract_495():
    data = _load()
    for wordset, words in data.items():
        assert isinstance(wordset, str) and wordset.strip()
        for word, d in words.items():
            assert isinstance(d, dict) and {"def1", "def2"} <= set(d), (
                f"issue-495: {wordset!r}/{word!r} is {d!r}; callers "
                "(wordset_processing.process_entries) index def1/def2 directly."
            )


# ─── AC2: the negative control ────────────────────────────────────────────────
# Each arm builds a DELIBERATELY broken CSV and asserts the checks above go red.
# Without these, every assertion above could be satisfied by a predicate that
# cannot fail, and the coverage would be decorative -- which is the exact
# false-assurance this issue was filed to avoid, one level down.


def _write(tmp, wordsets_text, words_text):
    w1 = tmp / "wordsets.csv"
    w2 = tmp / "words.csv"
    w1.write_text(wordsets_text, encoding="utf-8")
    w2.write_text(words_text, encoding="utf-8")
    return load_word_data(str(w1), str(w2))


def _real_head(path, n):
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[: n + 1]) + "\n"


def test_CONTROL_a_truncated_words_csv_breaks_the_floor_495(tmp_path):
    """A `head -20` on words.csv. Returns a valid dict; the floor is what sees it."""
    data = _write(tmp_path, WORDSETS.read_text(encoding="utf-8"), _real_head(WORDS, 20))
    total = sum(len(v) for v in data.values())
    assert total < MIN_WORDS, (
        "issue-495 CONTROL FAILED: a 20-row words.csv did not fall below the floor, "
        f"so the floor cannot detect truncation (got {total}, floor {MIN_WORDS})."
    )


def test_CONTROL_a_renamed_def_column_is_SILENT_and_the_ratio_sees_it_495(tmp_path):
    """🔴 The arm that matters. Rename `def1`/`def2` and `load_word_data` raises
    NOTHING -- it returns the full bank with every definition empty. This proves
    both that the silent-corruption case is real and that the ratio assertion
    above is the thing that catches it."""
    words_text = WORDS.read_text(encoding="utf-8")
    header, rest = words_text.split("\n", 1)
    renamed = header.replace("def1", "definition_1").replace("def2", "definition_2")
    assert renamed != header, "issue-495: words.csv header no longer contains def1/def2"

    data = _write(tmp_path, WORDSETS.read_text(encoding="utf-8"), renamed + "\n" + rest)

    total = sum(len(v) for v in data.values())
    assert total >= MIN_WORDS, (
        "issue-495 CONTROL FAILED: the renamed-column case was supposed to be "
        "SILENT (full bank, empty definitions). It changed the word count instead, "
        "so this arm is no longer demonstrating silent corruption."
    )
    defined = sum(
        1
        for words in data.values()
        for d in words.values()
        if (d.get("def1") or "").strip() or (d.get("def2") or "").strip()
    )
    assert defined == 0, (
        f"issue-495 CONTROL FAILED: {defined} definitions survived a renamed "
        "column, so the ratio assertion above is not actually testing this."
    )


def test_CONTROL_an_empty_wordsets_csv_breaks_the_wordset_floor_495(tmp_path):
    data = _write(tmp_path, "wordset_id,description\n", WORDS.read_text(encoding="utf-8"))
    assert len(data) < MIN_WORDSETS, (
        "issue-495 CONTROL FAILED: an empty wordsets.csv still produced "
        f"{len(data)} wordsets; the wordset floor cannot detect this."
    )
