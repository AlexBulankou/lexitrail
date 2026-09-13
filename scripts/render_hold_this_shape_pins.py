"""lex#504 — the Pinterest cut: 2:3, static-safe, the SAME frames as the Reel.

Extracted from `render_hold_this_shape.py` rather than folded in: that module
reached 508/500 with this in it, and the only way to keep it there was to
compress the finding below. A cap does not reject a correction, it selects for a
shortened one, and nothing downstream records that a fuller version existed.

The seam is a real one. The bible makes Pinterest the PRIMARY surface and the
Reel the cut-down, and this is a different ARTEFACT — stills, not video — off
the same timeline and the same drawing. The parent imports this lazily, inside
`main()`, so the dependency runs one way only.

Contract: `studio/bibles/hold-this-shape.md` (private `AlexBulankou/studio`).
"""

from __future__ import annotations

from pathlib import Path

from render_hold_this_shape import (
    FPS, Episode, Cue, build_timeline, render_frames,
)

PIN_W, PIN_H = 1080, 1620   # 2:3


def pin_beats(timeline: list[Cue], duration_s: float = 10.0,
              settle_s: float = 0.5) -> list[tuple[str, float]]:
    """The instants a pin sequence is cut at, DERIVED from the timeline.

    Not hardcoded: if the bible moves a beat, `build_timeline` moves with it and
    so do the pins. A second copy of 4.0/5.0/6.0 here would be a contract in two
    places that agree until someone edits one.

    `settle_s` after each cue, because a cue at exactly `t` is the frame the text
    APPEARS on and sampling the boundary is how you get a still that may or may
    not contain it depending on rounding.

    The first pin is the HOLD — character and arc, no words. That is the hook and
    it is the one that must not be dropped for looking empty: the bible's whole
    claim is that a held image with a timer is a question, and a pin sequence
    that opens on the answer has thrown the format away.
    """
    first_payoff = min(c.t for c in timeline
                       if c.kind in ("pinyin", "meaning", "sentence"))
    # 🔴 NOT `max(..., 0.0)`. Frame 0 is PURE BLACK by design (the hard cut), so
    # clamping the hold to 0.0 makes the hero pin a blank image -- silently, and
    # none of the other assertions here would notice: a black frame still DIFFERS
    # from the pinyin frame, so the join test passes, and `hold_t < PINYIN_S`
    # passes too. Found by hc2@ reviewing lex#521 by asking what happens if the
    # first payoff beat lands before 1.0s; reproduced (mean pixel 0.0000).
    #
    # Unreachable on today's constants -- PINYIN_S is 4.0 -- which is exactly the
    # shape worth guarding: it holds by a property of the CONSTANTS, not the code.
    hold_t = max(first_payoff - 1.0, 1.0 / FPS)
    if hold_t >= first_payoff:
        raise ValueError(
            f"no room for a hold: the first payoff beat is at {first_payoff}s and "
            f"the earliest non-black frame is {1.0 / FPS:.3f}s. The hold IS the "
            "format -- refuse rather than ship a pin sequence that opens on the answer")
    beats = [("1-hold", hold_t)]
    for c in sorted((c for c in timeline if c.kind in ("pinyin", "meaning", "sentence")),
                    key=lambda c: c.t):
        t = c.t + settle_s
        if t < duration_s:
            beats.append((f"{len(beats) + 1}-{c.kind}", t))
    return beats


def pin_sequence(ep: Episode, duration_s: float = 10.0, arc_width: int = 8):
    """The Pinterest cut: 2:3, static-safe, the SAME frames as the Reel.

    "Static-safe" is the bible's word and it is a constraint on the ARTEFACT, not
    a different render: Pinterest is an evergreen search surface, so it gets real
    stills rather than a video thumbnail. Same timeline, same drawing, 2:3 frame,
    sampled at the beats.

    🔴 2:3 is why `character_font_for_frame_height` takes the BINDING AXIS. At
    1080x1620, 88% of height is 1425px in a 1080px-wide frame — the same
    impossibility that function documents for 9:16, and it would silently draw a
    glyph wider than the pin. Width binds here too; the function already handles
    it, which is the whole reason this cut is a parameter and not a fork.
    """
    frames = render_frames(ep, duration_s, arc_width, frame=(PIN_W, PIN_H))
    out = []
    for label, t in pin_beats(build_timeline(ep, duration_s), duration_s):
        i = min(int(round(t * FPS)), len(frames) - 1)
        out.append((label, frames[i]))
    return out


def write_pins(pins, outdir: Path) -> list[Path]:
    """PNG per beat. Returns the paths in sequence order."""
    from PIL import Image
    outdir.mkdir(parents=True, exist_ok=True)
    written = []
    for label, arr in pins:
        dest = outdir / f"{label}.png"
        Image.fromarray(arr, mode="L").save(dest)
        written.append(dest)
    return written


