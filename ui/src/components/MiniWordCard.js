import React, { useState, useEffect } from 'react';
// import { GameMode } from './Game'; // GameMode is not used
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

  const handleSpeakChinese = (text) => {
    if ('speechSynthesis' in window) {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'zh-CN'; // Set language to Mandarin Chinese
      window.speechSynthesis.speak(utterance);
    } else {
      console.error('Speech synthesis not supported in this browser.');
      // Optionally, display a message to the user
    }
  };

  const stopPropagation = (e) => {
    e.stopPropagation();
  };

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
          <div className="mini-word-card-word"> {/* Inline style removed */}
            <span style={{ fontSize: calculateFontSize(word.word, 3.2, 0.7), marginRight: '5px' }}>
              {word.word}
            </span>
            <button
              onClick={(e) => {
                stopPropagation(e);
                handleSpeakChinese(word.word);
              }}
              disabled={loadingWord}
              className="speak-button-mini" // Inline style removed
            >
              🔊
            </button>
          </div>
          <div className="mini-word-card-def1">
            <span style={{ fontSize: calculateFontSize(word.def1, 3.5, 0.5) }}>
              <PinyinText text={word.def1} />
            </span>
          </div>
        </>
      }
    </div>
  );
};

export default MiniWordCard;
