import React, { useState } from 'react';
import '../styles/WordCard.css';

const WordCard = ({ word, handleMemorized, handleNotMemorized, incorrectAttempts, toggleExclusion }) => {
  const [isFlipped, setIsFlipped] = useState(false);

  const handleCardClick = () => {
    setIsFlipped(!isFlipped);
  };

  const stopPropagation = (e) => {
    e.stopPropagation();
  };

  const flipCard = () => {
    setIsFlipped(!isFlipped);
  };

  const onMemorized = () => {
    if (isFlipped) {
      flipCard();
    }
    handleMemorized();
  };

  const onNotMemorized = () => {
    if (isFlipped) {
      flipCard();
    }
    handleNotMemorized();
  };

  const handleExcludeToggle = (e) => {
    e.stopPropagation();
    toggleExclusion();
  };

  return (
    <div className="word-card" onClick={handleCardClick}>
      <div className={`word-card-inner ${isFlipped ? 'flipped' : ''}`}>
        <div className="word-card-front">
          {word.word}
        </div>
        <div className="word-card-back">
          <p>
            {word.meaning.split('\n').map((line, index) => (
              <React.Fragment key={index}>
                {line}
                <br />
              </React.Fragment>
            ))}
          </p>
        </div>
      </div>

      <div className="buttons" onClick={stopPropagation}>
        <button onClick={onNotMemorized}>❌</button>
        <button onClick={onMemorized}>✔️</button>
      </div>

      {/* Exclude/Include Button */}
      <button
        onClick={handleExcludeToggle}
        style={{ backgroundColor: word.is_included ? 'red' : 'green' }}
      >
        {word.is_included ? 'Exclude' : 'Include'}
      </button>

      {/* Recall History */}
      <div className="recall-history">
        {word.recall_history.slice(-3).map((attempt, index) => (
          <span key={index}>
            {attempt.recall ? '✔️' : '❌'} {attempt.timestamp}
          </span>
        ))}
      </div>
    </div>
  );
};

export default WordCard;
