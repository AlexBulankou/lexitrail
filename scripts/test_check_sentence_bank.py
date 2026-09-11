"""Tests for check_sentence_bank.py (#433).

Every check gets a NEGATIVE arm as well as a positive one. A validator whose
checks have only ever returned PASS has not been tested, it has been run -- and
the two failures this script was written for both *reported a clean bank as
broken*, so the arm that matters is the one where a correct bank must come back
green.

The two encoded traps get dedicated regression tests, because both are invisible
in a passing run:
  * wordset_trap  -- a headword at wordset 8 but not 3 must FAIL, and a headword
                     present in BOTH must PASS (the dict-keeps-last bug).
  * parenthetical -- `过（动词）` with `过` in the sentence must PASS.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_sentence_bank as m  # noqa: E402

CSV = "word_id,word,wordset_id,def1,def2\n" \
      "1,好,3,hǎo,good\n" \
      "2,过（动词）,3,guò,pass\n" \
      "3,好,8,hǎo,good\n" \
      "4,只在八,8,bā,only-in-8\n"


def _sentence(no, wno, word, pinyin, chinese, sp):
    return {"no": no, "word": {"no": wno, "chinese": word, "pinyin": pinyin,
                               "english": "x"},
            "chinese": chinese, "pinyin": sp, "english": "x"}


def _write(tmp_path, sentences, csv_text=CSV):
    bank = tmp_path / "sentences-hsk3-9-v1.json"
    bank.write_text(json.dumps({"sentences": sentences}, ensure_ascii=False),
                    encoding="utf-8")
    csvp = tmp_path / "words.csv"
    csvp.write_text(csv_text, encoding="utf-8")
    return str(bank), str(csvp), str(tmp_path / "sentences-*.json")


def _good():
    return [_sentence(1, 1, "好", "hǎo", "今天天气很好。", "Jīntiān tiānqì hěn hǎo."),
            _sentence(2, 1, "好", "hǎo", "他是好人。", "Tā shì hǎo rén.")]


def _run(tmp_path, sentences, csv_text=CSV):
    b, c, g = _write(tmp_path, sentences, csv_text)
    return m.check(b, c, "3", g)


# ── positive control ────────────────────────────────────────────────────────
def test_a_valid_bank_passes(tmp_path):
    code, lines = _run(tmp_path, _good())
    assert code == 0, "\n".join(lines)


# ── the two encoded traps ───────────────────────────────────────────────────
def test_headword_in_BOTH_wordsets_passes_not_keyed_on_the_last_row(tmp_path):
    """好 is at wordset 3 AND 8. Keying a dict on `word` keeps the 8 and reports
    a false failure -- the exact bug that read 0/25 on a correct bank."""
    code, lines = _run(tmp_path, _good())
    assert code == 0, "好 is present at wordset 3; it must not be judged by its wordset-8 row"


def test_headword_only_in_another_wordset_FAILS(tmp_path):
    """The negative arm: the filter must still exclude a genuinely absent word."""
    s = [_sentence(1, 1, "只在八", "bā", "只在八。", "Bā."),
         _sentence(2, 1, "只在八", "bā", "这是只在八。", "Zhè shì bā.")]
    code, _ = _run(tmp_path, s)
    assert code == 1, "a headword absent from wordset 3 must FAIL"


def test_pos_tagged_headword_passes_with_the_bare_form_in_the_sentence(tmp_path):
    """`过（动词）` never appears in prose; `过` does. A naive containment check
    reports 0/N here on correct sentences."""
    s = [_sentence(1, 1, "过（动词）", "guò", "请小心过马路。", "Qǐng guò mǎlù."),
         _sentence(2, 1, "过（动词）", "guò", "我们过了那座桥。", "Wǒmen guòle qiáo.")]
    code, lines = _run(tmp_path, s)
    assert code == 0, "\n".join(lines)


def test_bare_headword_strips_both_paren_styles():
    assert m.bare_headword("过（动词）") == "过"      # fullwidth, HSK3 POS tag
    assert m.bare_headword("这 (这儿)") == "这"       # ASCII, HSK1 alternate form
    assert m.bare_headword("句子") == "句子"          # unchanged when absent


# ── one negative arm per check ──────────────────────────────────────────────
def test_pinyin_not_matching_def1_FAILS(tmp_path):
    s = _good(); s[0]["word"]["pinyin"] = "hao"
    assert _run(tmp_path, s)[0] == 1


def test_headword_missing_from_its_sentence_FAILS(tmp_path):
    s = _good(); s[0]["chinese"] = "今天天气很棒。"
    assert _run(tmp_path, s)[0] == 1


def test_pinyin_without_tone_marks_FAILS(tmp_path):
    s = _good(); s[0]["pinyin"] = "Jintian tianqi hen hao."
    assert _run(tmp_path, s)[0] == 1


def test_pinyin_not_capitalised_FAILS(tmp_path):
    s = _good(); s[0]["pinyin"] = "jīntiān tiānqì hěn hǎo."
    assert _run(tmp_path, s)[0] == 1


def test_non_contiguous_numbering_FAILS(tmp_path):
    s = _good(); s[1]["no"] = 7
    assert _run(tmp_path, s)[0] == 1


def test_headword_already_covered_by_another_bank_FAILS(tmp_path):
    b, c, g = _write(tmp_path, _good())
    (tmp_path / "sentences-hsk3-1-v1.json").write_text(
        json.dumps({"sentences": [_sentence(1, 1, "好", "hǎo", "好。", "Hǎo.")]},
                   ensure_ascii=False), encoding="utf-8")
    assert m.check(b, c, "3", g)[0] == 1


# ── CANNOT-TELL is its own state, never folded into PASS or FAIL ────────────
def test_empty_bank_is_CANNOT_TELL_not_pass(tmp_path):
    assert _run(tmp_path, [])[0] == 3


def test_missing_bank_file_is_CANNOT_TELL(tmp_path):
    _, c, g = _write(tmp_path, _good())
    assert m.check(str(tmp_path / "nope.json"), c, "3", g)[0] == 3


def test_wordset_with_no_rows_is_CANNOT_TELL_not_a_clean_fail(tmp_path):
    """An unknown wordset must refuse to compare rather than report every
    headword missing -- otherwise a typo'd --wordset-id reads as a broken bank."""
    b, c, g = _write(tmp_path, _good())
    assert m.check(b, c, "99", g)[0] == 3
