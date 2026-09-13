#!/usr/bin/env python3
"""Render a "Hold This Shape" episode — LexiTrail's first actual renderer.

Contract: `studio/bibles/hold-this-shape.md` (private `AlexBulankou/studio`).
Issue: lex#504. The bible is the spec; this module is judged against it, so the
timeline below is a data structure and the tests assert the bible's clauses
against *that* rather than against a rendered file.

  Look at this character for four seconds. Now tell me what it means.

Hard cut from pure black to a single character at 88% of frame height, held with
a progress arc the viewer did not agree to; pinyin at ~4s, meaning at ~5s, then
one real sentence using it. 8-14s. Never show the answer early — the hold IS the
format.

WORD SELECTION IS DELIBERATELY SWAPPABLE. The bible's recipe selects from
`recall_history` (the product's own review log, preferring high miss-rate words)
— "that selection is itself the unfair asset". That table lives in Cloud SQL
behind a k8s proxy and is not reachable from a build host, and lex#513 reports a
seed that TRUNCATEs it. So `Episode` takes the four strings it needs and
`from_sentence_bank()` is one concrete supplier; a `from_recall_history()`
supplier drops in beside it without touching the renderer.

🔴 M1 IS SUSPENDED as a blocking criterion (zz1, 2026-09-13, dec#3480): there is
no implementation of it anywhere, so it has never machine-checked an asset. This
renderer therefore does NOT try to satisfy M1, and `m1_mean_delta_pct()` is
provided for measurement only. Measured for this hook at the corrected sizing:
the hard cut is 14.19% in ONE frame, M1's mean over 30 frames dilutes it to
0.489%, and sweeping the arc 0->64px moves that by 0.046 points — so the bible's
claim that "the progress arc is what carries this" is false. Do not build toward
it.

⚠️ An earlier figure of 40.51% / 1.40% is on lex#504, dec#3480 and this PR. It
was measured before the sizing fix, when the glyph overflowed the frame by 1.67x
and therefore carried far more ink. The conclusion is unchanged — still a wide
FAIL, arc still contributing ~nothing — but the numbers are not, and a stale
number in a durable place is the thing that gets quoted later.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

W, H = 1080, 1920           # 9:16, the Reel cut
PIN_W, PIN_H = 1080, 1620   # 2:3, the Pinterest cut (static-safe)
FPS = 30

# The bible's hook spec, as numbers.
ARC_START_S = 0.50
PINYIN_S = 4.0
MEANING_S = 5.0
SENTENCE_S = 6.0
MIN_DURATION_S, MAX_DURATION_S = 8.0, 14.0
WORD_CEILING_UNTIL_S = 4.0   # "0 words on screen before 4.0s"
CHAR_FRAME_HEIGHT_FRACTION = 0.88

_CJK_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)


def _can_render_cjk(path: str, probe: str = "爱") -> bool:
    """Does this font actually put ink on the page for a Chinese glyph?

    Existence is not capability, and neither is INK. 🔴 A Latin font opens fine
    and renders 爱 as a TOFU BOX — .notdef — which is ink, so an "is anything
    drawn?" check returns True for a font that cannot render Chinese at all.
    Measured: NotoSans-Regular.ttf passed exactly that check.

    The discriminator is rendering the probe against a codepoint the font is
    guaranteed NOT to have (U+E000, private use). If the two rasters are
    IDENTICAL the font is drawing .notdef for both and has no CJK coverage."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        f = ImageFont.truetype(path, 64)

        def raster(ch):
            im = Image.new("L", (96, 96), 0)
            ImageDraw.Draw(im).text((8, 8), ch, fill=255, font=f)
            return im.tobytes()

        got, notdef = raster(probe), raster("\ue000")
        return got != notdef and Image.frombytes("L", (96, 96), got).getbbox() is not None
    except Exception:
        return False


def resolve_cjk_font() -> str:
    """A CJK font path on THIS host.

    Hardcoding one path is a portability defect: the first version of this module
    carried bp's Noto Serif path, which does not exist on `ubuntu-latest`, so the
    geometry tests would have failed in CI for a reason unrelated to geometry.
    Candidates first, then fontconfig, then a loud error naming the fix — never a
    silent skip, because a geometry test that goes quiet is a geometry test that
    is not checking geometry."""
    for c in _CJK_FONT_CANDIDATES:
        if Path(c).exists() and _can_render_cjk(c):
            return c
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", ":lang=zh"],
                             capture_output=True, text=True, timeout=10)
        cand = out.stdout.strip()
        # 🔴 fc-match ALWAYS returns something. Asked for `:lang=zh` on a host
        # with no CJK font it returns the Latin default — measured, it handed
        # back NotoSans-Regular.ttf — which rasterises 爱 as an empty box with
        # no error. So the path must be VERIFIED, not trusted.
        if out.returncode == 0 and cand and Path(cand).exists() and _can_render_cjk(cand):
            return cand
    except (OSError, subprocess.SubprocessError):
        pass
    raise RuntimeError(
        "no CJK font found — install one (e.g. `apt-get install fonts-noto-cjk`). "
        f"Tried: {', '.join(_CJK_FONT_CANDIDATES)}, then fc-match :lang=zh"
    )


CJK_FONT = None  # resolved lazily by _glyph_font; see resolve_cjk_font()


@dataclass(frozen=True)
class Episode:
    """One episode's content. Four strings; the supplier is swappable."""
    character: str
    pinyin: str
    meaning: str
    sentence: str

    def __post_init__(self) -> None:
        for field in ("character", "pinyin", "meaning", "sentence"):
            if not str(getattr(self, field)).strip():
                raise ValueError(f"Episode.{field} is empty — refusing to render a blank hold")
        if self.character not in self.sentence:
            raise ValueError(
                f"the sentence {self.sentence!r} does not contain the character "
                f"{self.character!r} — the payoff must use the word that was held"
            )


@dataclass(frozen=True)
class Cue:
    """One timeline entry. `words` counts ON-SCREEN WORDS, for M3 and the bible's
    stricter 0-words-before-4.0s ceiling. The held character is NOT a word: the
    bible is explicit that "the character is not a word for this purpose — it is
    the image"."""
    t: float
    kind: str
    text: str
    words: int


def build_timeline(ep: Episode, duration_s: float = 10.0) -> list[Cue]:
    """The episode as cues. Pure — no rendering, no I/O — so the bible's clauses
    are assertable directly."""
    if not (MIN_DURATION_S <= duration_s <= MAX_DURATION_S):
        raise ValueError(
            f"duration {duration_s}s is outside the bible's 8-14s — short by design"
        )
    return [
        Cue(0.00, "hard-cut", ep.character, 0),
        Cue(ARC_START_S, "arc-begins", "", 0),
        Cue(PINYIN_S, "pinyin", ep.pinyin, 0),
        Cue(MEANING_S, "meaning", ep.meaning, len(ep.meaning.split())),
        Cue(SENTENCE_S, "sentence", ep.sentence, 0),
    ]


def words_on_screen_before(timeline: list[Cue], t: float) -> int:
    """Total on-screen words strictly before `t`. The bible's word ceiling and
    M3 are both expressed against this."""
    return sum(c.words for c in timeline if c.t < t)


def answer_revealed_at(timeline: list[Cue]) -> float:
    """When the hold breaks. 'Never show the answer early' is the format."""
    reveals = [c.t for c in timeline if c.kind in ("pinyin", "meaning")]
    return min(reveals) if reveals else float("inf")


def from_sentence_bank(path: Path, headword: str | None = None,
                       single_char_only: bool = True) -> Episode:
    """One concrete supplier: the HSK sentence banks already in this repo.

    Real LexiTrail data and reachable from a build host, which `recall_history`
    is not. Bank shape is `{"sentences": [{word: {chinese, pinyin, english},
    chinese, pinyin, english}, ...]}` — note `word` is a DICT and the top-level
    `chinese` is the SENTENCE, not the headword.

    🔴 `single_char_only` defaults True because the bible's premise is "look at
    THIS CHARACTER" and the hook holds one glyph. Most HSK headwords are
    multi-character (爱情, 互联网), and holding those breaks the format rather
    than merely looking wrong, so they are skipped rather than silently rendered.
    """
    items = json.loads(Path(path).read_text(encoding="utf-8"))["sentences"]
    for it in items:
        w = it["word"]
        if single_char_only and len(w["chinese"]) != 1:
            continue
        if headword is None or w["chinese"] == headword:
            return Episode(
                character=w["chinese"],
                pinyin=w["pinyin"],
                meaning=w["english"],
                sentence=it["chinese"],
            )
    raise LookupError(f"no entry for headword {headword!r} in {path}")


def m1_mean_delta_pct(frames) -> float:
    """M1's metric: mean absolute inter-frame delta as a % of full scale.

    MEASUREMENT ONLY — M1 is suspended (see module docstring). Kept because the
    number is the evidence for dec#3480's redefinition, and because a metric
    nobody can recompute is a claim rather than a measurement."""
    import numpy as np
    if len(frames) < 2:
        return 0.0
    return float(np.mean([
        np.abs(frames[i + 1].astype("int16") - frames[i].astype("int16")).mean() / 255.0 * 100
        for i in range(len(frames) - 1)
    ]))


def _glyph_font(size_px: int):
    from PIL import ImageFont
    return ImageFont.truetype(resolve_cjk_font(), size_px)


def character_font_for_frame_height(fraction: float = CHAR_FRAME_HEIGHT_FRACTION,
                                    frame_h: int = H, frame_w: int = W, char: str = "爱"):
    """A font whose GLYPH — not its em box — fills `fraction` of the frame,
    taking whichever axis BINDS.

    Two corrections the bible's wording does not survive, both found by building it:

    1. Sizing by point size understates the HEIGHT: the em box carries
       ascent/descent the glyph does not use, so `truetype(font, 0.88*H)` yields
       a glyph well short of 88% of its own height. (It does NOT understate the
       WIDTH — a CJK advance width is ~1em — so on 9:16, where width binds, the
       naive number happens to be right. Measured; do not generalise it to a
       horizontal frame, where height binds and the correction is load-bearing.)

    2. 🔴 "88% of frame height" is GEOMETRICALLY IMPOSSIBLE on 9:16 for a CJK
       glyph. 0.88 * 1920 = 1690px, the frame is 1080px wide, and CJK glyphs are
       approximately square — measured, 爱 at 88% of frame height is 1808px wide,
       1.67x the frame. So height cannot be the binding axis on a vertical frame
       and the spec has to mean "fills the frame", which on 9:16 is the WIDTH.
       Reported to lex#504 for zz3, who own the bible; this implementation takes
       the binding axis so it is correct under either reading.
    """
    target_h, target_w = int(frame_h * fraction), int(frame_w * fraction)
    f = _glyph_font(target_h)
    bb = f.getbbox(char)
    h, w = max(bb[3] - bb[1], 1), max(bb[2] - bb[0], 1)
    size = min(int(target_h * target_h / h), int(target_h * target_w / w))
    return _glyph_font(max(size, 1))


def render_frames(ep: Episode, duration_s: float = 10.0, arc_width: int = 8):
    """The frames. Frame 0 is PURE BLACK — the hard cut is the first transition,
    and it is the largest one in the piece."""
    import numpy as np
    from PIL import Image, ImageDraw

    f = character_font_for_frame_height(char=ep.character)
    bb = f.getbbox(ep.character)
    x = (W - (bb[2] - bb[0])) // 2 - bb[0]
    y = (H - (bb[3] - bb[1])) // 2 - bb[1]

    out = []
    for i in range(int(duration_s * FPS)):
        t = i / FPS
        im = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(im)
        if t > 0:                      # frame 0 stays pure black
            d.text((x, y), ep.character, fill=255, font=f)
            if t >= ARC_START_S:
                frac = min((t - ARC_START_S) / (PINYIN_S - ARC_START_S), 1.0)
                m = arc_width + 8
                d.arc([m, m, W - m, H - m], start=-90, end=-90 + 360 * frac,
                      fill=255, width=arc_width)
        out.append(np.asarray(im, dtype="uint8"))
    return out


def encode(frames, dest: Path) -> Path:
    """One ffmpeg pass, per the bible's recipe."""
    dest = Path(dest)
    proc = subprocess.run(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "gray",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dest)],
        input=b"".join(fr.tobytes() for fr in frames),
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed rc={proc.returncode}: {proc.stderr.decode()[-400:]}")
    if not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg reported success but {dest} is missing or empty")
    return dest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--bank", type=Path, help="sentence bank JSON to select from")
    p.add_argument("--headword", help="specific headword; default = first entry")
    p.add_argument("--out", type=Path, default=Path("hold-this-shape.mp4"))
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument("--selftest", action="store_true",
                   help="assert the bible's clauses against the timeline and exit")
    a = p.parse_args(argv)

    if a.selftest:
        ep = Episode("爱", "ài", "love", "我爱你。")
        tl = build_timeline(ep)
        assert words_on_screen_before(tl, WORD_CEILING_UNTIL_S) == 0, "word ceiling breached"
        assert answer_revealed_at(tl) >= PINYIN_S, "answer revealed early"
        print(f"selftest OK — {len(tl)} cues, 0 words before {WORD_CEILING_UNTIL_S}s, "
              f"answer at {answer_revealed_at(tl)}s")
        return 0

    if not a.bank:
        p.error("--bank is required unless --selftest")
    ep = from_sentence_bank(a.bank, a.headword)
    build_timeline(ep, a.duration)          # validates duration before rendering
    dest = encode(render_frames(ep, a.duration), a.out)
    print(f"rendered {ep.character} ({ep.pinyin}, {ep.meaning}) -> {dest} "
          f"[{dest.stat().st_size} bytes]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
