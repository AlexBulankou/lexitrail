import { resolveWordsetsView } from './wordsetsView';

describe('resolveWordsetsView (lexitrail#52 bug 6)', () => {
  test('shows the grid whenever there are items, regardless of status', () => {
    expect(resolveWordsetsView('loading', true)).toBe('grid');
    expect(resolveWordsetsView('loaded', true)).toBe('grid');
    // keep cached items on screen even if a background refresh failed — the
    // user is not interrupted with an error once something is showing.
    expect(resolveWordsetsView('error', true)).toBe('grid');
  });

  test('shows loading only when fetching AND nothing to show yet', () => {
    expect(resolveWordsetsView('loading', false)).toBe('loading');
  });

  test('REGRESSION: an error with no items surfaces as error, not loading', () => {
    // The original bug: error emptied the list and the render used
    // `length > 0 ? grid : loading`, so a failed fetch showed "Loading…"
    // forever. It must map to a retryable error instead.
    expect(resolveWordsetsView('error', false)).toBe('error');
  });

  test('a successful-but-empty result says "empty", not "loading"', () => {
    expect(resolveWordsetsView('loaded', false)).toBe('empty');
  });
});
