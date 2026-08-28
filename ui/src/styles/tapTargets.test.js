/**
 * lexitrail#52 bug 4 (tappability half) — the 44px touch-target floor.
 *
 * WHAT THIS TEST CAN AND CANNOT SAY, stated up front because the distinction is
 * the whole reason bug 4's tappability half shipped unnoticed:
 *
 *   CAN:    the CSS *declares* a >=44px minimum, and no control re-introduces a
 *           smaller fixed size.
 *   CANNOT: that the *rendered* box is >=44px. A parent with a fixed height, or
 *           an `align-items: center` on a short flex row, can still constrain a
 *           child below its declared min-height.
 *
 * PR #58 was titled "larger tap target" and shipped a 2.4rem (38.4px) control.
 * A declaration-level test would not have caught that either — but it would have
 * caught it the moment someone wrote the number down, which is what this does.
 * Render-level proof is lexitrail#52 item 3 (the E2E harness), and this file is
 * deliberately NOT named as satisfying it.
 */
const fs = require('fs');
const path = require('path');

const STYLES = __dirname;
const read = (f) => fs.readFileSync(path.join(STYLES, f), 'utf8');

const FLOOR_PX = 44;

/** Controls that must carry the shared floor. Enumerated on purpose: a future
 *  control added without being listed here is invisible to this test, and that
 *  is a known gap rather than a silent one. */
const FLOOR_SELECTORS = [
  '.speak-button',
  '.exclude-button',
  '.dropdown-trigger',
  '.wordsets-retry',
  '.game-settings-button',
  // issue-109 (RD-6): `.mark-all-memorized-button` REMOVED from this list
  // because the control itself was retired -- the blind "✔️ to all" shortcut
  // and both functions behind it are deleted, and its rule is gone from
  // Game.css and from the shared floor above.
  //
  // Removing an entry from a detector's list is normally the shape that
  // silently blinds it, so the check is stated rather than assumed: the
  // selector must appear NOWHERE in ui/src, which the assertion below pins.
  // If it ever comes back, it comes back with a floor.
  // issue-52: these three were the gap made concrete. They were absent from
  // this list, so this file stayed green while all three shipped under the
  // floor on live prod — found by the E2E harness measuring the rendered box,
  // not by anything here. Adding them closes the declaration half; the render
  // half is `e2e/tap_targets.py`'s and always will be.
  '.try-button',
  '.google-signin-compact',
  '.wordset-button',
  // issue-120: found by the E2E harness on the guest journey.
  // `.nav-wordsets-link` is the "Word Sets" nav link (98.9x32.0 on live
  // prod); `.dropdown-trigger` (already above) also gained a min-width --
  // its declared min-height alone wasn't enough, the mobile-media-query
  // padding left it 35.2px wide.
  '.nav-wordsets-link',
  // issue-107: the Today home's Start button, listed as it shipped rather than
  // after prod measured it short.
  // issue-85: the onboarding overlay's dismiss button. Found on live prod at
  // 43px in all three viewports, by the E2E harness driven past the landing
  // page — the `guest` route never left the homepage, so this control was
  // absent from every population the matrix had ever sampled.
  '.onboarding-button',
  '.today-start',
  // issue-196: "Sign in with Google" — 300x36 desktop, 270x36 mobile on live prod. THIRD time
  // this enumeration has been the gap (after #52's three and #120's nav link), and this one is
  // the secondary CTA at the acquisition moment. `.google-signin-compact` was already listed;
  // `.google-signin-button` is a DIFFERENT control and a listed near-namesake is exactly what
  // makes an absence hard to see.
  '.google-signin-button',
];

describe('shared touch-target floor', () => {
  const global = read('Global.css');

  test('the floor is declared once, as a custom property, at >= 44px', () => {
    const m = global.match(/--min-tap-target:\s*(\d+(?:\.\d+)?)px/);
    expect(m).not.toBeNull();
    expect(parseFloat(m[1])).toBeGreaterThanOrEqual(FLOOR_PX);
  });

  test.each(FLOOR_SELECTORS)('%s references the shared floor', (sel) => {
    // The selector must appear in a rule block that applies the custom property,
    // not merely somewhere in the file.
    const escaped = sel.replace('.', '\\.');
    const re = new RegExp(
      `${escaped}[^{]*\\{[^}]*var\\(--min-tap-target\\)`, 's'
    );
    expect(global).toMatch(re);
  });

  test('the pronunciation control is no longer 2.4rem (38.4px)', () => {
    // The specific regression bug 4 left behind. 2.4rem is 38.4px at a 16px
    // root, which is what the audit measured as "38x38".
    const speak = read('SpeakButton.css');
    const md = speak.match(/\.speak-button-md\s*\{([^}]*)\}/s);
    expect(md).not.toBeNull();
    expect(md[1]).not.toMatch(/(width|height):\s*2\.4rem/);
    expect(md[1]).toMatch(/var\(--min-tap-target\)/);
  });

  test('the floor is single-sourced — no component CSS re-declares it', () => {
    /* hc2@ on #73: `.exclude-button` (WordCard.css) and `.wordsets-retry`
     * (Wordsets.css) each carried their own `min-height: 44px`, pre-dating this
     * PR, alongside the new shared rule. Both were 44px so nothing rendered
     * wrong — and every other assertion in this file passed, because they all
     * check the VALUE and none checked the SOURCING.
     *
     * That gap is the bug this PR argues against, in the PR's own diff: the
     * literals do not reference `--min-tap-target`, and component CSS loads
     * AFTER Global.css at equal specificity, so it wins the tie. Raise the
     * floor and those two silently hold the old value while their siblings
     * follow.
     *
     * A control that genuinely needs a LARGER target should use the
     * `max(Xrem, var(--min-tap-target))` form `.speak-button-lg` uses, so it
     * still tracks the floor upward.
     */
    const files = fs.readdirSync(STYLES)
      .filter((f) => f.endsWith('.css') && f !== 'Global.css');
    const offenders = [];
    for (const f of files) {
      const css = read(f);
      for (const sel of FLOOR_SELECTORS) {
        const escaped = sel.replace('.', '\\.');
        for (const r of css.matchAll(
          new RegExp(`${escaped}[a-zA-Z0-9_-]*\\s*\\{([^}]*)\\}`, 'gs')
        )) {
          // min-height is shared for all these; min-width is shared for
          // .speak-button and .dropdown-trigger only, so a min-width literal
          // elsewhere (e.g. .exclude-button's 68px label width) is a
          // different job and allowed.
          const props = (sel === '.speak-button' || sel === '.dropdown-trigger')
            ? /\bmin-(height|width):\s*[\d.]+(px|rem)/g
            : /\bmin-height:\s*[\d.]+(px|rem)/g;
          for (const d of r[1].matchAll(props)) {
            offenders.push(`${f} ${sel}: ${d[0].trim()}`);
          }
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  test('no control declares a fixed size below the floor', () => {
    // Regression guard in the direction that actually happened: someone writes
    // a literal px/rem size on a control and it lands under 44.
    const files = fs.readdirSync(STYLES).filter((f) => f.endsWith('.css'));
    const offenders = [];
    for (const f of files) {
      const css = read(f);
      for (const sel of FLOOR_SELECTORS) {
        const escaped = sel.replace('.', '\\.');
        const rules = css.matchAll(
          new RegExp(`${escaped}[a-zA-Z0-9_-]*\\s*\\{([^}]*)\\}`, 'gs')
        );
        for (const r of rules) {
          const decls = r[1];
          for (const d of decls.matchAll(/\b(?:width|height):\s*([\d.]+)(px|rem)\b/g)) {
            const px = d[2] === 'rem' ? parseFloat(d[1]) * 16 : parseFloat(d[1]);
            if (px < FLOOR_PX) offenders.push(`${f} ${sel}: ${d[0]} (${px}px)`);
          }
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe('retired controls stay retired (issue-109)', () => {
  test('.mark-all-memorized-button exists nowhere in the tree', () => {
    // The blind bulk-tick wrote a full recall event per word -- same call,
    // same fields, same streak credit as a genuine answer -- so its history is
    // indistinguishable from earned recall downstream. It was removed from
    // this file's floor list, and this is what stops that removal from being a
    // blinded detector: the control is gone, not merely unlisted.
    const root = path.join(STYLES, '..');
    const offenders = [];
    const walk = (dir) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === 'node_modules') continue;
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) { walk(full); continue; }
        if (!/\.(js|css)$/.test(entry.name)) continue;
        if (full === __filename) continue;   // this file names it on purpose
        const text = fs.readFileSync(full, 'utf8');
        // Ignore the explanatory comments the removal left behind; what must
        // not exist is a live selector or handler.
        const live = text
          .split('\n')
          .filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l))
          .join('\n');
        if (/mark-all-memorized|markAllAsMemorized|handleMemorizedMultiple/.test(live)) {
          offenders.push(path.relative(root, full));
        }
      }
    };
    walk(root);
    expect(offenders).toEqual([]);
  });
});

// ── lexitrail#196: the landing example must read as separate tokens ──────────────────────────
//
// The "Character Breakdown" card rendered `记忆jì yìmemoryThink of 记 (jì)...` — three spans with
// NO styles at all, collapsing into each other and into the prose after them. A declaration-level
// pin, with the same limits as everything else in this file: it can say the CSS declares
// separation, not that the rendered box is separated.
describe('lexitrail#196 — the Character Breakdown example is not a run-on string', () => {
  const home = read('Home.css');

  test('the example-word spans are styled at all — they were not', () => {
    expect(home).toMatch(/\.example-word\s*\{/);
    expect(home).toMatch(/\.example-word\s+\.chinese-char\s*\{/);
  });

  test('something separates pinyin from the meaning that follows it', () => {
    // Either generated content or a margin: the assertion is on the SEPARATION, not on the
    // interpunct, so a later redesign that spaces them differently does not red for style.
    const rule = home.slice(home.indexOf('.example-word .pinyin'));
    expect(rule.slice(0, 400)).toMatch(/content:|margin|padding|display:\s*block/);
  });

  test('CONTROL: Home.css was read and is the real file', () => {
    // Without this, every assertion above is satisfied by an empty string.
    expect(home).toMatch(/\.chinese-word\s*\{/);
    expect(home.length).toBeGreaterThan(1000);
  });
});
