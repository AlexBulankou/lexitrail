// Source with JS/JSX comments removed.
//
// 🔴 WHY THIS EXISTS. Tests that assert on a component's SOURCE are use/mention-vulnerable: the
// comment explaining why a phrase was removed contains that phrase, so a naive
// `src.includes(...)` fails on the fix itself — and the natural "repair" is to delete the
// explanation. Introduced for lexitrail#191's banned-claim assertions and extracted here for
// #193 rather than copied, because two copies of a stripper drift and the tests that depend on
// them then disagree silently.
//
// ⚠️ Deliberately NOT a parser. It handles `{/* jsx */}`, `/* block */` and `// line`, which is
// what these tests need; it does not understand comment-like text inside string literals. Any
// test using it must carry controls in BOTH directions — that it removes a comment-only phrase
// AND that it keeps real code/JSX — or a stripper that ate the file would make every assertion
// built on it vacuous.
export const stripComments = (src) => src
  .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, ' ')   // {/* jsx comment */}
  .replace(/\/\*[\s\S]*?\*\//g, ' ')             // /* block */
  .replace(/^\s*\/\/.*$/gm, ' ');                // // line

export default stripComments;
