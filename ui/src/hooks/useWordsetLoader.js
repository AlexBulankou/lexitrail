import { useState, useEffect, useCallback } from 'react';
import { getWordsByWordset } from '../services/wordsService';

export const useWordsetLoader = (wordsetId) => {
  const [toShow, setToShow] = useState([]);
  const [loading, setLoading] = useState(true);
  const [firstTimeCorrect, setFirstTimeCorrect] = useState([]);
  const [incorrectAttempts, setIncorrectAttempts] = useState({});
  const [correctlyMemorized, setCorrectlyMemorized] = useState(new Set());
  const [timeElapsed, setTimeElapsed] = useState(0);
  
  const loadWordsForWordset = useCallback(() => {
    setLoading(true);
    getWordsByWordset(wordsetId)
      .then((response) => {
        const loadedWords = response.data;  // Assuming your API response includes { data: [...] }
        const convertedWords = loadedWords.map((word) => ({
          word: word.word,
          meaning: `${word.def1}\n${word.def2}`,  // Combine def1 and def2 as meaning
          word_id: word.word_id,
          wordset_id: word.wordset_id,
        }));
        setToShow(convertedWords);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [wordsetId]);

  useEffect(() => {
    if (wordsetId) {
      loadWordsForWordset();
    }
  }, [loadWordsForWordset, wordsetId]);

  const handleMemorized = (index, maxWordsToShow) => {
    const currentWord = toShow[index];
    
    if (!incorrectAttempts[currentWord.word]) {
      setFirstTimeCorrect([...firstTimeCorrect, currentWord]);
    }

    setCorrectlyMemorized(prevSet => new Set(prevSet.add(currentWord.word)));
    const filteredToShow = toShow.filter((_, i) => i !== index);
    
    const availableIndexes = filteredToShow.length > maxWordsToShow ?
      filteredToShow.slice(maxWordsToShow) : filteredToShow;
    const randomWordIndex = availableIndexes.length > 0 ?
      Math.floor(Math.random() * availableIndexes.length) + maxWordsToShow :
      filteredToShow.length - 1;

    const newWord = filteredToShow[randomWordIndex];
    filteredToShow.splice(randomWordIndex, 1);
    filteredToShow.splice(index, 0, newWord);

    setToShow(filteredToShow);
  };

  const handleNotMemorized = (index, maxWordsToShow) => {
    const currentWord = toShow[index];
    
    setIncorrectAttempts(prev => ({
      ...prev,
      [currentWord.word]: (prev[currentWord.word] || 0) + 1,
    }));

    const availableIndexes = toShow.length > maxWordsToShow ?
      toShow.slice(maxWordsToShow) : toShow;
    const randomIndex = availableIndexes.length > 0 ?
      Math.floor(Math.random() * availableIndexes.length) + maxWordsToShow : index;

    const newToShow = [...toShow];
    [newToShow[index], newToShow[randomIndex]] = [newToShow[randomIndex], newToShow[index]];
    
    setToShow(newToShow);
  };

  useEffect(() => {
    if (!loading) {
      const timer = setInterval(() => setTimeElapsed(prev => prev + 1), 1000);
      if (toShow.length === 0) {
        clearInterval(timer);
      }
      return () => clearInterval(timer);
    }
  }, [toShow.length, loading]);

  return {
    toShow,
    loading,
    firstTimeCorrect,
    incorrectAttempts,
    correctlyMemorized,
    timeElapsed,
    loadWordsForWordset,
    handleMemorized,
    handleNotMemorized,
  };
};
