// src/components/Wordsets.js
import React, { useState, useEffect, useCallback } from 'react';
import { getWordsets } from '../services/wordsService'; // Assuming getWordsets is implemented in wordsService.js
import { useNavigate } from 'react-router-dom';
import '../styles/Wordsets.css'; // Create a CSS file for styling the wordsets grid
import { GameMode } from './Game';
import { resolveWordsetsView } from '../utils/wordsetsView';

// lexitrail#52 bug 6: cache the wordset list across navigations. The list is
// small and changes rarely, so returning to the picker (e.g. after a practice
// session) should render the cached copy instantly and refresh silently in the
// background instead of dropping the user back onto a loading state.
const wordsetsCache = (window.__lexitrailWordsetsCache =
  window.__lexitrailWordsetsCache || { data: null });

const Wordsets = ({ profileDetails, login }) => {
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
    
    // Navigate to the game route
    navigate(`/game/${wordsetId}/${mode}`);
  };

  return (
    <div className="wordsets-container">
      {view === 'loading' ? (
        <div className="wordsets-status" role="status">Loading wordsets…</div>
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

                <button
                  className="wordset-button wordset-button-practice"
                  onClick={() => handleWordsetClick(wordset.wordset_id, GameMode.PRACTICE)}
                  aria-label={`Practice ${wordset.description}`}
                >
                  Practice
                </button>

                <button
                  className="wordset-button wordset-button-due"
                  onClick={() => handleWordsetClick(wordset.wordset_id, GameMode.DUE_TODAY)}
                >
                  Due Today
                </button>


                <button
                  className="wordset-button wordset-button-excluded"
                  onClick={() => handleWordsetClick(wordset.wordset_id, GameMode.SHOW_EXCLUDED)}
                  aria-label={`Show excluded words in ${wordset.description}`}
                >
                  Show Excluded
                </button>

                <button
                  className="wordset-button wordset-button-test"
                  onClick={() => handleWordsetClick(wordset.wordset_id, GameMode.TEST)}
                  aria-label={`Test ${wordset.description}`}
                >
                  Test!
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Wordsets;
