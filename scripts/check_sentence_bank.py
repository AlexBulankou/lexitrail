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
# #467 -- the headwords whose gloss slot must name a STRUCTURE rather than a
# content word. See sentences/function-words.json for why, and for the rule that
# it is keyed on the FULL headword (地 is registered; 地方 / 地铁 / 地图 are not).
FUNCTION_WORDS = os.path.join(REPO, "sentences", "function-words.json")


def bare_headword(word: str) -> str:
    """Strip a part-of-speech tag: `过（动词）` -> `过`.

    Handles fullwidth `（）` (the HSK3 POS tags) and ASCII `()` (HSK1's
    `这 (这儿)` alternate-form convention). Returns the input unchanged when
    there is no parenthetical, so it is safe to call on every headword.
    """
    return re.split(r"[（(]", word)[0].strip()


def load_function_words(path: str | None = None) -> dict[str, str]:
    """headword -> the structural gloss it must carry (#467).

    Returns a plain `{hanzi: gloss}`; the register's `structure` and `pinyin`
    fields are documentation for a human and are deliberately NOT enforced --
    the corpus spells 就 as both `jiù` and `jiǜ`, and that disagreement belongs
    to the def1 check above, not here.
    """
    with open(path or FUNCTION_WORDS, encoding="utf-8") as fh:
        return {k: v["gloss"] for k, v in json.load(fh)["words"].items()}


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
          bank_glob: str, fw_path: str | None = None) -> tuple[int, list[str]]:
    """Return (exit_code, report_lines)."""
    try:
        with open(bank_path, encoding="utf-8") as fh:
            sentences = json.load(fh)["sentences"]
        words = load_wordset(csv_path, wordset_id)
        fw = load_function_words(fw_path)
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

    # #467 -- an EMPTY gloss is not a neutral omission. The social card centres
    # `word.english` at 60pt with no fallback, so a blank one ships a card with a
    # hole where the meaning goes. All nine empties in the corpus at filing were
    # function words (的 了 吗 呢 得 着 过 吧 地), which is the same defect arriving
    # as absence rather than as a wrong word.
    bad = [f"#{s['no']} {s['word']['chinese']}" for s in sentences
           if not (s["word"].get("english") or "").strip()]
    record("every headword carries a non-empty gloss",
           len(sentences) - len(bad), len(sentences), bad)

    # #467 -- the defect itself: 把 shipping as "hold" beside 把书给我, where it is
    # the disposal particle. Exact equality against the register, because the
    # alternative (look for the word "particle") is a heuristic that a future
    # gloss can pass while still naming a content sense.
    reg = [s for s in sentences if s["word"]["chinese"] in fw]
    off = [s for s in reg if (s["word"].get("english") or "") != fw[s["word"]["chinese"]]]
    record("function words carry a registered structural gloss",
           len(reg) - len(off), len(reg),
           sorted({f'{s["word"]["chinese"]} says "{s["word"].get("english") or ""}",'
                   f' register says "{fw[s["word"]["chinese"]]}"' for s in off}))

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
    ap.add_argument("--function-words", default=None,
                    help=f"function-word register (default: {FUNCTION_WORDS})")
    args = ap.parse_args()

    wordset = args.wordset_id
    if wordset is None:
        m = re.search(r"sentences-hsk(\d+)-", os.path.basename(args.bank))
        if not m:
            print("CANNOT-TELL: cannot infer wordset_id from the filename; "
                  "pass --wordset-id", file=sys.stderr)
            return 3
        wordset = m.group(1)

    code, lines = check(args.bank, args.csv, wordset, args.bank_glob,
                        args.function_words)
    print(f"{os.path.basename(args.bank)} (wordset_id {wordset})")
    for line in lines:
        print(line)
    print({0: "PASS", 1: "FAIL", 3: "CANNOT-TELL"}[code])
    return code


if __name__ == "__main__":
    sys.exit(main())
