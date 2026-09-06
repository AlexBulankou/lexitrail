import React from 'react';

// Define tone colors
// revamp-2026-09: tone colours are TOKENS, not literals. `--t1..--t4` live in Global.css :root
// (and in PAGE_STYLE for the static pages, so an indexed page and the practice screen colour the
// same vowel the same way). The shipped literals (#FF4500 / #FFA500 / #32CD32 / #800080) failed
// contrast on white for tones 2 and 3 and had no dark-mode counterpart; the tokens are tuned per
// palette and flip with `prefers-color-scheme`. Neutral tone inherits the surrounding text colour.
const toneColors = {
    1: 'var(--t1)', // --t1 for first tone
    2: 'var(--t2)', // --t2 for second tone
    3: 'var(--t3)', // --t3 for third tone
    4: 'var(--t4)', // --t4 for fourth tone
    0: 'inherit', // inherit for neutral tone
};

// Function to determine the tone based on accented characters. Exported so the static-page
// generators (hskPages.pinyinHtml) use the SAME table — one source for which vowel is which tone.
export const getTone = (char) => {
    if ('āēīōūǖĀĒĪŌŪǕ'.includes(char)) return 1;
    if ('áéíóúǘÁÉÍÓÚǗ'.includes(char)) return 2;
    if ('ǎěǐǒǔǚǍĚǏǑǓǙ'.includes(char)) return 3;
    if ('àèìòùǜÀÈÌÒÙǛ'.includes(char)) return 4;
    return 0; // Neutral tone if no tone mark is found
};

// Function to detect syllables based on vowels in pinyin
const splitSyllables = (text) => {
    // Regex to match pinyin syllables
    const syllableRegex = /([bpmfdtnlgkhjqxrzcsyw]?u?[aeiouüāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]*|[a-z]+)(?=\b|[^a-z])/gi;
    return text.match(syllableRegex) || []; // Returns an array of syllables
};

// 📌 DEAD (see lexitrail#190 note below) — kept as the design for mid-token wrapping.
// Function to render pinyin with colored tones and syllable separation
const renderPinyinWithSyllables = (text) => {
    const syllables = splitSyllables(text); // Split text into syllables

    return syllables.map((syllable, index) => {
        const characters = Array.from(syllable); // Convert syllable to array of characters

        // Render each syllable with colored tones
        const syllableContent = characters.map((char, charIndex) => {
            const tone = getTone(char);
            const color = toneColors[tone];

            return (
                <span key={`${index}-${charIndex}`} style={{ color: tone > 0 ? color : 'inherit' }}>
                    {char}
                </span>
            );
        });

        // Add a hyphen `-` between syllables, except after the last one
        return (
            <React.Fragment key={index}>
                {syllableContent}
                {index < syllables.length - 1 && <span>-</span>}
            </React.Fragment>
        );
    });
};


const renderPinyin = (text) => {
    const characters = Array.from(text); // Convert text to an array of characters

    return characters.map((char, index) => {
        const tone = getTone(char);
        const color = toneColors[tone];

        // Return each character with a span, only applying color to vowels with tones
        return (
            <span key={index} className={tone > 0 ? `t${tone}` : undefined} style={{ fontWeight: tone > 0 ? 'bold' : 'inherit', color: tone > 0 ? color : 'inherit' }}>
                {char}
            </span>
        );
    });
};

// lexitrail#190 — WHY THIS WRAPPER EXISTS, and why the fix is here rather than on the button.
//
// THE DEFECT. `renderPinyin` emits ONE <span> PER CHARACTER so each vowel can carry its tone
// colour. Sibling inline elements are break opportunities, so the browser may wrap between ANY
// two characters of a pinyin token: measured on /game/<N>/TEST at 390x844, `xiǎojiě` rendered as
// `xiǎoji` / `ě`, and `shāngdiàn`, `míngtiān`, `gōngzuò`, `zěnme` all broke the same way.
//
// 🔴 THE ISSUE PROPOSED A MIN-WIDTH ON THE BUTTON. That treats the symptom: it makes the
// container wide enough that today's longest pinyin happens to fit, and the next longer one
// breaks again -- at every OTHER call site too (WordCard's main pinyin, MiniWordCard, Completed),
// none of which the issue mentions. The per-character break permission is a property of THIS
// component, so it is fixed once here and every caller inherits it.
//
// In a tone-teaching app a syllable split across two lines is not a layout nit: the tone mark and
// the vowel it belongs to end up on different rows.
//
// ⚠️ WHAT THIS DOES NOT DO: it does not decide how the button SIZES. With `nowrap` a token too
// wide for its container overflows rather than breaking, so the 4-up option grid still needs to
// let its buttons grow -- that is the layout half of #190 and it is deliberately separate,
// because a break-permission bug and a grid-sizing bug have different fixes and different tests.
//
// 📌 `renderPinyinWithSyllables` above (with `splitSyllables`) is DEAD -- defined, never exported,
// never called, verified by grep across ui/src. It is the syllable-aware renderer that would have
// made breaking-BETWEEN-syllables possible while keeping each intact. Left in place rather than
// deleted: if the layout half ever needs mid-token wrapping, that is where it comes from, and
// deleting it would erase the design that solves the problem this comment describes.
const PinyinText = ({ text }) => {
    return <span className="pinyin-text" style={{ whiteSpace: 'nowrap' }}>{renderPinyin(text)}</span>;
};

export default PinyinText;
