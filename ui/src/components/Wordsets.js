// src/components/Wordsets.js
import React, { useState, useEffect } from 'react';
import { getWordsets } from '../services/wordsService'; // Assuming getWordsets is implemented in wordsService.js
import { useNavigate } from 'react-router-dom';
import '../styles/Wordsets.css'; // Create a CSS file for styling the wordsets grid

const Wordsets = () => {
  const [wordsets, setWordsets] = useState([]);  // Initialize as empty array
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);  // Track errors if fetching fails
  const navigate = useNavigate();

  useEffect(() => {
    // Fetch all wordsets when the component is mounted
    getWordsets()
      .then((response) => {
        if (response && Array.isArray(response.data)) {
          setWordsets(response.data);  // Access the data property
        } else {
          setWordsets([]);  // Fallback to empty array if data is not an array
          console.error("Expected array but got:", response);
        }
      })
      .catch(error => {
        console.error('Error fetching wordsets:', error);
        setWordsets([]);  // Handle the error case by setting it to an empty array
      })
      .finally(() => setLoading(false));
  }, []);

  const handleWordsetClick = (wordsetId, showExcluded = false) => {
    // Navigate to the game route with the wordsetId and whether to show excluded words
    navigate(`/game/${wordsetId}`, { state: { showExcluded } });
  };

  return (
    <div className="wordsets-container">
      <div className="wordsets-grid">
        {wordsets.length > 0 ? (
          wordsets.map(wordset => (
            <div key={wordset.wordset_id} className="wordset-tile">
              <div className="wordset-button-group">
                {/* Main button to load included words */}
                <button 
                  className="wordset-button" 
                  onClick={() => handleWordsetClick(wordset.wordset_id)}
                >
                  <h3>{wordset.description}</h3>
                </button>

                {/* New button to load excluded words */}
                <button 
                  className="show-excluded-button" 
                  onClick={() => handleWordsetClick(wordset.wordset_id, true)}
                >
                  Show Excluded
                </button>
              </div>
            </div>
          ))
        ) : (
          <p>No wordsets available.</p>
        )}
      </div>
    </div>
  );
};

export default Wordsets;
