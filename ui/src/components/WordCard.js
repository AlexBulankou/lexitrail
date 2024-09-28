import React, { useState } from 'react';
import '../styles/WordCard.css';

const WordCard = ({ word, handleMemorized, handleNotMemorized, toggleExclusion, incorrectAttempts }) => {
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
      flipCard(); // Flip back to front first
    }
    handleMemorized(); // Then proceed with memorizing
  };

  const onNotMemorized = () => {
    if (isFlipped) {
      flipCard(); // Flip back to front first
    }
    handleNotMemorized(); // Then proceed with not memorizing
  };

  // Helper function to determine the style for recall states
  const getRecallStateStyle = (state) => {
    return {
      backgroundColor: state === 0 ? 'green' : 'red',
      color: 'white',
    };
  };

  // Remove leading and trailing quotes and whitespace
const removeQuotes = (text) => text.replace(/^['"]+|['"]+$/g, '').trim();

 // Remove quotes and calculate the longest line for font size
 const calculateFontSize = (text) => {
  // Remove leading and trailing quotes
  const trimmedText = text.trim();

  // Split text by '\n' and find the longest line
  const lines = trimmedText.split('\n');
  const longestLineLength = Math.max(...lines.map(line => removeQuotes(line).length));

  // Calculate font size based on the longest line length
  const fontSize = Math.max(10 / longestLineLength, 1); // Ensure the font size doesn't go too small
  return `${fontSize}rem`;
};



  return (
    <div className="word-card">
      {/* Metadata Section */}
      <div className="metadata">


        <button
          className={`exclude-button ${word.is_included ? 'red' : 'green'}`}
          onClick={(e) => {
            stopPropagation(e);
            toggleExclusion();  // Calls the passed toggleExclusion function
          }}
        >
          {word.is_included ? 'Exclude' : 'Include'}
        </button>


        <div className="recall-state" style={getRecallStateStyle(word.recall_state)}>
          {word.recall_state}
        </div>

        <div className="recall-history">
          {word.recall_history.map((recall, index) => (
            <div key={index} className="recall-item">
              <div className="recall-item-time">{recall.recall_time}</div>
              <div className="recall-item-guess">{recall.recall ? '✅' : '❌'}</div>
              <div
                className="recall-item-old-state"
                style={getRecallStateStyle(recall.old_recall_state ?? 0)}
              >
                {recall.old_recall_state ?? 0}
              </div>
              <div className="recall-item-transition">→</div>
              <div
                className="recall-item-new-state"
                style={getRecallStateStyle(recall.new_recall_state)}
              >
                {recall.new_recall_state}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div onClick={handleCardClick} className={`word-card-inner ${isFlipped ? 'flipped' : ''}`}>
        <div
          className="word-card-front"
          style={{ fontSize: calculateFontSize(word.word) }} // Dynamically set the font size
        >
          {word.word} {/* Remove preceding and trailing quotes */}
        </div>
        <div
          className="word-card-back"
          style={{ fontSize: calculateFontSize(word.meaning) }} // Dynamically set the font size
        >
          <p>
            {word.meaning.trim().split('\n').map((line, index) => (
              <React.Fragment key={index}>
                {removeQuotes(line)}
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
    </div>
  );
};

export default WordCard;
