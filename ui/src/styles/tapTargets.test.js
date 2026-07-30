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
  '.mark-all-memorized-button',
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
