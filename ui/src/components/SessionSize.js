// revamp-2026-09 — the interim "How many words?" screen between Wordsets and Game.
//
// WHY A SCREEN AND NOT A SETTING. #108 turned every practice into a 10-card session, which
// removed the whole-set run-through that advanced learners used. The size is a per-session
// decision (a quick round on the bus, the whole set on a Sunday), so it is asked at the moment
// it applies, defaults to the last pick for THIS wordset, and is one tap to accept.
//
// The pick travels on the game URL as `?n=`, so reload / share / "practice again" keep it, and
// `Game` owns nothing new: it reads one search param and hands `session.js` a budget.
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { getWordsets } from '../services/wordsService';
import {
  SESSION_SIZES, resolveSessionBudget, sessionSizeToken, readSessionSize, writeSessionSize,
} from '../utils/session';
import '../styles/SessionSize.css';

const HINTS = {
  10: { label: '10 words', hint: 'A quick round', time: '~3 min' },
  20: { label: '20 words', hint: 'The daily goal, doubled', time: '~6 min' },
  100: { label: '100 words', hint: 'A long sitting', time: '~30 min' },
  all: { label: 'Whole set', hint: 'Every word, until you are done', time: 'until done' },
};

const SessionSize = () => {
  const { wordsetId, mode = 'PRACTICE' } = useParams();
  const navigate = useNavigate();
  // Derived per wordsetId, NOT read-once state: React Router v6 does not remount on a
  // param-only route change (the same no-remount class session.js documents for Game), so a
  // /session/1/… -> /session/2/… navigation must not keep set 1's highlight or description.
  const remembered = useMemo(() => readSessionSize(wordsetId), [wordsetId]);
  const [wordset, setWordset] = useState(null);

  useEffect(() => {
    const cached = window.__lexitrailWordsetsCache && window.__lexitrailWordsetsCache.data;
    const fromCache = (cached || []).find((w) => String(w.wordset_id) === String(wordsetId)) || null;
    setWordset(fromCache);
    if (fromCache) return;
    let stale = false;
    getWordsets().then((r) => {
      const data = r && Array.isArray(r.data) ? r.data : [];
      if (!stale) setWordset(data.find((w) => String(w.wordset_id) === String(wordsetId)) || null);
    }).catch(() => { /* the screen works without the description */ });
    return () => { stale = true; };
  }, [wordsetId]);

  const choose = (size) => {
    const budget = resolveSessionBudget(String(size));
    writeSessionSize(wordsetId, budget);
    if (window.gtag) {
      window.gtag('event', 'session_size', {
        event_category: 'game_start', event_label: sessionSizeToken(budget), wordset_id: wordsetId, mode,
      });
    }
    navigate(`/game/${wordsetId}/${mode}?n=${sessionSizeToken(budget)}`);
  };

  const modeLabel = mode === 'DUE_TODAY' ? 'Due today' : 'Practice';

  return (
    <main className="session-size">
      <Link to="/wordsets" className="session-size-back">← Word sets</Link>
      <h1 className="session-size-title">How many words?</h1>
      <p className="session-size-sub">
        {wordset ? `${wordset.description} · ${modeLabel}. ` : `${modeLabel}. `}
        Pick a session size; missed words come back until you get them.
      </p>
      <div className="session-size-options" role="group" aria-label="Session size">
        {SESSION_SIZES.map((size) => {
          const budget = resolveSessionBudget(String(size));
          const selected = budget === remembered;
          const h = HINTS[size];
          return (
            <button
              key={String(size)}
              type="button"
              className={`session-size-option${selected ? ' is-selected' : ''}`}
              aria-pressed={selected}
              onClick={() => choose(size)}
            >
              <span className="session-size-option-text">
                <span className="session-size-option-label">{h.label}</span>
                <span className="session-size-option-hint">{h.hint}</span>
              </span>
              <span className="session-size-option-time">{h.time}</span>
            </button>
          );
        })}
      </div>
      <p className="session-size-note">Your last choice is remembered for this set.</p>
    </main>
  );
};

export default SessionSize;
