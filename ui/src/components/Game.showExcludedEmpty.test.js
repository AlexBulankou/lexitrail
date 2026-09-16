/**
 * uibug 2026-09 — /game/:id/SHOW_EXCLUDED with no excluded words used to
 * return a BARE, CLASSLESS <div>No excluded words in this wordset.</div>.
 * Measured live: the div's box landed at {x:0, y:0, h:22}, entirely under the
 * fixed 48px navbar (z-index 1000), so the route rendered as navbar + blank
 * page — and the sweep's waitForSelector('.cards-area, .empty-state,
 * .completed-container') timed out because the div carried no class at all.
 *
 * jsdom cannot see the rendered geometry (the navbar occlusion is pinned by
 * the harness sweep instead); what it CAN pin is the contract everything else
 * keys on: the empty state renders inside a container carrying the
 * `empty-state` class — the hook the stylesheet's navbar-clearing rule and the
 * sweep's readiness selector both target — with the message text intact.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';

jest.mock('react-router-dom', () => ({
  useParams: () => ({ mode: 'SHOW_EXCLUDED', wordsetId: '1' }),
  useSearchParams: () => [new URLSearchParams()],
  useNavigate: () => jest.fn(),
}));

jest.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { email: 'test@example.com' } }),
}));

// Not rendered in the empty branch; mocked only to sever its import chain
// (WordCard → hintService → apiService → axios ESM, which jsdom can't parse).
jest.mock('./WordCard', () => () => null);

// Loader resolved with ZERO words — the exact state measured live on
// /game/1/SHOW_EXCLUDED (a wordset with nothing excluded).
jest.mock('../hooks/useWordsetLoader', () => ({
  useWordsetLoader: () => ({
    toShow: [],
    loading: { status: 'loaded' },
    firstTimeCorrect: [],
    incorrectAttempts: {},
    incorrectWords: [],
    correctlyMemorized: [],
    loadWordsForWordset: jest.fn(),
    totalToShow: 0,
    toggleExclusion: jest.fn(),
    handleMemorized: jest.fn(),
    handleNotMemorized: jest.fn(),
    handleMemorizedMultiple: jest.fn(),
  }),
}));

import { Game } from './Game';

describe('SHOW_EXCLUDED empty state', () => {
  test('the message renders inside an .empty-state container, not a bare div', () => {
    render(<Game />);
    const message = screen.getByText(/no excluded words in this wordset/i);
    const container = message.closest('.empty-state');
    expect(container).not.toBeNull();
    expect(container).toBeVisible();
  });

  test('the harness readiness selector matches (the live sweep timed out on it)', () => {
    render(<Game />);
    // Exactly the waitForSelector the sweep uses to decide the route is ready.
    expect(
      document.querySelector('.cards-area, .empty-state, .completed-container')
    ).not.toBeNull();
  });
});
