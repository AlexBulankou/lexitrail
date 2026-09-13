"""lex#504 — the renderer is judged against studio/bibles/hold-this-shape.md.

Each test names the bible clause it pins. Where a test could pass vacuously it
carries a control that MUST fail, because a hold-format renderer is exactly the
kind of thing whose tests all pass on a blank video.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_hold_this_shape import (  # noqa: E402
    ARC_START_S, CHAR_FRAME_HEIGHT_FRACTION, FPS, H, MAX_DURATION_S,
    MEANING_S, MIN_DURATION_S, PINYIN_S, W, WORD_CEILING_UNTIL_S, Episode,
    answer_revealed_at, build_timeline, character_font_for_frame_height,
    from_sentence_bank, m1_mean_delta_pct, render_frames,
    words_on_screen_before,
)

EP = Episode("爱", "ài", "love", "我爱你。")


# ── the bible: "0 words on screen before 4.0s" ────────────────────────────────

def test_word_ceiling_zero_words_before_4s():
    assert words_on_screen_before(build_timeline(EP), WORD_CEILING_UNTIL_S) == 0


def test_CONTROL_the_word_counter_can_return_nonzero():
    """Without this, the test above passes on a counter wired to return 0."""
    assert words_on_screen_before(build_timeline(EP), MEANING_S + 0.1) > 0


# ── the bible: "Never show the answer early — the hold is the format" ─────────

def test_answer_is_not_revealed_before_the_pinyin_beat():
    assert answer_revealed_at(build_timeline(EP)) >= PINYIN_S


def test_CONTROL_answer_revealed_at_can_detect_an_early_reveal():
    tl = [c for c in build_timeline(EP)]
    early = type(tl[0])(1.0, "meaning", "love", 1)
    assert answer_revealed_at(tl + [early]) == 1.0


# ── the bible: "Length 8-14s. Short by design." ───────────────────────────────

@pytest.mark.parametrize("d", [MIN_DURATION_S, 10.0, MAX_DURATION_S])
def test_durations_inside_the_band_are_accepted(d):
    assert build_timeline(EP, d)


@pytest.mark.parametrize("d", [7.9, 14.1, 0.0, 60.0])
def test_durations_outside_the_band_are_REFUSED(d):
    with pytest.raises(ValueError, match="8-14s"):
        build_timeline(EP, d)


# ── the bible: "a single character at 88% of frame height" ────────────────────

def test_the_glyph_fills_88_percent_of_the_BINDING_axis_and_FITS_the_frame():
    """🔴 The bible says "88% of frame height". On 9:16 that is impossible:
    0.88*1920 = 1690px and the frame is 1080px wide, while CJK glyphs are ~square
    — measured, 爱 sized to 88% of frame HEIGHT is 1808px wide, 1.67x the frame.
    So the renderer takes the binding axis (width, on a vertical frame). Reported
    to lex#504 for zz3. This test pins FITTING, which the height-only version of
    it did not — that is how the overflow shipped past 27 green tests."""
    for ch in ("爱", "光", "厚"):
        f = character_font_for_frame_height(char=ch)
        bb = f.getbbox(ch)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        assert w <= W and h <= H, f"{ch} glyph {w}x{h} overflows the {W}x{H} frame"
        binding = max(w / W, h / H)
        assert abs(binding - CHAR_FRAME_HEIGHT_FRACTION) < 0.02, (
            f"{ch} fills {binding:.3f} of its binding axis, bible says "
            f"{CHAR_FRAME_HEIGHT_FRACTION}"
        )


def test_CONTROL_the_literal_88_percent_of_HEIGHT_reading_really_does_overflow():
    """Pins the geometric fact the correction rests on. If this ever fails, the
    bible's literal wording has become implementable and the note above is stale."""
    from PIL import ImageFont
    from render_hold_this_shape import resolve_cjk_font
    target = int(H * CHAR_FRAME_HEIGHT_FRACTION)
    f = ImageFont.truetype(resolve_cjk_font(), target)
    bb = f.getbbox("爱")
    scaled = ImageFont.truetype(resolve_cjk_font(), int(target * target / max(bb[3] - bb[1], 1)))
    bb2 = scaled.getbbox("爱")
    assert bb2[2] - bb2[0] > W, (
        "a glyph at 88% of frame HEIGHT now fits the frame width — re-check the bible note"
    )


def test_multi_character_headwords_are_SKIPPED_by_default(tmp_path):
    """The bible holds "a single character". Most HSK headwords are not one
    (爱情, 互联网) and holding those breaks the format, so they are skipped
    rather than silently rendered — which is what the first render did."""
    bank = tmp_path / "b.json"
    bank.write_text(json.dumps({"sentences": [
        {"no": 1, "word": {"chinese": "爱情", "pinyin": "àiqíng", "english": "love"},
         "chinese": "这是一个爱情故事。"},
        {"no": 2, "word": {"chinese": "光", "pinyin": "guāng", "english": "light"},
         "chinese": "光很亮。"},
    ]}, ensure_ascii=False), encoding="utf-8")
    assert from_sentence_bank(bank).character == "光", "picked a multi-character headword"
    assert from_sentence_bank(bank, single_char_only=False).character == "爱情"


# ── the bible: "Hard cut from pure black" ─────────────────────────────────────

def test_frame_zero_is_pure_black_and_frame_one_is_not():
    fr = render_frames(EP, duration_s=MIN_DURATION_S)
    assert fr[0].max() == 0, "frame 0 must be PURE black — the cut is the first transition"
    assert fr[1].max() > 0, "frame 1 must carry the character"


def test_the_hard_cut_is_the_largest_transition_in_the_first_second():
    import numpy as np
    fr = render_frames(EP, duration_s=MIN_DURATION_S)[:FPS]
    d = [float(np.abs(fr[i + 1].astype("int16") - fr[i].astype("int16")).mean())
         for i in range(len(fr) - 1)]
    assert d[0] == max(d) and d[0] > 0, "the cut should dominate; it is the format's only big move"


# ── the bible: the arc begins at 0.50s and MOVES ──────────────────────────────

def test_the_arc_begins_at_0_50s_and_not_before():
    import numpy as np
    fr = render_frames(EP, duration_s=MIN_DURATION_S, arc_width=32)
    before = int((ARC_START_S - 0.1) * FPS)
    assert np.array_equal(fr[before], fr[before - 1]), "nothing may move before the arc"
    after = int((ARC_START_S + 0.2) * FPS)
    assert not np.array_equal(fr[after], fr[after - 1]), "the arc must visibly move"


# ── M1 is SUSPENDED — this pins the MEASUREMENT, not a gate ───────────────────

def test_m1_is_recorded_as_FAILING_and_the_arc_does_not_rescue_it():
    """zz1 suspended M1 (dec#3480). Pinned so the bible's claim that 'the
    progress arc is what carries this' cannot quietly be believed again."""
    thin = m1_mean_delta_pct(render_frames(EP, duration_s=1.0, arc_width=4))
    fat = m1_mean_delta_pct(render_frames(EP, duration_s=1.0, arc_width=64))
    assert thin < 12.0 and fat < 12.0, "M1 now passes — re-measure before trusting dec#3480"
    assert fat - thin < 1.0, (
        f"a 4->64px arc moved M1 by {fat - thin:.3f} points; the bible says the arc "
        f"carries M1 and the measurement says it contributes almost nothing"
    )


def test_CONTROL_m1_metric_can_return_a_PASSING_value():
    """Otherwise the test above is satisfied by a metric that always returns 0."""
    import numpy as np
    alternating = [np.full((8, 8), 0 if i % 2 else 255, dtype="uint8") for i in range(10)]
    assert m1_mean_delta_pct(alternating) > 12.0


# ── Episode refuses content that would render a broken episode ────────────────

@pytest.mark.parametrize("kw", [
    {"character": ""}, {"pinyin": "  "}, {"meaning": ""}, {"sentence": ""},
])
def test_empty_fields_are_REFUSED(kw):
    base = {"character": "爱", "pinyin": "ài", "meaning": "love", "sentence": "我爱你。"}
    with pytest.raises(ValueError):
        Episode(**{**base, **kw})


def test_a_sentence_that_does_not_use_the_held_character_is_REFUSED():
    """The payoff must use the word that was held, or the episode has no payoff."""
    with pytest.raises(ValueError, match="does not contain"):
        Episode("爱", "ài", "love", "今天天气很好。")


# ── the supplier is swappable, and reads the REAL bank shape ──────────────────

def test_from_sentence_bank_reads_a_real_bank_in_this_repo():
    bank = Path(__file__).resolve().parents[1] / "sentences" / "sentences-hsk4-1-v1.json"
    if not bank.exists():
        pytest.skip(f"{bank.name} not present")
    ep = from_sentence_bank(bank)
    assert ep.character and ep.pinyin and ep.meaning
    assert ep.character in ep.sentence


def test_from_sentence_bank_uses_the_NESTED_word_dict_not_the_top_level_chinese(tmp_path):
    """Top-level `chinese` is the SENTENCE; the headword is `word.chinese`.
    Getting this backwards renders the sentence as the held character."""
    bank = tmp_path / "b.json"
    bank.write_text(json.dumps({"sentences": [{
        "no": 1,
        "word": {"chinese": "爱", "pinyin": "ài", "english": "love"},
        "chinese": "我爱你。", "pinyin": "wǒ ài nǐ.", "english": "I love you.",
    }]}, ensure_ascii=False), encoding="utf-8")
    ep = from_sentence_bank(bank)
    assert ep.character == "爱", "held the sentence instead of the headword"
    assert ep.sentence == "我爱你。"


def test_an_unknown_headword_is_an_error_not_a_silent_first_entry(tmp_path):
    bank = tmp_path / "b.json"
    bank.write_text(json.dumps({"sentences": [{
        "no": 1, "word": {"chinese": "爱", "pinyin": "ài", "english": "love"},
        "chinese": "我爱你。",
    }]}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(LookupError):
        from_sentence_bank(bank, headword="没有")


# ── the CLI ───────────────────────────────────────────────────────────────────

def test_selftest_exits_zero():
    r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent /
                                           "render_hold_this_shape.py"), "--selftest"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "selftest OK" in r.stdout


# ── font resolution: existence is not capability, and INK is not capability ───

def test_a_latin_font_is_REJECTED_as_a_cjk_font():
    """🔴 A Latin font renders 爱 as a TOFU box, which is ink — so an
    "is anything drawn?" check passes it. Measured: fc-match ':lang=zh' on a
    host with no CJK font returns NotoSans-Regular.ttf, and the first version of
    _can_render_cjk accepted it. The renderer would then have produced boxes
    with no error at all."""
    from render_hold_this_shape import _can_render_cjk
    latin = Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf")
    if not latin.exists():
        pytest.skip("no Latin Noto to test against")
    assert _can_render_cjk(str(latin)) is False


def test_a_real_cjk_font_is_ACCEPTED():
    """The other arm — without it, the test above is satisfied by a predicate
    that rejects everything."""
    from render_hold_this_shape import _can_render_cjk, resolve_cjk_font
    assert _can_render_cjk(resolve_cjk_font()) is True


def test_no_cjk_font_RAISES_rather_than_returning_a_latin_one(monkeypatch):
    import render_hold_this_shape as m
    monkeypatch.setattr(m, "_CJK_FONT_CANDIDATES", ())
    monkeypatch.setattr(m.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no fc-match")))
    with pytest.raises(RuntimeError, match="no CJK font"):
        m.resolve_cjk_font()
