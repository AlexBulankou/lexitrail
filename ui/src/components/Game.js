import React, { useState, useEffect, useRef, useCallback } from 'react';
import WordCard from './WordCard';
import { markOnce, FIRST_CARD_MARK } from '../utils/perfMark';
import MiniWordCard from './MiniWordCard';
import Completed from './Completed';
import {
  SESSION_BUDGET, sessionRemaining, sessionProgress, sessionOutcome,
  nextSessionBinding, sessionVisibleIndices, EMPTY_BINDING, progressLabel } from '../utils/session';
import OnboardingOverlay from './OnboardingOverlay';
import Timer from './Timer';
import { useParams } from 'react-router-dom';
import { useWordsetLoader } from '../hooks/useWordsetLoader';
import { gridDimensions, selectLayout } from '../utils/cardLayout';
import { useAuth } from '../contexts/AuthContext';
import '../styles/Game.css';
import { useNavigate } from 'react-router-dom';
import Logo from './Logo';

const GameMode = {
  PRACTICE: "PRACTICE",
  SHOW_EXCLUDED: "SHOW_EXCLUDED",
  TEST: "TEST",
  DUE_TODAY: "DUE_TODAY",
};


const Game = () => {
  let { mode, wordsetId } = useParams();
  const validMode = [GameMode.SHOW_EXCLUDED, GameMode.TEST, GameMode.DUE_TODAY].includes(mode || "")
    ? mode
    : GameMode.PRACTICE;

  mode = validMode;


  const { user } = useAuth();
  const navigate = useNavigate();

  if (!user) {
    return <div>Please log in to play the game</div>;
  }

  /*
  if (mode == GameMode.TEST) {
    return <div>Test mode not implemented</div>;
  }
    */

  const {
    toShow: displayWords, //1
    loading, //2
    firstTimeCorrect, //4
    incorrectAttempts, //5
    incorrectWords, // 5.5 :)
    correctlyMemorized, //6
    loadWordsForWordset, //7
    totalToShow: totalToShow, //9
    toggleExclusion, //10
    handleMemorized, //11
    handleNotMemorized, //12
    handleMemorizedMultiple,

  } = useWordsetLoader(
    wordsetId,
    user.email,
    mode
  );

  // issue-108 (RD-2): bind the session ONCE per (wordset, mode).
  //
  // A ref rather than state because this must NOT re-derive on re-render:
  // `displayWords` shrinks as words are memorized, so any expression that
  // recomputes the first N pulls unseen words in behind them and the session
  // never ends. `utils/session.js` holds the whole rule — including the
  // read-time mode gate hc2 caught missing on #134, where a bound practice
  // session survived an in-place toggle into the excluded-words browse view
  // and collapsed it to the completion screen.
  const sessionRef = useRef(EMPTY_BINDING);
  sessionRef.current = nextSessionBinding(sessionRef.current, {
    wordsetId,
    mode,
    loaded: loading.status === 'loaded',
    words: displayWords,
    budget: SESSION_BUDGET,
  });
  const sessionKeys = sessionRef.current.keys;

  // Non-session modes (SHOW_EXCLUDED browse, TEST's own 20-cap) keep the full
  // queue — `sessionKeys` stays null and this is the identity function.
  const sessionWords = sessionKeys ? sessionRemaining(displayWords, sessionKeys) : displayWords;
  const progress = sessionProgress(sessionKeys, sessionWords.length);



  const [layoutClass, setLayoutClass] = useState('layout1c1r');
  const [maxCardsToShow, setMaxCardsToShow] = useState(1);

  // NB placed AFTER `maxCardsToShow`'s declaration on purpose: it reads that
  // state, and `const` is in the temporal dead zone until its own line, so
  // computing this next to the other session values (above) throws at render
  // and the component mounts nothing. The E2E harness caught exactly that —
  // `.progress-info` never appeared — which a unit test on the pure helper
  // could not have, since the helper was fine and the CALL SITE was not.
  // The session is over when none of its words remain — or when none of them
  // is still ON SCREEN.
  //
  // 🔴 issue-137: this used to check only `displayWords[0]`, and that dropped
  // `maxCardsToShow` cards at the end of every session, silently. Measured on a
  // 12-word queue with a 10-card budget: 2 cards visible reported "8 of 10", 1
  // card visible reported "9 of 10" — the loss tracked the WINDOW SIZE, which
  // is what identified the cause. As captured words run out the loader pulls an
  // uncaptured word into slot 0, the front-check fired, and captured words
  // still sitting in slot 1 were never offered.
  //
  // Asking whether ANY VISIBLE card belongs to the session keeps the property
  // the front-check was for — the session cannot outlive its own words — while
  // letting the learner finish the cards they were promised.
  // issue-137: the window is filled from SESSION words first, so a captured
  // word can never be stranded behind an uncaptured one -- at ANY window size,
  // including one card, where the previous window-rule degenerated to the
  // front-rule it replaced.
  //
  // These are indices into `displayWords`, not words. The recall handlers do
  // `toShow[index]`, so the index a card carries must be its position in the
  // loader's list; a filtered list would desynchronise every handler from the
  // word it marks. Card-local UI state (flip, feedback) keeps its own 0..N-1
  // index below -- two indices, two jobs, and conflating them is the bug this
  // shape exists to avoid.
  const visibleIndices = sessionVisibleIndices(displayWords, sessionKeys, maxCardsToShow);
  // With the window filled that way, "no captured word is on screen" and "no
  // captured word remains" are the same statement, so the second clause the
  // previous fix needed is gone: the session now ends on its own terms rather
  // than on a proxy for them. It still cannot run past the budget -- when
  // `sessionWords` is empty there is nothing left to render, structurally.
  const sessionOver = Boolean(sessionKeys) && sessionWords.length === 0;
  const [flippedStates, setFlippedStates] = useState({});
  const [feedbackClasses, setFeedbackClasses] = useState({});
  const [finalTimeElapsed, setFinalTimeElapsed] = useState(0);
  const [hintsDisplayed, setHintsDisplayed] = useState(false); // SUG-2: hints opt-in (toggle via "Show Hints")
  const [allFlipped, setAllFlipped] = useState(false);

  // SUG-5: one-time first-run coach-mark explaining the game controls.
  const [showOnboarding, setShowOnboarding] = useState(() => {
    try { return !localStorage.getItem('lexitrail_onboarded'); } catch { return false; }
  });
  const dismissOnboarding = () => {
    try { localStorage.setItem('lexitrail_onboarded', '1'); } catch { /* private mode — just close */ }
    setShowOnboarding(false);
  };

  // Optional callback to handle timer tick in parent (if you need the time in Game component)
  const handleTimerTick = useCallback((elapsedTime, isTimerBeingCleared = false) => {
    console.log('Elapsed Time:', elapsedTime);

    if (isTimerBeingCleared) {
      setFinalTimeElapsed(elapsedTime);
    }
  }, [setFinalTimeElapsed]); // setFinalTimeElapsed is stable from useState, but explicit dependency is good practice

  // Initialize or re-run loadWordsForWordset on dependency change
  useEffect(() => {
    if (wordsetId && user) {
      loadWordsForWordset();
    }
  }, [wordsetId, user, mode, loadWordsForWordset]);

  // TODO: consider re-activating this block if flipped states are loading incorrectly
  /*
  useEffect(() => {
    const initialFlippedStates = {};
    displayWords.forEach((_, index) => {
      initialFlippedStates[index] = false;
    });
    setFlippedStates(initialFlippedStates);
  }, [displayWords]);
*/

  // Use ref to store previous dimensions and word count
  const previousDimensions = useRef({ width: null, height: null, wordCount: null });

  useEffect(() => {
    // Define the update function with event logging
    const handleUpdate = (event) => {
      // console.log(`Event triggered: ${event.type}`);
      updateLayout(event.type);
    };

    // Add event listeners
    window.addEventListener('resize', handleUpdate);
    window.addEventListener('orientationchange', handleUpdate);
    window.addEventListener('visibilitychange', handleUpdate);
    window.addEventListener('fullscreenchange', handleUpdate);
    window.addEventListener('pageshow', handleUpdate);

    // Initial call to set the layout
    updateLayout('initial');

    // Cleanup listeners on unmount
    return () => {
      window.removeEventListener('resize', handleUpdate);
      window.removeEventListener('orientationchange', handleUpdate);
      window.removeEventListener('visibilitychange', handleUpdate);
      window.removeEventListener('fullscreenchange', handleUpdate);
      window.removeEventListener('pageshow', handleUpdate);
    };
  }, [displayWords.length]);

  // issue-266: mark when the first card is actually on screen.
  //
  // In an EFFECT rather than during render, deliberately: an effect runs after
  // React has committed, so the mark lands when the card is painted rather than
  // when we decided to paint it. Those differ by the commit, which is part of
  // what the issue is complaining about on a big dataset.
  //
  // 🔴 The condition must match the render guard EXACTLY, and my first version did
  // not -- hc2 caught it on #288. The guard below is
  //
  //     if ((displayWords.length === 0 || sessionOver) && loading.status === 'loaded')
  //         -> <Completed/>, NOT a card
  //
  // so a card shows only when `!sessionOver` as well. I omitted that, and wrote a
  // comment claiming the condition "mirrors the render guards" -- asserting the
  // property I had failed to implement, which is worse than omitting it silently,
  // because the comment tells the next reader not to check.
  //
  // It matters more than an ordinary off-by-one because `markOnce` is once-EVER:
  // a single wrong mark does not add noise, it permanently consumes the name and
  // the real first card can never be recorded for that page load. The metric would
  // then report a number that looks plausible and measures the Completed screen.
  useEffect(() => {
    if (loading.status === 'loaded' && displayWords.length > 0 && !sessionOver) {
      markOnce(FIRST_CARD_MARK);
    }
  }, [loading.status, displayWords.length, sessionOver]);


  const updateLayout = (triggerEvent) => {
    const width = window.innerWidth;
    const height = window.innerHeight;

    const cardWidth = 160;
    const cardHeight = mode === GameMode.TEST ? 345 : 280;

    // TODO: 115 is the width of the incorrect cards container, not sure why 80 and 120 were added
    const extraHorizontalSpaceNeeded = 200 ; //mode === (GameMode.TEST ? 80 : 120) + 115; 
    const extraVerticalSpaceNeeded = 100;

    // issue-338: floored at 1x1 inside `gridDimensions`. This previously read
    // `Math.floor((390 - 200) / 280)` = 0 in phone LANDSCAPE, which emptied the
    // option list below and left `layoutClass` at its initial `layout1c1r` —
    // one card, indistinguishable from having chosen one.
    const { maxColumns, maxRows } = gridDimensions(
      width, height, cardWidth, cardHeight,
      extraVerticalSpaceNeeded, extraHorizontalSpaceNeeded);

    // Check if dimensions or displayWords length changed
    if (
      previousDimensions.current.width === width &&
      previousDimensions.current.height === height &&
      previousDimensions.current.wordCount === displayWords.length
    ) {
      // console.log(`Skipped update: No change in dimensions or word count since last update (Event: ${triggerEvent}).`);
      return;
    }

    // Update previous dimensions to the current values
    previousDimensions.current = { width, height, wordCount: displayWords.length };

    // issue-338: option generation + selection moved to utils/cardLayout so it
    // can be unit-tested. The two `.filter`s on columns/rows were redundant --
    // the loops above never produced an option exceeding either bound -- so the
    // extracted version drops them rather than carrying a filter that has never
    // removed anything.
    const selectedLayout = selectLayout(maxColumns, maxRows, displayWords.length);

    if (selectedLayout) {
      setLayoutClass(selectedLayout.className);
      setMaxCardsToShow(selectedLayout.capacity);

      // Add this: Set the height for incorrect-cards-container
      const availableHeight = selectedLayout.rows * cardHeight;
      document.documentElement.style.setProperty('--cards-container-height', `${availableHeight}px`);

      //console.log(
      //  `Update layout: Width: ${width}, Height: ${height}, maxColumns: ${maxColumns}, maxRows: ${maxRows}, Selected layout: ${selectedLayout.className} (Event: ${triggerEvent}).`
      // );
    } else {
      console.log(`Update layout: Could not select layout (Event: ${triggerEvent}).`);
    }
  };

  const setFlippedState = (index, state) => {
    setFlippedStates(prev => ({ ...prev, [index]: state }));
  };

  const provideFeedback = (index, isSuccess, callback) => {
    const newFeedbackClass = isSuccess ? 'success' : 'failure'
    setFeedbackClasses(prev => ({ ...prev, [index]: newFeedbackClass }));
    setTimeout(() => setFeedbackClasses(prev => ({ ...prev, [index]: '' })), 200);
    callback();
  };

  // issue-137: `index` here is the LOADER-LIST position, which is what
  // `handleMemorized`/`handleNotMemorized` index (`toShow[index]`). It used to
  // be the same number as the on-screen slot because the visible set was a
  // prefix; it is not any more. Nothing in this function is slot-keyed --
  // `provideFeedback` and `setFlippedState` are wired with the slot directly
  // at the call site -- so no second argument is threaded here.
  const handleCardGuessed = (index, isCorrect) => {
    // Send Google Analytics event for single recall attempt
    window.gtag('event', 'recall', {
      'event_category': 'learning',
      'event_label': isCorrect ? 'correct' : 'incorrect',
      'wordset_id': wordsetId,
      'mode': mode,
      'cards_count': 1
    });

    if (isCorrect) {
      handleMemorized(index, maxCardsToShow);
    } else {
      handleNotMemorized(index, maxCardsToShow);
    }
  };

  const handleCardInclusionStateChanged = (index, isIncluded) => {
    const word = displayWords[index];
    toggleExclusion(index, maxCardsToShow);
  };

  const toggleWordsetFilter = () => {
    const reversedPracticeMode = mode == GameMode.PRACTICE ? GameMode.SHOW_EXCLUDED : GameMode.PRACTICE;
    navigate(`/game/${wordsetId}/${reversedPracticeMode}`);
  };

  const toggleShowHints = () => {
    setHintsDisplayed(!hintsDisplayed);
  };


  const toggleFlipStates = () => {
    const newFlippedState = !allFlipped;
    for (let i = 0; i < maxCardsToShow; i++) {
      setFlippedState(i, newFlippedState);
    }
    setAllFlipped(newFlippedState);
  };

  const resetGame = () => {
    // Clear the binding so the next loaded queue starts a FRESH session.
    // Without this, "practice again" would re-enter a session whose words are
    // all already done and land straight back on the completion screen.
    sessionRef.current = EMPTY_BINDING;
    navigate(`/game/${wordsetId}/${mode}`);
    loadWordsForWordset();
  }

  // issue-264: RESTORED. Alex ruled this back on 2026-08-30 (option A, via zz1)
  // -- "my favorite feature ... helps accelerate training for advanced learners".
  // The ruling knowingly accepts the SRS-provenance trade-off #109 retired it
  // for, so that argument is settled and deliberately not re-made here.
  //
  // 🔴 ONE DEVIATION FROM THE LITERAL 2026-08-13 CODE, AND IT IS A BUG FIX, NOT
  // A REDESIGN. The original looped `for (i = 0; i < maxCardsToShow; i++)`,
  // which was correct when the visible cards WERE indices 0..maxCardsToShow-1.
  // They are not any more: `visibleIndices` is chosen by session state
  // (`sessionVisibleIndices`), so the old loop would now mark cards that are
  // not on screen and skip cards that are. Restoring it byte-for-byte would
  // restore a control that lies about what it ticked.
  const markAllAsMemorized = () => {
    const indicesToMark = [];

    // Send Google Analytics event for bulk recall
    window.gtag('event', 'recall', {
      'event_category': 'learning',
      'event_label': 'correct',
      'wordset_id': wordsetId,
      'mode': mode,
      'cards_count': visibleIndices.length
    });

    visibleIndices.forEach((i) => {
      provideFeedback(i, true, () => {
        setFlippedState(i, false);
        indicesToMark.push(i);
      });
    });
    setAllFlipped(false);

    handleMemorizedMultiple(indicesToMark, maxCardsToShow);
  };

  const wordsToRender = visibleIndices.map((i) => ({ word: displayWords[i], wordIndex: i }));

  if (loading.status === 'loading') {
    return (
      <div className="loading-container" role="status" aria-live="polite">
        <Logo size="medium" />
        {/* lexitrail#266: was a bare "Loading..." string. Alex asked for a
            visual indicator; static text is not one. Matches the pre-mount
            spinner in public/index.html so the two hand off invisibly. */}
        <div className="loading-spinner" data-testid="loading-spinner" />
        <div>Loading...</div>
      </div>
    );
  }

  if (loading.status === 'error') {
    return (
      <div className="error-container">
        <Logo size="small" />
        <div>Error loading data. Please try again.</div>
      </div>
    );
  }

  if ((displayWords.length === 0 || sessionOver) && loading.status === 'loaded') {

    if (mode === GameMode.SHOW_EXCLUDED) {
      return <div>No excluded words in this wordset.</div>;
    }



    return (
      <Completed
        timeElapsed={finalTimeElapsed}
        firstTimeCorrect={firstTimeCorrect}
        incorrectAttempts={incorrectAttempts}
        incorrectWords={incorrectWords}
        resetGame={resetGame}
        outcome={sessionKeys ? sessionOutcome(sessionKeys, SESSION_BUDGET) : null}
        sessionDone={progress.done}
        sessionTotal={progress.total}
      />
    );
  }

  return (
    <div className="container">

      {showOnboarding && <OnboardingOverlay mode={mode} onDismiss={dismissOnboarding} />}

      <div className="progress-stats">
        <div className="not-memorized">❌ {Object.keys(incorrectAttempts).length}</div>

        <div className="game-settings">
          <button className="game-settings-button" onClick={toggleShowHints}>
            {hintsDisplayed ? 'Hide Hints' : 'Show Hints'}
          </button>
          {mode !== GameMode.TEST ? (
            <>
              <button className="game-settings-button" onClick={toggleFlipStates}>
                {allFlipped ? 'Flip all back' : 'Flip all'}
              </button>
              <button className="game-settings-button" onClick={toggleWordsetFilter}>
                {mode == GameMode.SHOW_EXCLUDED ? 'Show Included' : 'Show Excluded'}
              </button>
            </>
          ) : (
            <></>
          )}
        </div>

        <div className="timer">
          <Timer onTick={handleTimerTick} />  {/* Timer updates every second */}

        </div>
        <div className="memorized">✔️ {correctlyMemorized.size}</div>

      </div>


      <div className="cards-area">
        <div className="incorrect-cards-container">
          {Object.values(incorrectWords).map((word) => (
            <MiniWordCard
              mode={mode}
              word={{ ...word, user_id: user.email, index: word.word_index }}
            />
          ))}
        </div>
        <div className={`cards-container ${layoutClass}`}>
          {wordsToRender.map(({ word, wordIndex }, index) => (
            <WordCard
              mode={mode}
              key={index}
              word={{ ...word, user_id: user.email, index: word.word_index }} // Ensure user_id is passed correctly
              isHintDisplayed={hintsDisplayed}
              // issue-137: `index` is the SLOT (card-local UI state — flip,
              // feedback, and the 0..N-1 loop in toggleFlipStates).
              // `wordIndex` is the position in the loader's list, which is what
              // every recall handler indexes. They coincided while the visible
              // set was a prefix; they do not now.
              isFlipped={flippedStates[index]} // The flipped state for this card
              feedbackClass={feedbackClasses[index]}
              handleMemorized={() => handleCardGuessed(wordIndex, true)}
              handleNotMemorized={() => handleCardGuessed(wordIndex, false)}
              toggleExclusion={() => handleCardInclusionStateChanged(wordIndex, word.is_included)}  // Pass toggleExclusion to WordCard
              setFlippedState={(isFlipped) => setFlippedState(index, isFlipped)}
              provideFeedback={(isSuccess, callback) => provideFeedback(index, isSuccess, callback)}
            />
          ))}
        </div>
      </div>


      {(mode === GameMode.PRACTICE || mode === GameMode.DUE_TODAY) ? (
        <button
          className="mark-all-memorized-button"
          onClick={markAllAsMemorized}
        >
          ✔️ to all {visibleIndices.length}
        </button>
      ) : (<></>)
      }

      {/* issue-108: inside a session the bar tracks position within THE
          SESSION, not within the wordset. Denominating on `totalToShow` (149
          for HSK 2) is what made practice feel endless: ten cards in, the bar
          has moved 7% and the finish line is invisible. Outside a session
          (browse / test) the wordset-wide numbers are still the right answer,
          so that rendering is unchanged. */}
      <div className="progress-bar-container">
        <div className="progress-bar">
          <div
            className="progress"
            style={{
              width: sessionKeys
                ? `${progress.percent}%`
                : (totalToShow ? `${(correctlyMemorized.size / totalToShow) * 100}%` : '0%'),
            }}
          ></div>

        </div>
        <div className="progress-info">
          {sessionKeys
            ? progressLabel(progress, visibleIndices.length)
            : `recalled ${correctlyMemorized.size} out of ${totalToShow}`}
        </div>
      </div>

    </div>
  );
};

export { Game, GameMode };