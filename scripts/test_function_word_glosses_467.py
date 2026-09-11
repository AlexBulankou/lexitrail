"""The whole sentence corpus, one property: no function word under a content gloss (#467).

check_sentence_bank.py validates ONE bank, by hand, before it is merged. That is
the right tool for a bank being written and the wrong one for this defect,
because the defect is already IN the committed corpus and no future bank has to
be written for it to publish: 把 was scheduled to Instagram for 2026-09-12 as
"hold" beside 把书给我, where 把 is the disposal particle and carries no lexical
sense at all. It also renders on 把's generated word page, which Google indexes.
A per-bank tool that nobody re-runs over the fourteen existing banks cannot see
either surface.

🔴 THIS SWEEP IS DELIBERATELY NARROW, and that is the load-bearing decision.
FOUR of the fourteen banks already FAIL check_sentence_bank.py's full verdict on
main -- hsk2-1-v1, hsk2-1-v2, hsk2-2-v1 and hsk3-1-v1, for duplicate v1/v2
coverage, correlative headwords (因为……所以……) that never appear verbatim in a
sentence, and two def1 mismatches. Asserting the whole verdict here would import
four pre-existing failures and land red, and a guard that is red on arrival gets
deleted rather than fixed. Asserting ONE property makes it green the moment
#467's data lands and red the moment a bank reintroduces the defect.

⚠️ The non-vacuity test at the bottom is not ceremony. The two sweeps below are
`assert not [x for x in population if broken(x)]`, which passes loudly on an
EMPTY population -- so a renamed directory, a changed filename convention or an
emptied register would turn this file green while it checks nothing.
"""
from __future__ import annotations

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_sentence_bank as m  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANKS = sorted(glob.glob(os.path.join(REPO, "sentences", "sentences-*.json")))
REGISTER = os.path.join(REPO, "sentences", "function-words.json")


def _entries():
    """(bank filename, sentence) for every sentence in every committed bank."""
    for path in BANKS:
        with open(path, encoding="utf-8") as fh:
            for s in json.load(fh)["sentences"]:
                yield os.path.basename(path), s


def test_no_bank_ships_a_registered_function_word_under_another_gloss():
    """把 must not say "hold". The register is the single source of the answer."""
    fw = m.load_function_words()
    wrong = [f'{bank} #{s["no"]} {s["word"]["chinese"]}: '
             f'"{s["word"].get("english") or ""}" != "{fw[s["word"]["chinese"]]}"'
             for bank, s in _entries()
             if s["word"]["chinese"] in fw
             and (s["word"].get("english") or "") != fw[s["word"]["chinese"]]]
    assert not wrong, (
        "a function word is glossed as a content word -- the card would teach a "
        "sense its own example does not demonstrate:\n  " + "\n  ".join(wrong))


def test_no_headword_in_any_bank_carries_an_EMPTY_gloss():
    """The other half of the same defect, arriving as absence.

    The social card centres `word.english` at 60pt with no fallback and no
    placeholder, so an empty gloss ships a card with a hole where the meaning
    goes. All nine empties in the corpus at filing were function words.
    """
    blank = [f'{bank} #{s["no"]} {s["word"]["chinese"]}'
             for bank, s in _entries()
             if not (s["word"].get("english") or "").strip()]
    assert not blank, (
        "these headwords would render a blank gloss slot:\n  " + "\n  ".join(blank))


def test_the_register_covers_the_class_named_in_the_issue():
    """Coverage is asserted against the NAMED list, not against what the corpus
    happens to contain today -- 才 is registered and appears in no bank yet, and
    that is the point: the twenty-one banks still to be written for #433 must hit
    a register that already has an answer for them.

    A word may be ENFORCED or DEFERRED, and deferred is a real answer rather than
    an escape hatch: 被's card is internally consistent today (a 'cover' gloss over
    a 被子 sentence), so correcting its sense means changing its SENTENCES, which
    lands on an indexed page whose gloss comes from words.csv. What is not allowed
    is a named word appearing in neither list, or a deferral with no reason.
    """
    with open(REGISTER, encoding="utf-8") as fh:
        reg = json.load(fh)
    covered = set(reg["words"]) | set(reg.get("deferred", {}))
    named = ["把", "了", "着", "过", "得", "被", "就", "才", "呢", "吧", "地", "的", "吗"]
    assert not [w for w in named if w not in covered], (
        f"named by the issue and in neither list: {[w for w in named if w not in covered]}")
    for word, entry in reg.get("deferred", {}).items():
        assert entry.get("reason"), f"{word} is deferred with no reason recorded"


def test_a_DEFERRED_word_is_not_enforced_and_is_not_silently_enforced_either():
    """load_function_words() reads `words` only. If a later edit folded `deferred`
    in, 被 would go red across the corpus for a change nobody made to a bank."""
    fw = m.load_function_words()
    with open(REGISTER, encoding="utf-8") as fh:
        deferred = set(json.load(fh).get("deferred", {}))
    assert deferred, "the deferred list is empty -- update this test with the residual"
    assert not (deferred & set(fw)), f"deferred words leaked into the contract: {deferred & set(fw)}"


def test_the_register_is_keyed_on_WHOLE_headwords_not_characters():
    """地方 / 地铁 / 地图 / 过去 / 了解 / 过（动词） are content words that begin with a
    registered character. A substring rule would rewrite six correct glosses to
    close one defect, so the key must be the full headword string."""
    fw = m.load_function_words()
    for content in ("地方", "地铁", "地图", "过去", "了解", "过（动词）"):
        assert content not in fw, f"{content} is a content word; it must not be registered"


def test_the_sweep_is_NOT_VACUOUS():
    """Every assertion above passes on an empty population."""
    assert len(BANKS) >= 10, f"found {len(BANKS)} banks -- the glob or the directory moved"
    fw = m.load_function_words()
    assert len(fw) >= 10, f"the register holds {len(fw)} entries"
    seen = {s["word"]["chinese"] for _, s in _entries() if s["word"]["chinese"] in fw}
    assert len(seen) >= 10, (
        f"the sweep matched only {sorted(seen)} -- if the banks stopped carrying "
        "function words this file is asserting nothing")
