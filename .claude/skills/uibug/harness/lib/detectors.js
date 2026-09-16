'use strict';
/**
 * Geometric + logic detectors. These run IN THE PAGE against the rendered boxes.
 *
 * Everything here is deliberately a MEASUREMENT, never an inference from source.
 * This repo already learned that lesson the expensive way: ui/src/styles/
 * tapTargets.test.js asserted the CSS *declared* a 44px floor and stayed green
 * while 23 of 33 live controls *rendered* under it (e2e/tap_targets.py, and its
 * README says so in as many words). So every finding below carries the numbers
 * it was derived from, and a reviewer can re-run the arithmetic.
 *
 * Exported as a single function string-evaluated by page.evaluate, so it must be
 * self-contained -- no requires, no closure over Node scope.
 */

/** Runs inside the browser. Returns { elements, findings }. */
function collect() {
  const TAP_FLOOR = 44;          // WCAG 2.5.5 / Apple HIG; the repo's stated floor
  const CONTRAST_AA = 4.5;       // WCAG AA, normal text
  const CONTRAST_AA_LARGE = 3.0; // >=24px, or >=18.66px bold
  const EPS = 1;                 // sub-pixel slop; below this is rounding, not a bug

  const vw = window.innerWidth;
  const vh = window.innerHeight;

  const isInteractive = (el) => {
    const t = el.tagName.toLowerCase();
    if (['button', 'a', 'input', 'select', 'textarea'].includes(t)) return true;
    if (el.getAttribute('role') && /button|link|checkbox|tab|menuitem/.test(el.getAttribute('role'))) return true;
    if (el.hasAttribute('onclick')) return true;
    return false;
  };

  const visible = (el, r, cs) => {
    if (r.width <= 0 || r.height <= 0) return false;
    if (cs.visibility === 'hidden' || cs.display === 'none') return false;
    if (parseFloat(cs.opacity) === 0) return false;
    return true;
  };

  // --- color math for the contrast detector -------------------------------
  const parseRGB = (s) => {
    const m = String(s).match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map((x) => parseFloat(x));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const lum = (c) => {
    const f = (v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const ratio = (a, b) => {
    const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
  };
  // Walk up for the first non-transparent background -- the element's own is
  // usually rgba(0,0,0,0), and comparing text against transparent is meaningless.
  const effectiveBg = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const c = parseRGB(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0.1) return c;
      n = n.parentElement;
    }
    return { r: 255, g: 255, b: 255, a: 1 };
  };

  const els = [];
  const findings = [];
  const all = Array.from(document.querySelectorAll('body *'));

  for (const el of all) {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (!visible(el, r, cs)) continue;

    const rec = {
      tag: el.tagName.toLowerCase(),
      id: el.id || null,
      cls: (el.className && typeof el.className === 'string' ? el.className : '').trim(),
      text: (el.textContent || '').trim().slice(0, 80),
      box: { x: +r.x.toFixed(1), y: +r.y.toFixed(1), w: +r.width.toFixed(1), h: +r.height.toFixed(1),
             top: +r.top.toFixed(1), bottom: +r.bottom.toFixed(1), left: +r.left.toFixed(1), right: +r.right.toFixed(1) },
      interactive: isInteractive(el),
      scroll: { sw: el.scrollWidth, cw: el.clientWidth, sh: el.scrollHeight, ch: el.clientHeight },
      style: {
        position: cs.position, overflow: cs.overflow, overflowX: cs.overflowX, overflowY: cs.overflowY,
        zIndex: cs.zIndex, fontSize: cs.fontSize, fontWeight: cs.fontWeight,
        color: cs.color, background: cs.backgroundColor, display: cs.display,
      },
    };
    els.push(rec);

    const sel = rec.cls ? `${rec.tag}.${rec.cls.split(/\s+/).join('.')}` : rec.tag;

    // --- TAP TARGET: rendered box under the floor ------------------------
    if (rec.interactive && (r.width < TAP_FLOOR - EPS || r.height < TAP_FLOOR - EPS)) {
      findings.push({
        kind: 'tap-target', selector: sel, text: rec.text,
        measured: { w: rec.box.w, h: rec.box.h, floor: TAP_FLOOR },
        detail: `interactive control renders ${rec.box.w}x${rec.box.h}, under the ${TAP_FLOOR}px floor`,
      });
    }

    // --- VIEWPORT OVERFLOW: content pushed outside the viewport ----------
    // Horizontal only. Vertical overflow is normal page scroll; horizontal is a
    // layout break on every site that is not deliberately a horizontal scroller.
    if (r.right > vw + EPS || r.left < -EPS) {
      findings.push({
        kind: 'viewport-overflow', selector: sel, text: rec.text,
        measured: { left: rec.box.left, right: rec.box.right, viewportWidth: vw },
        detail: `box spans ${rec.box.left}..${rec.box.right} outside viewport width ${vw}`,
      });
    }

    // --- CLIPPING: an overflow:hidden box whose content does not fit -----
    const hidesX = /hidden|clip/.test(cs.overflowX);
    const hidesY = /hidden|clip/.test(cs.overflowY);
    if (hidesX && el.scrollWidth > el.clientWidth + EPS && el.clientWidth > 0) {
      findings.push({
        kind: 'clipped', selector: sel, text: rec.text,
        measured: { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth, axis: 'x' },
        detail: `overflow-x:${cs.overflowX} clips ${el.scrollWidth - el.clientWidth}px of content`,
      });
    }
    if (hidesY && el.scrollHeight > el.clientHeight + EPS && el.clientHeight > 0) {
      findings.push({
        kind: 'clipped', selector: sel, text: rec.text,
        measured: { scrollHeight: el.scrollHeight, clientHeight: el.clientHeight, axis: 'y' },
        detail: `overflow-y:${cs.overflowY} clips ${el.scrollHeight - el.clientHeight}px of content`,
      });
    }

    // --- DEAD CONTROL: looks clickable, goes nowhere ---------------------
    if (rec.tag === 'a') {
      const href = el.getAttribute('href');
      if (href === null || href === '' || href === '#') {
        findings.push({
          kind: 'dead-control', selector: sel, text: rec.text,
          measured: { href },
          detail: `anchor with href="${href}" -- renders as a link, navigates nowhere`,
        });
      }
    }
    if (el.hasAttribute('disabled') && rec.interactive && parseFloat(cs.opacity) === 1) {
      findings.push({
        kind: 'dead-control', selector: sel, text: rec.text, measured: { disabled: true },
        detail: 'disabled control renders at full opacity -- no visual signal it is inert',
      });
    }

    // --- CONTRAST: text below WCAG AA ------------------------------------
    const ownText = Array.from(el.childNodes)
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent.trim())
      .join('')
      .trim();
    if (ownText.length > 0) {
      const fg = parseRGB(cs.color);
      if (fg && fg.a > 0.1) {
        const bg = effectiveBg(el);
        const cr = ratio(fg, bg);
        const px = parseFloat(cs.fontSize);
        const bold = parseInt(cs.fontWeight, 10) >= 700;
        const floor = px >= 24 || (bold && px >= 18.66) ? CONTRAST_AA_LARGE : CONTRAST_AA;
        if (cr < floor) {
          findings.push({
            kind: 'contrast', selector: sel, text: ownText.slice(0, 60),
            measured: { ratio: +cr.toFixed(2), floor, fontSize: px, color: cs.color, background: `rgb(${bg.r},${bg.g},${bg.b})` },
            detail: `text contrast ${cr.toFixed(2)}:1 is under WCAG AA ${floor}:1`,
          });
        }
      }
    }
  }

  // --- OVERLAP: two interactive boxes intersecting ------------------------
  // Only interactive-vs-interactive, and only when NEITHER contains the other.
  // A parent overlapping its child is nesting, not a bug, and reporting it
  // would bury the real finds under thousands of rows.
  const inter = els.filter((e) => e.interactive);
  const contains = (a, b) =>
    a.box.left <= b.box.left + EPS && a.box.right >= b.box.right - EPS &&
    a.box.top <= b.box.top + EPS && a.box.bottom >= b.box.bottom - EPS;

  for (let i = 0; i < inter.length; i++) {
    for (let j = i + 1; j < inter.length; j++) {
      const a = inter[i], b = inter[j];
      if (contains(a, b) || contains(b, a)) continue;
      const ox = Math.min(a.box.right, b.box.right) - Math.max(a.box.left, b.box.left);
      const oy = Math.min(a.box.bottom, b.box.bottom) - Math.max(a.box.top, b.box.top);
      if (ox > EPS && oy > EPS) {
        findings.push({
          kind: 'overlap',
          selector: a.cls ? `${a.tag}.${a.cls.split(/\s+/).join('.')}` : a.tag,
          selectorB: b.cls ? `${b.tag}.${b.cls.split(/\s+/).join('.')}` : b.tag,
          text: `${a.text} | ${b.text}`,
          measured: { overlapX: +ox.toFixed(1), overlapY: +oy.toFixed(1), a: a.box, b: b.box },
          detail: `two interactive controls overlap by ${ox.toFixed(1)}x${oy.toFixed(1)}px -- one is partly untappable`,
        });
      }
    }
  }

  // --- PAGE-LEVEL horizontal scroll ---------------------------------------
  const de = document.documentElement;
  if (de.scrollWidth > vw + EPS) {
    findings.push({
      kind: 'page-h-scroll', selector: 'html',
      measured: { scrollWidth: de.scrollWidth, viewportWidth: vw },
      detail: `page scrolls horizontally by ${de.scrollWidth - vw}px`,
    });
  }

  return { viewport: { w: vw, h: vh }, url: location.href, elements: els, findings };
}

module.exports = { collect };
