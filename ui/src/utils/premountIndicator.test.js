/**
 * lexitrail#266 — pins the PRE-MOUNT loading indicator and the one assumption
 * that makes it safe.
 *
 * Alex's ruling (2026-09-02, relayed by zz1) set the time-to-first-card bar at
 * 5 s — 2278 ms measured on prod passes it — and separately asked for a visual
 * indicator while loading. Of that 2278 ms, ~446 ms is network + bundle
 * download/execute, i.e. BEFORE React exists. No component can render in that
 * window, so the indicator has to be static markup inside `#root` in
 * `public/index.html`.
 *
 * That only works because `src/index.js` calls `createRoot(...).render(...)`,
 * and createRoot REPLACES the container's existing children on first render.
 * If someone switched to `hydrateRoot`, React would try to hydrate the
 * placeholder against the app tree instead of replacing it, and the spinner
 * would either persist behind the app or blow up with a hydration mismatch.
 *
 * 🔴 That is the failure this file exists to catch, and it is invisible in a
 * diff: `hydrateRoot` is a one-word change that looks like a performance
 * improvement. Nothing else in the suite would go red.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import fs from 'fs';
import path from 'path';

const INDEX_HTML = path.join(__dirname, '..', '..', 'public', 'index.html');

// The placeholder markup, read from the file rather than retyped — a retyped
// fixture would keep passing after someone edited the real one.
//
// 🔴 HTML COMMENTS ARE STRIPPED, and that is not tidiness. The first version of
// this file asserted `not.toContain('<img')` against the raw block and failed
// immediately — because the block's own explanatory comment says the spinner is
// CSS-only "rather than an <img>". A substring match cannot tell an <img> tag
// from prose ABOUT <img> tags, so the artifact explaining the rule tripped the
// rule. Left as a note because the same trap catches the next person who adds an
// assertion here: assert on MARKUP, and make sure the thing you read is markup.
const stripComments = (html) => html.replace(/<!--[\s\S]*?-->/g, '');

const readRawRootBlock = () => {
  const html = fs.readFileSync(INDEX_HTML, 'utf8');
  const start = html.indexOf('<div id="root">');
  expect(start).toBeGreaterThan(-1);
  const end = html.indexOf('</body>', start);
  expect(end).toBeGreaterThan(start);
  return html.slice(start, end);
};

const readRootBlock = () => stripComments(readRawRootBlock());

describe('lexitrail#266 pre-mount loading indicator', () => {
  test('index.html ships a placeholder INSIDE #root, not merely somewhere in the file', () => {
    const rootBlock = readRootBlock();
    // Scoped to the #root block on purpose: a whole-file `includes` would also
    // be satisfied by the id appearing in a comment elsewhere in the document.
    expect(rootBlock).toContain('id="lx-premount"');
    expect(rootBlock).toContain('lx-premount-spinner');
  });

  test('the placeholder is announced to assistive tech', () => {
    const rootBlock = readRootBlock();
    expect(rootBlock).toContain('role="status"');
    expect(rootBlock).toContain('aria-label="Loading Lexitrail"');
  });

  test('its styles are INLINE — the CSS bundle has not loaded in this window', () => {
    const rootBlock = readRootBlock();
    expect(rootBlock).toContain('<style>');
    // An <img> would cost a request during the exact window this covers.
    expect(rootBlock).not.toContain('<img');
  });

  test('CONTROL: comment-stripping is what makes the <img> assertion mean anything', () => {
    // Without this control the assertion above could pass for the wrong reason
    // — e.g. if stripComments ever over-matched and returned an empty string,
    // `not.toContain` would pass on nothing at all. So pin BOTH directions:
    // the mention is present in the raw block, and absent after stripping.
    expect(readRawRootBlock()).toContain('<img');   // the prose mention
    expect(readRootBlock()).not.toContain('<img');  // no actual tag
    // ...and stripping must not have eaten the markup we assert on elsewhere.
    expect(readRootBlock()).toContain('id="lx-premount"');
  });

  test('reduced motion keeps the indicator and drops only the spin', () => {
    const rootBlock = readRootBlock();
    expect(rootBlock).toContain('prefers-reduced-motion');
    const idx = rootBlock.indexOf('prefers-reduced-motion');
    // The rule inside the media query must null the ANIMATION, not hide the
    // element — a reduced-motion user must not end up with less feedback.
    expect(rootBlock.slice(idx, idx + 200)).toContain('animation: none');
    expect(rootBlock.slice(idx, idx + 200)).not.toContain('display: none');
  });

  test('createRoot REPLACES pre-existing children (why the placeholder self-clears)', () => {
    const container = document.createElement('div');
    container.innerHTML =
      '<div id="lx-premount"><div class="lx-premount-spinner"></div>Loading Lexitrail…</div>';
    document.body.appendChild(container);
    // Control: the placeholder really is there before we render.
    expect(container.querySelector('#lx-premount')).not.toBeNull();

    const root = createRoot(container);
    act(() => {
      root.render(React.createElement('main', { 'data-testid': 'app' }, 'app mounted'));
    });

    expect(container.querySelector('#lx-premount')).toBeNull();
    expect(container.querySelector('[data-testid="app"]')).not.toBeNull();

    act(() => root.unmount());
    document.body.removeChild(container);
  });

  // hc2's review Q on PR #329: the pre-mount spinner and the in-app one are two
  // separately-maintained CSS blocks (inline <style> here, Game.css there) rather
  // than one shared class. That duplication is FORCED — the pre-mount block exists
  // precisely because the CSS bundle has not loaded, so it cannot reference a class
  // from it. What is not forced is letting them drift apart silently, which is the
  // real risk hc2 named. Pinning the shared constants is cheaper than a build-time
  // codegen step and catches the same drift: an edit to one block that is not
  // mirrored in the other now reds here rather than shipping two spinners that
  // visibly change shape mid-load.
  test('the two spinners keep the SAME shape constants (they cannot share a class)', () => {
    const rootBlock = readRootBlock();
    const gameCss = fs.readFileSync(
      path.join(__dirname, '..', 'styles', 'Game.css'), 'utf8');

    // Control first: if either source stopped containing its spinner rule at all,
    // every assertion below would pass vacuously on two empty strings.
    expect(rootBlock).toContain('.lx-premount-spinner');
    expect(gameCss).toContain('.loading-spinner');

    for (const decl of ['width: 40px', 'height: 40px', 'border-radius: 50%',
                        'border: 4px solid rgba(0, 0, 0, 0.12)']) {
      expect(rootBlock).toContain(decl);
      expect(gameCss).toContain(decl);
    }
    // Same timing/easing, spelled per-block because the keyframes names differ.
    expect(rootBlock).toContain('0.9s linear infinite');
    expect(gameCss).toContain('0.9s linear infinite');
  });

  test('index.js still uses createRoot — hydrateRoot would break the above', () => {
    const src = fs.readFileSync(path.join(__dirname, '..', 'index.js'), 'utf8');
    expect(src).toContain('createRoot');
    expect(src).not.toContain('hydrateRoot');
  });
});
