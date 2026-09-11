"""issue-472: a CORRELATIVE headword's halves appear separately in prose.

`因为……所以……` is the CSV's catalogue key. No sentence contains that literal
string — `因为` and `所以` appear with the clause between them. The containment
check required the joined form and reported four correct sentences as broken
across three banks.

🔴 The fix SPLITS rather than loosens: every half must be present. The test
that matters here is `test_ONE_HALF_IS_NOT_ENOUGH` — without it, "the check
stopped failing" is indistinguishable from "the check stopped checking".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_sentence_bank as m  # noqa: E402


def test_a_correlative_splits_into_its_halves_472():
    assert m.headword_parts("因为……所以……") == ["因为", "所以"]
    assert m.headword_parts("只有……才……") == ["只有", "才"]


def test_everything_else_is_UNCHANGED_472():
    """One part, and it is exactly what `bare_headword` already returned — so
    no existing bank's verdict can move on this change alone."""
    for w in ("聊天", "过（动词）", "这 (这儿)", "盘子"):
        assert m.headword_parts(w) == [m.bare_headword(w)], w


def _run_check(tmp_path, headword, sentence):
    """Drive the REAL `m.check()` over a one-row bank + a matching CSV.

    🔴 An earlier version of this file reimplemented the containment predicate
    locally (`all(p in ... for p in m.headword_parts(...))`) and called that
    the control. It was VACUOUS: mutating `check()`'s `all` to `any` reds
    ZERO tests, because the test never executed the line it claimed to pin.
    Measured, not supposed — the mutation run said RED=0 where I predicted 1.
    The control has to call the consumer, not a copy of it.
    """
    import csv as _csv
    import json as _json
    bank = tmp_path / "sentences-hsk2-9-v1.json"
    bank.write_text(_json.dumps({"sentences": [
        {"no": 1,
         "word": {"no": 1, "chinese": headword, "pinyin": "yīnwèi…suǒyǐ…",
                  "english": "because...so"},
         "chinese": sentence,
         "pinyin": "Yīnwèi xià yǔ, suǒyǐ wǒ méi qù.",
         "english": "Because it rained, I did not go."}]}, ensure_ascii=False),
        encoding="utf-8")
    csvp = tmp_path / "words.csv"
    with open(csvp, "w", encoding="utf-8", newline="") as fh:
        w = _csv.DictWriter(fh, ["word_id", "word", "wordset_id", "def1", "def2"])
        w.writeheader()
        w.writerow({"word_id": "1", "word": headword, "wordset_id": "2",
                    "def1": "yīnwèi…suǒyǐ…", "def2": "because...so"})
    return m.check(str(bank), str(csvp), "2", str(tmp_path / "sentences-*.json"))


def test_both_halves_present_PASSES_472(tmp_path):
    rc, out = _run_check(tmp_path, "因为……所以……", "因为下雨，所以我没去。")
    assert rc == 0, "\n".join(out)


def test_ONE_HALF_IS_NOT_ENOUGH_472(tmp_path):
    """🔴 THE CONTROL, and it now drives `m.check()` rather than a copy.

    Loosening `all` to `any` makes a sentence demonstrating HALF the
    construction pass — which is fixing a false positive by weakening the
    predicate rather than correcting it. This test reds on that mutation;
    the reimplemented version did not."""
    rc, out = _run_check(tmp_path, "因为……所以……", "因为下雨，我没去。")
    assert rc == 1, "only 因为 present — must FAIL"
    assert "appears in its own sentence" in "\n".join(out)
    rc2, _ = _run_check(tmp_path, "因为……所以……", "下雨了，所以我没去。")
    assert rc2 == 1, "only 所以 present — must FAIL"


def test_the_real_bank_that_motivated_this_now_passes_472():
    """hsk3-1-v1 failed ONLY on `不但……而且……`; it is the end-to-end case."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rc, _ = m.check(os.path.join(repo, "sentences/sentences-hsk3-1-v1.json"),
                    os.path.join(repo, "terraform/csv/words.csv"), "3",
                    os.path.join(repo, "sentences/sentences-hsk3-*.json"))
    assert rc == 0, "hsk3-1-v1 should now pass the full battery"
