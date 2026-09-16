// uibug 2026-09-16 — TEST-mode option buttons clipped long pinyin at BOTH ends.
//
// MEASURED on lexitrail.com (desktop 1440x900; the same ~67px squares exist at
// 390x844): a `.test-buttons button` is ~67px wide — 160px `.word-card`, minus
// border+padding, times the 95% `.test-buttons` grid, split into two 1fr
// columns. The label is PinyinText, a `white-space: nowrap` span (the #190 fix,
// which is load-bearing: per-character spans are break opportunities, and a
// tone mark must never be split from its vowel). The button is
// `overflow: hidden` and flex-centered at `font-size: 1.5rem`, so a token wider
// than the button cannot wrap, cannot shrink and cannot scroll — it loses BOTH
// ends, with no ellipsis (`text-overflow` is inert on a flex container):
// 'dǎdiànhuà' (scrollWidth 90 vs clientWidth 67) rendered 'diànhu',
// 'zěnmeyàng' (95 vs 67) rendered 'nmeyà'. 19 of the dealt options clipped in
// one sweep — the learner literally could not read the answers.
//
// ⚠️ Those scrollWidths UNDERSTATE the overflow: on a flex-centered box
// scrollWidth reports only the END-side half (the start side is unreachable),
// so 'zěnmeyàng' at 95 scrollWidth is really a 124px text run in a 67px box
// (95 = 67 + 57/2 ✓ — verified in-page against the span's own rect).
//
// THE FIX IS SIZING, NOT LAYOUT: the length of the option decides a font-size
// step (classes in WordCard.css) so the longest real deals fit the same square
// with margin to spare, while short options keep the original 1.5rem exactly.
// Steps are calibrated against the TRUE text-run width of the widest measured
// option in each length band at 24px (1.5rem) — text width scales linearly
// with font-size (verified across 24→11.2px) — targeting the 63px client box a
// revealed `.quiz-option-correct` button keeps after its 2px border:
//
//   len ≤ 4   —             (1.5rem)  widest real 4-char ≈ 55px — already fits
//   len 5–6   — md (1rem)      'shénme' 85px → ~57px
//   len 7–8   — sm (0.85rem)   'xuéshēng' 104px → ~59px
//   len 9–10  — xs (0.7rem)    'zěnmeyàng' 124px → ~58px
//   len ≥ 11  — xxs (0.6rem)   headroom for longer wordsets
//
// Length counts CODE POINTS (Array.from), so a precomposed tone-marked vowel
// ('ǎ', 'à'…) counts as one character, matching what the reader sees.

export const quizOptionSizeClass = (pinyin) => {
  if (!pinyin) return '';
  const len = Array.from(String(pinyin).trim()).length;
  if (len <= 4) return '';
  if (len <= 6) return 'test-option-md';
  if (len <= 8) return 'test-option-sm';
  if (len <= 10) return 'test-option-xs';
  return 'test-option-xxs';
};
