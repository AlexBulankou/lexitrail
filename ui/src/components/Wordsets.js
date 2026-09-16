// src/components/Wordsets.js
import React, { useState, useEffect, useCallback } from 'react';
import { getWordsets } from '../services/wordsService'; // Assuming getWordsets is implemented in wordsService.js
import { useNavigate } from 'react-router-dom';
import '../styles/Wordsets.css';
import SiteFooter from './SiteFooter'; // Create a CSS file for styling the wordsets grid
import { GameMode } from './Game';
import { resolveWordsetsView } from '../utils/wordsetsView';

// lexitrail#52 bug 6: cache the wordset list across navigations. The list is
// small and changes rarely, so returning to the picker (e.g. after a practice
// session) should render the cached copy instantly and refresh silently in the
// background instead of dropping the user back onto a loading state.
const wordsetsCache = (window.__lexitrailWordsetsCache =
  window.__lexitrailWordsetsCache || { data: null });

// lexitrail#406: the signed-out home's loading state used to render a single
// line of text ("Loading wordsets…") with no reserved layout space, so the
// real grid arriving caused a large post-first-paint reflow (CLS 0.168 ->
// 0.228, attributed to this exact container). A small, FIXED skeleton count
// (not tied to the real wordset total, which lex#427 already changed by one)
// reserves roughly the right amount of above-the-fold space without needing
// to track the live count.
const WORDSET_SKELETON_COUNT = 6;

// Reuses the REAL tile's classes (.wordset-tile / .wordset-button-group /
// .wordset-button-*) so the reserved box model is derived from the actual
// CSS rules (grid rows, padding, --min-tap-target floors) rather than a
// hand-computed pixel guess that silently drifts the moment that CSS
// changes. Plain `div`s, not `button`s -- nothing here is interactive, and
// `aria-hidden` + the wrapping `role="status"` keep it invisible to
// assistive tech instead of announcing placeholder content.
const WordsetSkeletonTile = () => (
  <div className="wordset-tile" aria-hidden="true">
    <div className="wordset-button-group">
      <div className="wordset-header">
        <div className="wordset-header-text skeleton-block skeleton-text" />
      </div>
      <div className="wordset-button wordset-button-due skeleton-block" />
      <div className="wordset-button wordset-button-practice skeleton-block" />
      <div className="wordset-button wordset-button-test skeleton-block" />
      <div className="wordset-button wordset-button-excluded skeleton-block" />
    </div>
  </div>
);

// uibug 2026-09-16 (footer-in-wordsets-flex): `embedded` is passed by Home,
// which mounts its OWN page-bottom <SiteFooter /> after the features/CTA
// sections — without it the home page showed the footer twice (once mid-page
// beside the tiles, once at the bottom). Standalone /wordsets keeps its own.
const Wordsets = ({ profileDetails, login, embedded = false }) => {
  const [wordsets, setWordsets] = useState(wordsetsCache.data || []);
  // 'loading' | 'loaded' | 'error'. Start 'loaded' if we have a cached list so
  // the picker never shows a spinner on a revisit.
  const [status, setStatus] = useState(wordsetsCache.data ? 'loaded' : 'loading');
  const navigate = useNavigate();

  const fetchWordsets = useCallback(async ({ silent }) => {
    // Only show the blocking loading state when we have nothing to show;
    // background refreshes over a cached list stay silent.
    if (!silent) setStatus('loading');
    try {
      const response = await getWordsets();
      const data = response && Array.isArray(response.data) ? response.data : [];
      wordsetsCache.data = data;
      setWordsets(data);
      setStatus('loaded');
    } catch (error) {
      console.error('Error fetching wordsets:', error);
      // Keep any cached list on screen; only surface the error (with a retry)
      // when there is nothing to show — never leave the user on an endless
      // "Loading…" as the old code did.
      if (!wordsetsCache.data) setStatus('error');
    }
  }, []);

  useEffect(() => {
    // First load blocks with a loading state; if we already have a cached list,
    // refresh in the background without interrupting the user.
    fetchWordsets({ silent: Boolean(wordsetsCache.data) });
  }, [fetchWordsets]);

  const view = resolveWordsetsView(status, wordsets.length > 0);

  const handleWordsetClick = (wordsetId, mode) => {
    // Send Google Analytics event
    if (mode === GameMode.PRACTICE || mode === GameMode.TEST || mode === GameMode.DUE_TODAY) {
      const label = mode === GameMode.PRACTICE
        ? 'practice'
        : mode === GameMode.TEST ? 'test' : 'due_today';
      window.gtag('event', 'wordset_click', {
        'event_category': 'game_start',
        'event_label': label,
        'wordset_id': wordsetId
      });
    }
    
    // revamp-2026-09: session modes go through "How many words?" first. TEST keeps its own
    // 20-cap and SHOW_EXCLUDED is a browse view, so both still go straight to the game.
    if (mode === GameMode.PRACTICE || mode === GameMode.DUE_TODAY) {
      navigate(`/session/${wordsetId}/${mode}`);
      return;
    }
    // Navigate to the game route
    navigate(`/game/${wordsetId}/${mode}`);
  };

  return (
    <>
    <div className="wordsets-container">
      {view === 'loading' ? (
        <div className="wordsets-grid" role="status" aria-label="Loading wordsets…">
          {Array.from({ length: WORDSET_SKELETON_COUNT }).map((_, i) => (
            <WordsetSkeletonTile key={i} />
          ))}
        </div>
      ) : view === 'error' ? (
        <div className="wordsets-status wordsets-error" role="alert">
          <p>Couldn't load your wordsets.</p>
          <button
            className="wordsets-retry"
            onClick={() => fetchWordsets({ silent: false })}
          >
            Retry
          </button>
        </div>
      ) : view === 'empty' ? (
        <div className="wordsets-status">No wordsets available yet.</div>
      ) : (
        <div className="wordsets-grid">
          {wordsets.map(wordset => (
            <div key={wordset.wordset_id} className="wordset-tile">
              <div className="wordset-button-group" >
                <div className="wordset-header">
                  <div className="wordset-header-text">{wordset.description}</div>
                </div>

                {/* revamp-2026-09: Due Today is the primary action — it is where a returning
                    learner starts — and Practice / Test share the row under it. Show Excluded
                    is demoted to a text button: it is a browse view, not a way to learn. */}
                <button
                  className="wordset-button wordset-button-due"
                  onClick={() => handleWordsetClick(wordset.wordset_id, GameMode.DUE_TODAY)}
                  aria-label={`Due today in ${wordset.description}`}
                >
                  Due today
                </button>

                <button
                  className="wordset-button wordset-button-practice"
                  onClick={() => handleWordsetClick(wordset.wordset_id, GameMode.PRACTICE)}
                  aria-label={`Practice ${wordset.description}`}
                >
                  Practise
                </button>

                <button
                  className="wordset-button wordset-button-test"
                  onClick={() => handleWordsetClick(wordset.wordset_id, GameMode.TEST)}
                  aria-label={`Test ${wordset.description}`}
                >
                  Test
                </button>

                <button
                  className="wordset-button wordset-button-excluded"
                  onClick={() => handleWordsetClick(wordset.wordset_id, GameMode.SHOW_EXCLUDED)}
                  aria-label={`Show excluded words in ${wordset.description}`}
                >
                  Excluded
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
    {/* uibug 2026-09-16: the footer must be a SIBLING of .wordsets-container,
        never a child — the container is `display: flex` (row, centered,
        Wordsets.css), so a footer inside it lays out BESIDE the tile grid:
        on a 390px viewport the two children's min-widths (240px grid floor +
        148px footer) overflowed the 350px content box, squeezing the grid to
        x=0.8 (killing the 20px gutter) and pinning "Support: support@..."
        0.8px from the right screen edge. Below the container it stacks in
        normal flow, full-width, after the grid. */}
    {!embedded && <SiteFooter />}
    </>
  );
};

export default Wordsets;
