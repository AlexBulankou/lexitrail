#!/usr/bin/env python3
"""lexitrail#513 STEP 3: the seed Job's `files_hash` must cover exactly the
files the Job LOADS -- no more, no less.

STEPS 1 and 2 made the seed non-destructive (#541) and stabilised `word_id`
(#542). This is the last piece: the Job used to be re-triggered by files it
never reads.

    files_hash = sha1(... fileset("${path.module}/csv", "**/*") ...)

`fileset` reads the FILESYSTEM, not git, and `**/*` matched a gitignored
`__pycache__/*.pyc` plus the generator script and six HSK input CSVs. Measured
with `terraform console` against terraform/csv: 10 entries, of which 2 are
loaded. Consequences, in order of nastiness:

  1. Two engineers at the same commit computed DIFFERENT hashes, because one of
     them had run the generator locally and had a .pyc the other did not.
  2. Editing the generator -- including the commit that NARROWS this very glob
     -- re-fired the Job.

While the seed truncated `recall_history` (95,141 rows) that made every one of
these a data-loss event; #541 removed the truncation, which is why this is now a
noise fix rather than a P1. The ordering was deliberate and is recorded on #513.

🔴 WHAT THIS PINS, and why it is not a grep for the old string. The expected set
is DERIVED from `storage.tf` -- the bucket objects are what physically reach the
Job's pod -- so:

  * adding a third loaded CSV to storage.tf and NOT adding it to the hash  -> red
  * re-widening either hash site back to a glob                            -> red
  * hashing a file that is not uploaded (the generator, an HSK input)      -> red
  * hashing a gitignored file                                              -> red

A test that just asserted `"**/*" not in sql.tf` would pass on all four.

Run: python3 -m pytest -q scripts/test_seed_hash_inputs_513.py
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TF = ROOT / "terraform"
CSV_DIR = TF / "csv"

# The two expressions that decide whether the seed Job re-applies. Both must
# agree; sql.tf's hash goes into the Job manifest, triggers.tf's into the
# null_resource that gates the re-upload.
HASH_SITES = ("sql.tf", "triggers.tf")

_CSV_FILESHA1 = re.compile(
    r'filesha1\(\s*"\$\{path\.module\}/csv/([^"]+)"\s*\)')
_CSV_FILESET = re.compile(
    r'fileset\(\s*"\$\{path\.module\}/csv"')
# storage.tf: `source = "${path.module}/csv/<name>"` on a bucket object.
_CSV_SOURCE = re.compile(
    r'source\s*=\s*"\$\{path\.module\}/csv/([^"]+)"')


def _uploaded_csvs() -> set[str]:
    """The csv/ files that are actually shipped to the Job, per storage.tf."""
    names = set(_CSV_SOURCE.findall((TF / "storage.tf").read_text()))
    # Guard the derivation itself: if storage.tf stops matching, every
    # assertion below would compare two empty sets and pass vacuously.
    assert names, "derived an EMPTY uploaded-CSV set from storage.tf"
    return names


def _hashed_csvs(site: str) -> set[str]:
    return set(_CSV_FILESHA1.findall((TF / site).read_text()))


@pytest.mark.parametrize("site", HASH_SITES)
def test_hash_covers_exactly_the_uploaded_csvs(site):
    assert _hashed_csvs(site) == _uploaded_csvs(), (
        f"{site}: the seed hash must cover exactly the CSVs storage.tf uploads. "
        f"hashed={sorted(_hashed_csvs(site))} uploaded={sorted(_uploaded_csvs())}"
    )


@pytest.mark.parametrize("site", HASH_SITES)
def test_no_glob_over_the_csv_directory(site):
    """A glob re-admits whatever lands in csv/ next, silently."""
    assert not _CSV_FILESET.search((TF / site).read_text()), (
        f"{site}: hash the loaded files by name; a fileset() over csv/ matches "
        f"untracked build artefacts (__pycache__) and build-time inputs."
    )


def test_the_two_sites_agree():
    a, b = (_hashed_csvs(s) for s in HASH_SITES)
    assert a == b, f"{HASH_SITES[0]} hashes {sorted(a)}, {HASH_SITES[1]} {sorted(b)}"


def test_every_hashed_file_exists_and_is_tracked():
    """The original defect was hashing a gitignored, machine-local .pyc."""
    hashed = _hashed_csvs("sql.tf")
    # Without this, the loop below passes VACUOUSLY on an empty set -- which is
    # exactly the state the re-widened-to-a-glob mutant produces. Found by
    # asking of this test "could it pass if the code did nothing?"; it could.
    assert hashed, "no csv/ file is hashed at all -- nothing was checked"
    for name in sorted(hashed):
        p = CSV_DIR / name
        assert p.is_file(), f"{name} is hashed but does not exist"
        rc = subprocess.run(
            ["git", "check-ignore", "-q", str(p)], cwd=ROOT).returncode
        # check-ignore: 0 = IS ignored (the bug), 1 = not ignored (what we want).
        assert rc == 1, f"{name} is hashed but is gitignored -> hash is machine-local"


def test_the_removed_inputs_are_still_present_but_unhashed():
    """Not cosmetic: it is what makes this a NARROWING rather than a deletion.

    If someone 'fixes' a future red by deleting the generator or the HSK inputs,
    the tests above would go green while the corpus lost its source of truth.
    """
    hashed = _hashed_csvs("sql.tf")
    for name in ("generate_words_wordsets.py", "HSK1.csv", "HSK6.csv"):
        assert (CSV_DIR / name).is_file(), f"{name} vanished from csv/"
        assert name not in hashed, f"{name} is a build-time INPUT and must not re-fire the Job"
