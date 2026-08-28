// lexitrail#191 — no signed-out surface may advertise a feature that does not ship.
//
// Three claims were live on 2026-08-27, all at the acquisition moment:
//   PrivateRoute login card  "Create custom word sets"      no create UI, wordsets.py is GET-only
//   Home "Smart Word Sets"   "Create and organize ..."      the SAME nonexistent feature
//   Home "Cultural Context"  "example sentences and ..."    #118 removed the sentences view
//
// The issue named the first and third. The second is the one that makes this a TEST rather than
// two edits: fixing one surface of a claim while a sibling keeps making it leaves the claim true
// of the site and the issue closed.
//
// 🔴 THIS ASSERTS RENDERED TEXT, NOT SOURCE. The fix comments in those files QUOTE the banned
// phrases -- a naive `src.includes("Create custom word sets")` would fail on the fix itself, and
// the natural "repair" is to delete the explanation that says why the copy changed. Comments are
// stripped first, and the stripper is controlled in both directions below.
import fs from 'fs';
import path from 'path';

const COMPONENTS = path.resolve(__dirname, '..', 'components');
const read = (f) => fs.readFileSync(path.join(COMPONENTS, f), 'utf8');

// #193: extracted to ./stripComments so WordCard's test uses the SAME stripper. Two copies would
// drift and the tests depending on them would then disagree silently.
import { stripComments } from './stripComments';

// Claims with no shipped implementation. Each entry names WHY, because a banned-phrase list with
// no reasons rots into a list nobody dares change.
const UNSHIPPED = [
  ['Create custom word sets', 'no create-wordset UI; wordsets.py exposes GET only'],
  ['Create and organize', 'same nonexistent create feature, landing-page wording'],
  ['example sentences and usage notes', '#118 removed the sentences view; #192 would restore it'],
];

describe('the comment stripper works, in both directions', () => {
  // Without these the main assertions below are satisfied by a stripper that deletes everything.
  test('it removes a phrase that exists only inside a comment', () => {
    expect(stripComments('{/* was "Create custom word sets" */}')).not.toContain('custom word sets');
    expect(stripComments('/* block */ kept')).toBe('  kept');
    expect(stripComments('  // line\nkept')).toBe(' \nkept');
  });

  test('it KEEPS real JSX text', () => {
    expect(stripComments('<p>Track your learning progress</p>'))
      .toContain('Track your learning progress');
  });

  test('CONTROL: the real files still contain visible copy after stripping', () => {
    // A stripper that ate the whole file would make every assertion below vacuous.
    expect(stripComments(read('PrivateRoute.js'))).toContain('Track your learning progress');
    expect(stripComments(read('Home.js'))).toContain('AI Memory Hints');
  });
});

describe.each(['PrivateRoute.js', 'Home.js'])('%s advertises nothing unshipped', (file) => {
  const visible = () => stripComments(read(file));

  test.each(UNSHIPPED)('does not claim "%s" (%s)', (claim) => {
    expect(visible()).not.toContain(claim);
  });
});

test('the claims that REMAIN are ones that actually ship', () => {
  // The point is truthful copy, not empty copy: a fix that deleted every benefit would pass the
  // assertions above. These three are verified in the tree --
  //   progress   userwords/recall_history are persisted server-side per user
  //   AI hints   WordCard.js calls getHint/regenerateHint and renders hint_image
  //   practice   /game/:wordsetId/:mode? exists in App.js
  const card = stripComments(read('PrivateRoute.js'));
  expect(card).toContain('Track your learning progress');
  expect(card).toContain('Get AI-powered memory hints');
  expect(stripComments(read('Home.js'))).toContain('AI Memory Hints');
});
