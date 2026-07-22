import React, { useState, useEffect } from 'react';
import { getExamples } from '../services/sentencesService';
import '../styles/ExampleSentences.css';

// FEAT-9 (ITP #21): show up to two curated example sentences for the current
// word, each with chinese + pinyin + english and a pronunciation control.
// Renders nothing when the word has no sentences (most cards on a full set),
// so it never leaves an empty heading.
const ExampleSentences = ({ word, limit = 2 }) => {
  const [examples, setExamples] = useState([]);

  useEffect(() => {
    let active = true;
    const chinese = (word || '').trim();
    if (!chinese) {
      setExamples([]);
      return undefined;
    }
    getExamples(chinese, limit)
      .then((rows) => { if (active) setExamples(rows); })
      .catch(() => { if (active) setExamples([]); });
    return () => { active = false; };
  }, [word, limit]);

  if (!examples.length) return null;

  return (
    <div className="example-sentences" onClick={(e) => e.stopPropagation()}>
      <div className="example-sentences-heading">Example sentences</div>
      <ul className="example-sentences-list">
        {examples.map((ex, i) => (
          <li key={i} className="example-sentence">
            <div className="example-zh-row">
              <span lang="zh" className="example-zh">{ex.zh}</span>
            </div>
            {ex.py && <div className="example-py">{ex.py}</div>}
            {ex.en && <div className="example-en">{ex.en}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default ExampleSentences;
