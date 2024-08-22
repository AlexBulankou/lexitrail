import React, { useState, useEffect } from 'react';
import WordCard from './WordCard';
import '../styles/Game.css'; // Importing styles for the Game component

const Game = ({
  timeElapsed,
  displayWords, // Receive the list of words directly from App.js
  handleMemorized,
  handleNotMemorized,
  firstTimeCorrectCount,
  totalWords,
  correctlyMemorizedCount,
  incorrectAttempts
}) => {
  const [layoutClass, setLayoutClass] = useState('layout1');
  const [maxCardsToShow, setMaxCardsToShow] = useState(1); // State to track max cards based on layout

  useEffect(() => {
    updateLayout();
    window.addEventListener('resize', updateLayout);

    return () => {
      window.removeEventListener('resize', updateLayout);
    };
  }, []);

  const updateLayout = () => {
    const width = window.innerWidth;
    const height = window.innerHeight;

    const cardWidth = 150; // Estimated width of each card in pixels
    const cardHeight = 200; // Estimated height of each card in pixels

    // Determine layout based on both width and height
    if (width <= cardWidth * 2) {
      setLayoutClass('layout1');
      setMaxCardsToShow(1); // Layout1 allows 1 card
    } else if (width <= cardWidth * 3) {
      if (height <= cardHeight * 2) {
        setLayoutClass('layout2');
        setMaxCardsToShow(2); // Layout2 allows 2 cards
      } else {
        setLayoutClass('layout4');
        setMaxCardsToShow(4); // Layout2 allows 4 cards
      }
    } else {
      if (height <= cardHeight * 2) {
        setLayoutClass('layout3');
        setMaxCardsToShow(3); // Layout3 allows 3 cards
      } else {
        setLayoutClass('layout5');
        setMaxCardsToShow(6); // Layout5 allows 6 cards
      }
    } 
  };

  const handleCardGuessed = (index, isCorrect) => {
    const word = displayWords[index];
    console.log(`handleCardGuessed: Guessing word at index ${index}: ${word.word}, isCorrect: ${isCorrect}`);

    
    if (isCorrect) {
      handleMemorized(index); // Mark the word as memorized
    } else {
      handleNotMemorized(index); // Mark the word as not memorized
    }
  };

  // Slice displayWords to respect the layout rules
  const wordsToRender = displayWords.slice(0, maxCardsToShow);

  return (
    <div className="container">
      <div className="timer">
        {Math.floor(timeElapsed / 60)}:{('0' + timeElapsed % 60).slice(-2)}
      </div>
      <div className={`cards-container ${layoutClass}`}>
        {wordsToRender.map((word, index) => (
          <WordCard
            key={index}
            word={word}
            handleMemorized={() => handleCardGuessed(index, true)}
            handleNotMemorized={() => handleCardGuessed(index, false)}
            incorrectAttempts={incorrectAttempts[word.word] || 0}
          />
        ))}
      </div>
      <div className="progress-bar-container">
        <div className="progress-bar">
          <div className="progress" style={{ width: `${(correctlyMemorizedCount / totalWords) * 100}%` }}></div>
        </div>
        <div className="progress-info">
          word {correctlyMemorizedCount} out of {totalWords}
        </div>
      </div>
      <div className="progress-stats">
        <div className="not-memorized">❌ {Object.keys(incorrectAttempts).length}</div>
        <div className="memorized">✔️ {correctlyMemorizedCount}</div>
      </div>
    </div>
  );
};

export default Game;
