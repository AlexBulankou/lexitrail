#!/usr/bin/env python3
"""Validate an example-sentence bank before it is generated into word pages (#433).

WHY THIS IS A SCRIPT RATHER THAN THE CHECKLIST IN EACH PR BODY
--------------------------------------------------------------
#433's AC2 needs >= 1,000 word pages carrying example sentences. At 25 headwords
per bank and 474 covered, that is ~21 more banks. Every one of them has been
validated by a block of throwaway Python pasted into a PR body, rewritten from
scratch each time -- and the checklist in the PR body is read by the reviewer,
not by the author writing the next bank.

Tonight that cost two false readings, both of which reported a CLEAN bank as
broken, and either of which could as easily have pointed the other way:

  * The wordset filter. Every HSK3 headword also appears in `words.csv` at
    `wordset_id 8`. A dict comprehension keyed on `word` silently keeps the LAST
    row, so `rows[w]["wordset_id"]` reads `8` and the check reports `0/25` on a
    bank where all 25 are present. The tell was a uniform zero sitting beside a
    passing 25/25 on a check that needs the same lookup -- FILTER to the wordset
    BEFORE keying.

  * The containment check. Four HSK3 headwords carry a part-of-speech tag in the
    CSV itself -- `过（动词）`, `花（动词）`, `花（名词）`, `还（动词）`. `word.chinese`
    must keep that string for the generator's join, but no sentence contains it,
    so a naive `headword in sentence` reports 0/8 on correct sentences. The bare
    form is what appears in prose (HSK1's `这 (这儿)` established this).

Both are invisible in a passing run and both fail toward "your bank is broken",
which is the direction that wastes an hour rather than shipping a defect. They
are encoded here so the next bank cannot meet them again.

EXIT CODES
----------
    0  PASS         every check passed
    1  FAIL         at least one check failed -- each failure is enumerated
    3  CANNOT-TELL  the bank or the CSV could not be read at all

WHAT THIS DOES NOT CHECK
------------------------
Sense AGREEMENT, and there is a convention for it because a machine cannot settle
it. A headword with several grammatical functions -- the directional/resultative
complements especially (`起来`, `出来`, `下去`) -- can be used correctly in a
sentence that demonstrates a DIFFERENT sense from the one the CSV defines, and
every check above still passes: the headword appears, the pinyin matches, the
numbering is contiguous.

    THE FIRST sentence MUST demonstrate the CSV's own sense.
    THE SECOND may show breadth -- and if it does, SAY SO in the PR body.

Why first-must-match rather than both-must-match: the card is drilled from the
CSV definition, so the learner's first encounter has to agree with the gloss they
were just shown. But `起来` genuinely means both "get up" and the inchoative "adj
+ 起来", and a bank that hid the second would teach a false narrowness. Breadth is
worth having in the second slot; it is a defect only in the first.

Found by hc2@ reviewing bank 6 (#468): `我每天六点起来。` (CSV sense, "get up") is
paired with `天气热起来了。` (inchoative). Both correct Chinese, both pass this
script, and a learner drilling the "get up" card meets the second one cold. ~125
HSK3 headwords remain, so this recurs.

Sentence QUALITY: whether the Chinese is idiomatic, whether the pinyin tones are
correct for the characters used, or whether the English translates it. Those need
a reader and are what the peer review is for. This checks only the properties a
machine can settle, which is why a green run here is a precondition for review
rather than a substitute for it.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys

TONE_MARKS = set("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bare_headword(word: str) -> str:
    """Strip a part-of-speech tag: `过（动词）` -> `过`.

    Handles fullwidth `（）` (the HSK3 POS tags) and ASCII `()` (HSK1's
    `这 (这儿)` alternate-form convention). Returns the input unchanged when
    there is no parenthetical, so it is safe to call on every headword.
    """
    return re.split(r"[（(]", word)[0].strip()


def load_wordset(csv_path: str, wordset_id: str) -> dict[str, dict]:
    """CSV rows for ONE wordset, keyed by word.

    🔴 The filter is applied BEFORE keying, and that ordering is the whole point:
    a headword appearing in several wordsets would otherwise be represented by
    whichever row happened to come last in the file.
    """
    with open(csv_path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {r["word"]: r for r in rows if str(r["wordset_id"]) == str(wordset_id)}


def other_banks(bank_path: str, bank_glob: str) -> set[str]:
    """Headwords covered by every bank EXCEPT the one under test."""
    target = os.path.abspath(bank_path)
    covered: set[str] = set()
    for p in glob.glob(bank_glob):
        if os.path.abspath(p) == target:
            continue
        with open(p, encoding="utf-8") as fh:
            for s in json.load(fh).get("sentences", []):
                covered.add(s["word"]["chinese"])
    return covered


def check(bank_path: str, csv_path: str, wordset_id: str,
          bank_glob: str) -> tuple[int, list[str]]:
    """Return (exit_code, report_lines)."""
    try:
        with open(bank_path, encoding="utf-8") as fh:
            sentences = json.load(fh)["sentences"]
        words = load_wordset(csv_path, wordset_id)
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        return 3, [f"CANNOT-TELL: {exc}"]
    if not sentences:
        return 3, ["CANNOT-TELL: the bank contains no sentences"]
    if not words:
        return 3, [f"CANNOT-TELL: no rows in {csv_path} with wordset_id {wordset_id}"]

    covered = other_banks(bank_path, bank_glob)
    heads = {s["word"]["chinese"] for s in sentences}
    out, failures = [], []

    def record(label: str, good: int, total: int, bad: list[str]) -> None:
        out.append(f"  {label:<52} {good}/{total}")
        if good != total:
            failures.append(f"{label}: {', '.join(bad[:6])}")

    bad = [w for w in sorted(heads) if w not in words]
    record(f"every headword is in the CSV with wordset_id {wordset_id}",
           len(heads) - len(bad), len(heads), bad)

    bad = [s["word"]["chinese"] for s in sentences
           if words.get(s["word"]["chinese"], {}).get("def1") != s["word"]["pinyin"]]
    record("word.pinyin matches the CSV's def1 exactly",
           len(sentences) - len(bad), len(sentences), sorted(set(bad)))

    bad = [f"#{s['no']} {s['word']['chinese']}" for s in sentences
           if bare_headword(s["word"]["chinese"]) not in s["chinese"]]
    record("every headword appears in its own sentence",
           len(sentences) - len(bad), len(sentences), bad)

    bad = [w for w in sorted(heads) if w in covered]
    record("no headword already covered by another bank",
           len(heads) - len(bad), len(heads), bad)

    bad = [f"#{s['no']}" for s in sentences
           if not (s["pinyin"][:1].isupper()
                   and any(c in TONE_MARKS for c in s["pinyin"]))]
    record("every pinyin is sentence-capitalised, with tone marks",
           len(sentences) - len(bad), len(sentences), bad)

    nos = [s["no"] for s in sentences]
    ok = nos == list(range(1, len(sentences) + 1))
    out.append(f"  {'sentence numbering is 1..N contiguous':<52} {'yes' if ok else 'NO'}")
    if not ok:
        failures.append("sentence numbering is not 1..N contiguous")

    return (1 if failures else 0), out + ([""] + [f"FAIL: {f}" for f in failures]
                                          if failures else [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bank", help="path to sentences-<level>-<n>-v1.json")
    ap.add_argument("--wordset-id", default=None,
                    help="CSV wordset_id (default: inferred from the filename)")
    ap.add_argument("--csv", default=os.path.join(REPO, "terraform/csv/words.csv"))
    ap.add_argument("--bank-glob",
                    default=os.path.join(REPO, "sentences/sentences-*.json"))
    args = ap.parse_args()

    wordset = args.wordset_id
    if wordset is None:
        m = re.search(r"sentences-hsk(\d+)-", os.path.basename(args.bank))
        if not m:
            print("CANNOT-TELL: cannot infer wordset_id from the filename; "
                  "pass --wordset-id", file=sys.stderr)
            return 3
        wordset = m.group(1)

    code, lines = check(args.bank, args.csv, wordset, args.bank_glob)
    print(f"{os.path.basename(args.bank)} (wordset_id {wordset})")
    for line in lines:
        print(line)
    print({0: "PASS", 1: "FAIL", 3: "CANNOT-TELL"}[code])
    return code


if __name__ == "__main__":
    sys.exit(main())
