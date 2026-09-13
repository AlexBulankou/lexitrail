import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Wordsets from './Wordsets';
import { getWordsets } from '../services/wordsService';

// Factory mock (not automock): same rationale as useDueToday.test.js --
// wordsService reads window.config at import time, which jsdom doesn't have.
jest.mock('../services/wordsService', () => ({ getWordsets: jest.fn() }));

// Wordsets.js imports GameMode from ./Game, whose module chain pulls in
// hintService -> apiService -> axios (ESM, unparseable under jest's default
// transform). Only the GameMode enum is actually used by Wordsets.js, so
// stub the whole module down to that rather than dragging in Game's runtime.
jest.mock('./Game', () => ({
  GameMode: { PRACTICE: 'PRACTICE', SHOW_EXCLUDED: 'SHOW_EXCLUDED', TEST: 'TEST', DUE_TODAY: 'DUE_TODAY' },
}));

// lexitrail#52 bug 6's own cache -- reset between tests so one test's fetch
// doesn't make the next start 'loaded' instead of 'loading'.
beforeEach(() => {
  jest.clearAllMocks();
  window.__lexitrailWordsetsCache = { data: null };
});

const renderWordsets = () =>
  render(
    <MemoryRouter>
      <Wordsets profileDetails={null} login={jest.fn()} />
    </MemoryRouter>
  );

describe('lexitrail#406 — loading-state skeleton reserves layout space', () => {
  test('the loading state renders a fixed number of skeleton tiles, not the old bare status line', () => {
    // Never resolves during this test -- keeps status pinned at 'loading'.
    getWordsets.mockReturnValue(new Promise(() => {}));

    renderWordsets();

    const status = screen.getByRole('status');
    expect(status).toHaveClass('wordsets-grid');
    // .wordset-tile is the same class the LOADED grid uses -- the skeleton
    // reuses the real tile markup rather than a bespoke placeholder shape.
    expect(status.querySelectorAll('.wordset-tile')).toHaveLength(6);
    // The old implementation's literal text must be gone -- a leftover copy
    // of both would defeat the CLS fix while still passing a loose assertion.
    expect(screen.queryByText('Loading wordsets…')).not.toBeInTheDocument();
  });

  test('skeleton tiles are inert and hidden from assistive tech (aria-hidden)', () => {
    getWordsets.mockReturnValue(new Promise(() => {}));
    renderWordsets();

    const tiles = document.querySelectorAll('.wordset-tile');
    expect(tiles.length).toBeGreaterThan(0);
    tiles.forEach((tile) => expect(tile).toHaveAttribute('aria-hidden', 'true'));
    // No buttons in the skeleton -- a screen reader tabbing through must not
    // land on placeholder controls that do nothing.
    expect(document.querySelectorAll('.wordset-tile button')).toHaveLength(0);
  });

  test('once data arrives, the skeleton is replaced by the real grid', async () => {
    getWordsets.mockResolvedValue({
      data: [{ wordset_id: 1, description: 'HSK1' }],
    });

    renderWordsets();

    expect(await screen.findByText('HSK1')).toBeInTheDocument();
    expect(document.querySelectorAll('.skeleton-block')).toHaveLength(0);
  });
});
