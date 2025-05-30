import React, { useState, useEffect, useRef, useCallback } from 'react';
import WordCard from './WordCard';
import MiniWordCard from './MiniWordCard';
import Completed from './Completed';
import Timer from './Timer';
import { useParams } from 'react-router-dom';
import { useWordsetLoader } from '../hooks/useWordsetLoader';
import { useAuth } from '../hooks/useAuth';
import '../styles/Game.css';
import { useNavigate } from 'react-router-dom';
import Logo from './Logo';

const GameMode = {
  PRACTICE: "PRACTICE",
  SHOW_EXCLUDED: "SHOW_EXCLUDED",
  TEST: "TEST",
};


const Game = () => {
  let { mode, wordsetId } = useParams();
  const validMode = [GameMode.SHOW_EXCLUDED, GameMode.TEST].includes(mode || "")
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

  const [layoutClass, setLayoutClass] = useState('layout1c1r');
  const [maxCardsToShow, setMaxCardsToShow] = useState(1);
  const [flippedStates, setFlippedStates] = useState({});
  const [feedbackClasses, setFeedbackClasses] = useState({});
  const [finalTimeElapsed, setFinalTimeElapsed] = useState(0);
  const [hintsDisplayed, setHintsDisplayed] = useState(true);
  const [allFlipped, setAllFlipped] = useState(false);

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

  const updateLayout = (triggerEvent) => {
    const width = window.innerWidth;
    const height = window.innerHeight;

    const cardWidth = 160;
    const cardHeight = mode === GameMode.TEST ? 345 : 280;

    // TODO: 115 is the width of the incorrect cards container, not sure why 80 and 120 were added
    const extraHorizontalSpaceNeeded = 200 ; //mode === (GameMode.TEST ? 80 : 120) + 115; 
    const extraVerticalSpaceNeeded = 100;

    const maxColumns = Math.min(Math.floor((width - extraVerticalSpaceNeeded) / cardWidth), 20);
    const maxRows = Math.min(Math.floor((height - extraHorizontalSpaceNeeded) / cardHeight), 7);

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

    // Dynamically generate layout options
    var layoutOptions = [];
    for (let columns = 1; columns <= maxColumns; columns++) {
      for (let rows = 1; rows <= maxRows; rows++) {
        const capacity = columns * rows;
        layoutOptions.push({
          className: `layout${columns}c${rows}r`,
          columns,
          rows,
          capacity,
        });
      }
    }

    layoutOptions.sort((a, b) => a.capacity - b.capacity);

    /*
    for (var loIndex in layoutOptions){
      console.log(`Option: ${layoutOptions[loIndex].className}`);
    }
    */

    // Select the most suitable layout based on available cards and window size
    const selectedLayout = layoutOptions
      .filter(option => option.columns <= maxColumns && option.rows <= maxRows)
      .filter(option => option.capacity <= displayWords.length)
      .pop();

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
    navigate(`/game/${wordsetId}/${mode}`);
    loadWordsForWordset();
  }

  const markAllAsMemorized = () => {
    const indicesToMark = [];

    // Send Google Analytics event for bulk recall
    window.gtag('event', 'recall', {
      'event_category': 'learning',
      'event_label': 'correct',
      'wordset_id': wordsetId,
      'mode': mode,
      'cards_count': maxCardsToShow
    });

    // Collect all indices up to maxCardsToShow
    for (let i = 0; i < maxCardsToShow; i++) {
      provideFeedback(i, true, () => {
        setFlippedState(i, false);
        indicesToMark.push(i);
      });
    }
    setAllFlipped(false);

    // Call handleMemorizedMultiple with the collected indices
    handleMemorizedMultiple(indicesToMark, maxCardsToShow);
  };

  const wordsToRender = displayWords.slice(0, maxCardsToShow);

  if (loading.status === 'loading') {
    return (
      <div className="loading-container">
        <Logo size="medium" />
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

  if (displayWords.length === 0 && loading.status === 'loaded') {

    if (mode === GameMode.SHOW_EXCLUDED) {
      return <div>No excluded words in this wordset.</div>;
    }



    return (
      <Completed
        timeElapsed={finalTimeElapsed}
        firstTimeCorrect={firstTimeCorrect}
        incorrectAttempts={incorrectAttempts}
        resetGame={resetGame}
      />
    );
  }

  return (
    <div className="container">

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
          {wordsToRender.map((word, index) => (
            <WordCard
              mode={mode}
              key={index}
              word={{ ...word, user_id: user.email, index: word.word_index }} // Ensure user_id is passed correctly
              isHintDisplayed={hintsDisplayed}
              isFlipped={flippedStates[index]} // The flipped state for this card
              feedbackClass={feedbackClasses[index]}
              handleMemorized={() => handleCardGuessed(index, true)}
              handleNotMemorized={() => handleCardGuessed(index, false)}
              toggleExclusion={() => handleCardInclusionStateChanged(index, word.is_included)}  // Pass toggleExclusion to WordCard
              setFlippedState={(isFlipped) => setFlippedState(index, isFlipped)}
              provideFeedback={(isSuccess, callback) => provideFeedback(index, isSuccess, callback)}
            />
          ))}
        </div>
      </div>


      {mode === GameMode.PRACTICE ? (
        <button
          className="mark-all-memorized-button"
          onClick={markAllAsMemorized}
        >
          ✔️ to all {maxCardsToShow}
        </button>
      ) : (<></>)
      }

      <div className="progress-bar-container">
        <div className="progress-bar">
          <div className="progress" style={{ width: totalToShow ? `${(correctlyMemorized.size / totalToShow) * 100}%` : '0%' }}></div>

        </div>
        <div className="progress-info">
          recalled {correctlyMemorized.size} out of {totalToShow}
        </div>
      </div>

    </div>
  );
};

export { Game, GameMode };