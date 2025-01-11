import React, { useState, useEffect } from 'react';
import { GameMode } from './Game';
import PinyinText from './PinyinText';
import '../styles/MiniWordCard.css';

const MiniWordCard = ({ mode, word }) => {

  const [loadingWord, setLoadingWord] = useState(true); // New state for controlling button loading state

  useEffect(() => {
    // Validate that user_id and word_id are set correctly
    if (word.user_id && word.word_id) {
      setLoadingWord(false);
    }
  }, [word.user_id, word.word_id]);

  // Remove leading and trailing quotes and whitespace
  const removeQuotes = (text) => {
    if (!text) {
      return "";
    }

    return text
      .replace(/^['"]+|['"]+$/g, '')  // Remove quotes at the beginning and end
      .trim()                         // Trim whitespace
      .toLowerCase()                  // Convert to lowercase
      .replace(/\.$/, '');            // Remove trailing dot if it exists
  };

  // Remove quotes and calculate the longest line for font size
  const calculateFontSize = (text, baseCoefficient, minSize = 1.5) => {
    // Remove leading and trailing quotes
    const trimmedText = text.trim();

    // Split text by '\n' and find the longest line
    const lines = trimmedText.split('\n');
    const longestLineLength = Math.max(...lines.map(line => removeQuotes(line).length));

    // Calculate font size based on the longest line length
    const fontSize = Math.max(baseCoefficient / (Math.pow(longestLineLength, 0.65)), minSize); // Ensure the font size doesn't go too small
    return `${fontSize}rem`;
  };

  return (

    <div className="mini-word-card">
      {loadingWord ? '⏳' :
        <>
          <div className="mini-word-card-word">
          <span style={{ fontSize: calculateFontSize(word.word, 1.3, 0.7) }}>
            {word.word}
            </span>
            </div>
          <div className="mini-word-card-def1">
            <span style={{ fontSize: calculateFontSize(word.def1, 1.3, 0.5) }}>
              <PinyinText text={word.def1} />
            </span>
          </div>
        </>
      }
    </div>
  );
};

export default MiniWordCard;
