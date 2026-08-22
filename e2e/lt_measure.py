"""Measurement primitives for the tap-target harness (lexitrail#163).

Split out of `tap_targets.py`, which had reached exactly 500/500 lines — the
file cap — leaving no room for the next route. Extracting THIS half rather than
the routes half is deliberate: routes are the part that grows (every new journey
adds an entry callable, a marker and a fixture), so the headroom belongs to the
file they live in.

What is here: the floor, what counts as a control, the viewport matrix, the
measured `Control` record, and `_measure`. All of it is pure — no navigation, no
knowledge of Lexitrail's journeys, no site-specific strings. That is the seam:
this module could measure any page.

What is deliberately NOT here: `ANALYTICS_RE` and the request-abort it drives
(harness/interception, not measurement) and everything route-shaped. The
dependency runs one way, `tap_targets` -> here, so there is no cycle and no
import-time surprise.
"""
from __future__ import annotations

from dataclasses import dataclass

# lexitrail#163 review (hc2): `_measure` catches PlaywrightError, and an import
# does NOT carry across a module boundary -- each module has its own globals. The
# extraction left this name undefined here, so the detach/re-render race stopped
# degrading gracefully and started raising NameError, masking the original error.
# Not a purity violation: this is the Playwright API, the same category as the
# module already requiring `page` to be a Playwright page. Site knowledge is what
# stays out, not the driver.
from playwright.sync_api import Error as PlaywrightError

EXIT_PASS, EXIT_FAIL, EXIT_BLIND = 0, 1, 2
_OUTCOME = {EXIT_PASS: "PASS", EXIT_FAIL: "FAIL", EXIT_BLIND: "BLIND"}

#: The shared floor. Mirrors `--min-tap-target` in ui/src/styles/Global.css and
#: FLOOR_PX in tapTargets.test.js. Kept as a plain number here on purpose: this
#: harness must be able to disagree with the CSS, which is the entire point.
FLOOR_PX = 44.0

#: What counts as a control the user is expected to hit.
INTERACTIVE_SELECTOR = (
    "button, a[href], [role=button], input[type=submit], "
    "input[type=button], input[type=checkbox], input[type=radio], select")

VIEWPORTS = {
    "mobile": {"viewport": {"width": 390, "height": 844}, "is_mobile": True,
               "has_touch": True, "device_scale_factor": 3},
    # 1440x900 is doc 2.5's HARD RULE for desktop, and 390x844 is its iPhone 13
    # mobile. Matching them exactly so a finding here is comparable to a finding
    # from a manual ITP pass rather than needing a viewport caveat attached.
    "desktop": {"viewport": {"width": 1440, "height": 900}},
    # issue-45 / R3-BUG-4: the ITP reported "landscape practice renders one
    # card". Until now the matrix was PORTRAIT-ONLY (390x844 and 1440x900 are
    # both taller than wide), so that half of the bug was not merely unfixed --
    # it was structurally unmeasurable, and a green run said nothing about it.
    # 844x390 is the SAME iPhone 13 device rotated, deliberately: a difference
    # between this row and `mobile` is then attributable to orientation alone
    # and not to a second device's dimensions.
    "mobile_landscape": {"viewport": {"width": 844, "height": 390},
                         "is_mobile": True, "has_touch": True,
                         "device_scale_factor": 3},
}


@dataclass
class Control:
    """One measured control. `key` groups repeats (a wordset grid renders the
    same button once per set), so the report names a defect once with a count
    rather than seven times."""
    key: str
    tag: str
    text: str
    width: float
    height: float

    @property
    def undersized(self) -> bool:
        return self.width < FLOOR_PX or self.height < FLOOR_PX

    @property
    def short_side(self) -> float:
        return min(self.width, self.height)


def _measure(page) -> list[Control]:
    """Measure every VISIBLE interactive control's rendered box.

    Invisible elements are skipped rather than counted as passing: an element
    with no box has no tap target, and scoring it as compliant would be the
    reassuring-direction failure this harness exists to remove.
    """
    out: list[Control] = []
    for el in page.query_selector_all(INTERACTIVE_SELECTOR):
        try:
            if not el.is_visible():
                continue
            box = el.bounding_box()
            if not box:
                continue
            cls = (el.get_attribute("class") or "").strip()
            tag = el.evaluate("n => n.tagName.toLowerCase()")
            text = (el.inner_text() or "").strip().replace("\n", " ")[:40]
            key = f"{tag}.{cls}" if cls else f"{tag}[{text[:20]}]"
            out.append(Control(key, tag, text, box["width"], box["height"]))
        except PlaywrightError:
            # The node went away mid-measure (re-render). Not a verdict either
            # way — skip it rather than record a value we did not observe.
            continue
    return out


def selftest_detach() -> list[str]:
    """The detach/re-render race, exercised deterministically. Returns failures.

    lexitrail#163 review: the split under-tested exactly one path -- the
    `except PlaywrightError` in `_measure` -- and neither mutation control nor
    `--self-test` nor a prod run reaches it, because by design it only fires
    when a node vanishes mid-measure.

    hc2 suggested a `data:` fixture that removes a node on a short timer. This
    uses a fake page instead, deliberately: a timing fixture has to win a race
    to fail, so it would flake, and a control that flakes gets muted -- which
    would leave this branch untested again, by a slower route. A fake page
    tests the same branch with no clock in it.

    ⚠️ What it does NOT cover: that a REAL detached node raises PlaywrightError
    rather than something else. That is Playwright's contract, not ours.
    """
    failures: list[str] = []

    class _DetachedEl:
        def is_visible(self):
            raise PlaywrightError("Node is detached from document")

    class _DetachingPage:
        def query_selector_all(self, selector):
            return [_DetachedEl()]

    try:
        out = _measure(_DetachingPage())
    except NameError as e:
        failures.append(f"_measure raised NameError on the detach path ({e}) — "
                        "the graceful skip is not reachable")
        return failures
    except Exception as e:  # noqa: BLE001 - any escape is the failure
        failures.append(f"_measure let {type(e).__name__} escape the detach path: {e}")
        return failures
    if out:
        failures.append(f"_measure counted {len(out)} detached control(s); a node "
                        "that vanished mid-measure must be skipped, not recorded")
    return failures

