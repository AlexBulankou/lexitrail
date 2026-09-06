#!/usr/bin/env node
// revamp-2026-09 — mechanical colour/font migration for the SPA's component CSS.
//
// Global.css now declares the token layer. This rewrites the literals the audit
// (docs/design-system.md §4.2) found in ui/src/styles/*.css to the matching var, so the
// remaining stylesheets (Game.css 27 KB, WordCard.css, NavBar.css, Home.css, Completed.css,
// Today.css, StreakBadge.css, SpeakButton.css, MiniWordCard.css, PrivateRoute.css, About.css,
// Policy.css, App.css) join the system without a hand edit per rule.
//
// Run:   node scripts/migrate-tokens.mjs            (from ui/)
//        node scripts/migrate-tokens.mjs --check    (exit 1 if anything would change; CI guard)
//
// Review the diff. Two things it deliberately does NOT do: it does not touch tapTargets.test.js
// or Global.css, and it does not decide LAYOUT (radii are mapped only where the shipped value is
// one of the four system radii).
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const stylesDir = join(here, '..', 'src', 'styles');
const check = process.argv.includes('--check');

// literal (case-insensitive) -> token. Order matters only where one literal is a prefix of another.
const COLOR_MAP = [
  // blues -> accent
  ['#1a73e8', 'var(--accent)'], ['#4285f4', 'var(--accent)'], ['#007bff', 'var(--accent)'],
  ['#2c6cd3', 'var(--accent)'], ['#1557b0', 'var(--accent)'], ['#0056b3', 'var(--accent)'],
  ['#3367d6', 'var(--accent)'],
  // greens -> ok
  ['#2e7d32', 'var(--ok)'], ['#28a745', 'var(--ok)'], ['#1b5e20', 'var(--ok)'], ['#4caf50', 'var(--ok)'],
  ['#34a853', 'var(--ok)'], ['#218838', 'var(--ok)'], ['#e8f5e9', 'var(--ok-soft)'], ['#d4edda', 'var(--ok-soft)'],
  // reds -> bad
  ['#dc3545', 'var(--bad)'], ['#c82333', 'var(--bad)'], ['#d32f2f', 'var(--bad)'], ['#ea4335', 'var(--bad)'],
  ['#ffebee', 'var(--bad-soft)'], ['#f8d7da', 'var(--bad-soft)'],
  // greys -> surfaces / ink
  ['#f0f0f0', 'var(--bg)'], ['#f8f9fa', 'var(--bg)'], ['#fafafa', 'var(--bg)'], ['#f5f5f5', 'var(--surface-2)'],
  ['#f1f3f4', 'var(--surface-2)'], ['#e0e0e0', 'var(--line)'], ['#dadce0', 'var(--line)'], ['#ddd', 'var(--line)'],
  ['#e5e5e5', 'var(--line)'], ['#202124', 'var(--ink)'], ['#333', 'var(--ink)'], ['#333333', 'var(--ink)'],
  ['#3c4043', 'var(--ink)'], ['#5f6368', 'var(--muted)'], ['#555', 'var(--muted)'], ['#666', 'var(--muted)'],
  ['#777', 'var(--muted)'], ['#888', 'var(--muted)'],
  // #fff backgrounds must flip with the colour scheme (dark mode is NEW with the token layer;
  // a literal white chip under token text is 1.17:1 in dark).
  // Property-anchored so a `color:#fff` on a coloured control is left for a human decision.
  [/\b(background(?:-color)?)\s*:\s*#fff(?:fff)?\b/gi, '$1: var(--surface)'],
  // named keywords the audit found in component CSS
  [/\b(background(?:-color)?|color|border-color)\s*:\s*white\b/gi, '$1: var(--surface)'],
  [/\b(background(?:-color)?|color|border-color)\s*:\s*black\b/gi, '$1: var(--ink)'],
  [/\b(background(?:-color)?|color|border-color)\s*:\s*blue\b/gi, '$1: var(--accent)'],
  [/\b(background(?:-color)?|color|border-color)\s*:\s*green\b/gi, '$1: var(--ok)'],
  [/\b(background(?:-color)?|color|border-color)\s*:\s*red\b/gi, '$1: var(--bad)'],
  [/\b(background(?:-color)?|color|border-color)\s*:\s*purple\b/gi, '$1: var(--accent)'],
  [/\b(background(?:-color)?|color|border-color)\s*:\s*darkgray\b/gi, '$1: var(--surface-2)'],
];

const FONT_MAP = [
  [/font-family\s*:\s*[^;]*(Google Sans|Arial|Helvetica|Segoe UI|Roboto)[^;]*;/gi, 'font-family: var(--font-latin);'],
  [/font-family\s*:\s*[^;]*(Songti|SimSun|Noto Serif SC|KaiTi)[^;]*;/gi, 'font-family: var(--font-hanzi);'],
];

const RADIUS_MAP = [
  [/border-radius\s*:\s*4px;/g, 'border-radius: 8px;'],      // nothing in the system is 4px; smallest is 8
  [/border-radius\s*:\s*12px;/g, 'border-radius: var(--r-item);'],
  [/border-radius\s*:\s*16px;/g, 'border-radius: var(--r-card);'],
  [/border-radius\s*:\s*20px;/g, 'border-radius: var(--r-hero);'],
  // 50% is deliberately NOT mapped: it is a circle, a shape constant, not a design radius — and
  // the pre-mount spinner in public/index.html must stay literal-for-literal identical to the
  // React spinner's CSS (premountIndicator.test.js), which tokens can't satisfy before mount.
  [/border-radius\s*:\s*(999px|9999px);/g, 'border-radius: var(--r-pill);'],
];

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// Comments are archaeology in this repo (issue numbers, "was #007bff" notes) and must read the
// same after the migration — so they are masked out before any rewrite and restored verbatim.
const applyOutsideComments = (css, rewrite) => {
  const comments = [];
  const masked = css.replace(/\/\*[\s\S]*?\*\//g, (m) => {
    comments.push(m);
    return `\u0000C${comments.length - 1}\u0000`;
  });
  return rewrite(masked).replace(/\u0000C(\d+)\u0000/g, (_, i) => comments[Number(i)]);
};

const apply = (css) => applyOutsideComments(css, (masked) => {
  let out = masked;
  for (const [from, to] of COLOR_MAP) {
    out = from instanceof RegExp
      ? out.replace(from, to)
      : out.replace(new RegExp(escapeRe(from) + '(?![0-9a-f])', 'gi'), to);
  }
  for (const [re, to] of [...FONT_MAP, ...RADIUS_MAP]) out = out.replace(re, to);
  return out;
});

const SKIP = new Set(['Global.css', 'Wordsets.css', 'OnboardingOverlay.css', 'SessionSize.css']);
let changed = 0;
for (const name of readdirSync(stylesDir)) {
  if (!name.endsWith('.css') || SKIP.has(name)) continue;
  const path = join(stylesDir, name);
  const before = readFileSync(path, 'utf8');
  const after = apply(before);
  if (after === before) continue;
  changed += 1;
  if (check) { console.log(`would change: ${name}`); continue; }
  writeFileSync(path, after);
  console.log(`migrated: ${name}`);
}
if (check && changed) process.exit(1);
console.log(check ? `${changed} file(s) pending` : `${changed} file(s) migrated`);
