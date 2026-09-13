// lexitrail: the per-word social/search card for the "<gloss> in Chinese" pages.
//
// 🔴 WHY THIS EXISTS. Every gloss page shipped `og:image` pointing at ONE site-wide PNG
// (`/images/og/generated/og-landscape.png`), so all five pages — and every share of them — looked
// identical, and a search engine had no per-page image to thumbnail. Measured on the SERP for
// "reputation in chinese": our result is text-only at position ~10.7, sitting under two YouTube
// results that stand out for exactly one reason — they have a picture.
//
// The page itself is not the problem. It is genuinely handsome: a 300px serif hanzi, tone-coloured
// pinyin, an HSK chip. ALL OF THAT IS HTML TEXT, which is why none of it reaches the result. This
// file renders that same object as an image so the thing a person sees BEFORE clicking is the
// thing that makes the page worth clicking.
//
// DESIGN NOTES, because they are decisions and not taste:
//   - The hanzi dominates. The card is read at ~200px wide in a mobile result; at that size the
//     glyph is the only element that survives, so it gets the scale and everything else defers.
//   - Centred, not left-weighted. Gloss words run 1-4 characters; a left-aligned hero re-balances
//     the whole composition per word, and a card that only looks composed for two-character words
//     is not a template.
//   - One accent, used once. The coral is the HSK chip and nothing else, so it reads as a focal
//     point rather than decoration.
//   - Tone colour is the product's signature and it teaches at a glance — the one element that
//     says "this will help you" without a word of marketing. It is the same mapping the practice
//     screen uses (`pinyinHtml`), not a second table that can drift.
//   - Warm near-black, not neutral. #141310 against a SERP of white cards is the cheapest
//     distinctiveness available, and it is already the site's dark ground.
//
// FONT: the stack names "Noto Serif CJK SC" explicitly. The site's CSS asks for "Noto Serif SC",
// which does NOT resolve on the build box (`fc-match` falls through to NotoSans) — a card that
// silently renders the hero glyph in a sans is the whole point lost, so the generator names the
// family that actually exists and keeps the site's names after it.

/** Dark-mode tokens from hskPages' PAGE_TOKENS, inlined: the card is rendered standalone by a
 * headless browser with no stylesheet, and it is ALWAYS dark regardless of the renderer's
 * prefers-color-scheme — a card that changed with the build machine's theme would be a defect. */
export const CARD_TOKENS = {
  bg: '#141310', ink: '#f7f2e8', muted: '#a79e8e', line: '#332f27',
  accent: '#e6796a', accentSoft: '#2b1d19',
  t1: '#ff8a6f', t2: '#f0b45a', t3: '#7fd08a', t4: '#c39cf0',
};

export const CARD_W = 1200;
export const CARD_H = 630;

const escCard = (s) => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

/** Hero type scale, stepped by glyph count so a 1-char word is not dwarfed and a 4-char word
 * does not collide with the frame. Measured against the 1200px canvas minus 2x88px gutters. */
// 🔴 These numbers come from LOOKING at the render, not from arithmetic. The first pass used
// 340/300/232/186 and the stack came out taller than the 630px canvas, so `align-items:center`
// pushed the overflow out BOTH ends: the kicker was clipped off the top and the HSK chip off the
// bottom. Every unit test still passed — the card was well-formed HTML the whole time. The budget
// is ~505px of stack inside 630, leaving ~60px of air above and below the frame inset.
export const hanziSize = (word) => {
  const n = Array.from(String(word ?? '')).length;
  if (n <= 1) return 290;
  if (n === 2) return 250;
  if (n === 3) return 196;
  return 158;
};

/**
 * The card's HTML. Pure: same inputs -> same bytes, so the generator's --check can byte-compare.
 *
 * The English gloss appears ONCE, in the kicker. An earlier pass also set it as a line under the
 * pinyin and the card read as a stutter — "REPUTATION IN CHINESE" above, "reputation" below. Four
 * elements and a wordmark is the whole card; anything else competes with the glyph.
 *
 * @param {{gloss:string, word:string, pinyin:string, hsk:number|string}} card
 * @param {(text:string)=>string} pinyinHtml  the SHARED tone renderer (injected, never re-implemented)
 */
export const renderGlossCard = (card, pinyinHtml) => {
  const { gloss, word, pinyin, hsk } = card;
  const T = CARD_TOKENS;
  const kicker = `${String(gloss ?? '').toUpperCase()} IN CHINESE`;
  const chip = hsk ? `<span class="chip">HSK ${escCard(hsk)}</span>` : '';
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><style>
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:${CARD_W}px;height:${CARD_H}px}
  body{
    background:${T.bg};
    /* Light falling on paper: the glow sits slightly ABOVE centre so the hero reads optically
       centred once the pinyin and gloss hang below it. */
    background-image:radial-gradient(ellipse 70% 62% at 50% 40%, #2b2521 0%, ${T.bg} 68%);
    color:${T.ink};
    font-family:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    display:flex;align-items:center;justify-content:center;
  }
  .frame{
    position:absolute;inset:26px;border:1px solid ${T.line};border-radius:22px;
    pointer-events:none;
  }
  .stack{display:flex;flex-direction:column;align-items:center;text-align:center;padding:0 88px}
  .kicker{
    font-size:24px;letter-spacing:.3em;text-transform:uppercase;color:${T.muted};
    font-weight:600;margin-bottom:28px;
  }
  .hanzi{
    font-family:"Noto Serif CJK SC","Noto Serif SC","Songti SC","Source Han Serif SC","STSong",serif;
    font-size:${hanziSize(word)}px;line-height:1.06;letter-spacing:.05em;
    /* The glyph carries a faint warm bloom so it sits IN the light rather than on top of it. */
    text-shadow:0 0 60px rgba(230,121,106,.14);
  }
  .pinyin{
    font-size:62px;font-weight:700;margin-top:20px;letter-spacing:.01em;
  }
  .t1{color:${T.t1}}.t2{color:${T.t2}}.t3{color:${T.t3}}.t4{color:${T.t4}}
  .chip{
    display:inline-block;margin-top:24px;background:${T.accentSoft};color:${T.accent};
    border-radius:999px;padding:8px 21px;font-size:22px;font-weight:700;letter-spacing:.09em;
  }
  .mark{
    /* Tucked into the corner, BELOW the chip's baseline. At bottom:62px it sat level with the
       HSK chip and the two small elements read as a competing pair across the bottom instead of
       a mark and a badge. Hierarchy, not symmetry. */
    position:absolute;left:64px;bottom:44px;display:flex;align-items:center;gap:10px;
    font-size:23px;color:${T.muted};font-weight:600;letter-spacing:.02em;
  }
  .dot{width:12px;height:12px;border-radius:4px;background:${T.accent};display:inline-block}
</style></head><body>
<div class="frame"></div>
<div class="stack">
  <div class="kicker">${escCard(kicker)}</div>
  <div class="hanzi" lang="zh-Hans">${escCard(word)}</div>
  <div class="pinyin">${pinyinHtml(pinyin)}</div>
  ${chip}
</div>
<div class="mark"><span class="dot"></span>LexiTrail</div>
</body></html>`;
};

/** Where the card is served from. One place, imported by both the generator and the page meta,
 * so the file a page POINTS at and the file the generator WRITES cannot drift apart. */
export const glossCardPath = (slug) => `/images/og/words/${slug}.png`;
export const glossCardUrl = (slug, origin) => `${origin}${glossCardPath(slug)}`;
