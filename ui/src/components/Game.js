import React, { useState, useEffect, useRef } from 'react';
import WordCard from './WordCard';
import Completed from './Completed';
import { useParams, useLocation } from 'react-router-dom';
import { useWordsetLoader } from '../hooks/useWordsetLoader';
import { useAuth } from '../hooks/useAuth';
import '../styles/Game.css';
import { useNavigate } from 'react-router-dom';

const Game = () => {
  const { wordsetId } = useParams();
  const { state } = useLocation();  // Capture the state passed from navigation
  const showExcludedFromState = state?.showExcluded || false;  // Extract the showExcluded flag
  const { user } = useAuth();
  const navigate = useNavigate();

  if (!user) {
    return <div>Please log in to play the game</div>;
  }

  const {
    toShow: displayWords,
    totalToShow: totalToShow,
    loading,
    timeElapsed,
    handleMemorized,
    handleNotMemorized,
    firstTimeCorrect,
    correctlyMemorized,
    incorrectAttempts,
    toggleExclusion,
    resetGame
  } = useWordsetLoader(wordsetId, user.email, showExcludedFromState);  // Pass showExcludedFromState to hook

  const [layoutClass, setLayoutClass] = useState('layout1c1r');
  const [maxCardsToShow, setMaxCardsToShow] = useState(1);
  const [flippedStates, setFlippedStates] = useState({});

  useEffect(() => {
    const initialFlippedStates = {};
    displayWords.forEach((_, index) => {
      initialFlippedStates[index] = false;
    });
    setFlippedStates(initialFlippedStates);
  }, [displayWords]);


  // Use ref to store previous dimensions and word count
  const previousDimensions = useRef({ width: null, height: null, wordCount: null });

  useEffect(() => {
    // Define the update function with event logging
    const handleUpdate = (event) => {
      console.log(`Event triggered: ${event.type}`);
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

    const cardWidth = 180;
    const cardHeight = 310;
    const extraHorizontalSpaceNeeded = 120;

    const maxColumns = Math.min(Math.floor(width / cardWidth), 12);
    const maxRows = Math.min(Math.floor((height - extraHorizontalSpaceNeeded) / cardHeight), 4);

    // Check if dimensions or displayWords length changed
    if (
      previousDimensions.current.width === width &&
      previousDimensions.current.height === height &&
      previousDimensions.current.wordCount === displayWords.length
    ) {
      console.log(`Skipped update: No change in dimensions or word count since last update (Event: ${triggerEvent}).`);
      return;
    }

    // Update previous dimensions to the current values
    previousDimensions.current = { width, height, wordCount: displayWords.length };

    // Dynamically generate layout options
    const layoutOptions = [];
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

    // Select the most suitable layout based on available cards and window size
    const selectedLayout = layoutOptions
      .filter(option => option.columns <= maxColumns && option.rows <= maxRows)
      .filter(option => option.capacity <= displayWords.length)
      .pop();

    if (selectedLayout) {
      setLayoutClass(selectedLayout.className);
      setMaxCardsToShow(selectedLayout.capacity);

      console.log(
        `Update layout: Width: ${width}, Height: ${height}, maxColumns: ${maxColumns}, maxRows: ${maxRows}, Selected layout: ${selectedLayout.className} (Event: ${triggerEvent}).`
      );
    } else {
      console.log(`Update layout: Could not select layout (Event: ${triggerEvent}).`);
    }
  };

  const setFlippedState = (index, state) => {
    setFlippedStates(prev => ({ ...prev, [index]: state }));
  };

  const handleCardGuessed = (index, isCorrect) => {
    const word = displayWords[index];
    if (isCorrect) {
      handleMemorized(index, maxCardsToShow);
    } else {
      handleNotMemorized(index, maxCardsToShow);
    }
  };

  const toggleWordsetFilter = () => {
    const reversedShowExcluded = !showExcludedFromState;
    navigate(`/game/${wordsetId}`, { state: { showExcluded: reversedShowExcluded } });
  };

  const markAllAsMemorized = () => {
    for (let i = 0; i < maxCardsToShow; i++) {
      setFlippedState(i, false);
      handleCardGuessed(i, true);
    }
  };

  const wordsToRender = displayWords.slice(0, maxCardsToShow);

  if (loading) {
    return <div>Loading...</div>;
  }

  if (displayWords.length === 0) {
    return (
      <Completed
        timeElapsed={timeElapsed}
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

        <button className="show-excluded-button" onClick={toggleWordsetFilter}>
          {showExcludedFromState ? 'Show Included' : 'Show Excluded'}
        </button>
        <div className="timer">
          {Math.floor(timeElapsed / 60)}:{('0' + timeElapsed % 60).slice(-2)}

        </div>
        <div className="memorized">✔️ {correctlyMemorized.size}</div>
      </div>



      <div className={`cards-container ${layoutClass}`}>
        {wordsToRender.map((word, index) => (
          <WordCard
            key={index}
            word={{ ...word, user_id: user.email, index: word.word_index }} // Ensure user_id is passed correctly
            isFlipped={flippedStates[index]} // The flipped state for this card
            handleMemorized={() => handleCardGuessed(index, true)}
            handleNotMemorized={() => handleCardGuessed(index, false)}
            toggleExclusion={() => toggleExclusion(index)}  // Pass toggleExclusion to WordCard
            incorrectAttempts={incorrectAttempts[word.word] || 0}
            setFlippedState={(isFlipped)=>setFlippedState(index, isFlipped)}
          />
        ))}
      </div>

      {/* New Button to Mark All Cards as Memorized */}
      <button
        className="mark-all-memorized-button"
        onClick={markAllAsMemorized}
      >
        ✔️ to all {maxCardsToShow}
      </button>

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

export default Game;