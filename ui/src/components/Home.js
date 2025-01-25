import React from 'react';
import { Link } from 'react-router-dom';
import '../styles/Home.css';
import Logo from './Logo';

const Home = () => {
  return (
    <div className="page-wrapper">
      <div className="page-container">
        <div className="centered-content">
          <div className="hero-section">
            <Logo size="large" />
            <h1>Welcome to Lexitrail</h1>
          </div>
          <div className="intro-section">
            <h2>Master Chinese Vocabulary Through Smart Learning</h2>
            <p>Lexitrail is your AI-powered companion for mastering Mandarin Chinese vocabulary. Perfect for beginners to advanced learners looking to expand their Chinese word knowledge.</p>
            <Link to="/wordsets" className="cta-button">Start Learning Chinese</Link>
          </div>
          
          <div className="features-section">
            <div className="features-grid">
              <div className="feature-card">
                <h3>智能 Smart Word Sets</h3>
                <p>Create and organize Chinese vocabulary lists with Pinyin, characters, and English translations. More languages coming soon!</p>
              </div>
              <div className="feature-card">
                <h3>AI Memory Hints</h3>
                <p>Our AI generates clever memory aids and etymology explanations for Chinese characters, making them stick in your memory naturally.</p>
              </div>
              <div className="feature-card">
                <h3>Interactive Practice</h3>
                <p>Test your knowledge with character recognition, pronunciation, and meaning exercises. Track your progress with spaced repetition.</p>
              </div>
              <div className="feature-card">
                <h3>Cultural Context</h3>
                <p>Learn how words are actually used in Chinese culture with example sentences and usage notes.</p>
              </div>
            </div>
          </div>

          <div className="game-preview">
            <h3>Learn Through Interactive Flashcards</h3>
            <div className="cards-demo">
              <div className="flashcard">
                <div className="card-content">
                  <div className="chinese-word">护照</div>
                  <div className="pinyin">hù zhào</div>
                  <div className="english">passport</div>
                  <div className="card-controls">
                    <button className="wrong-btn">✕</button>
                    <button className="right-btn">✓</button>
                  </div>
                </div>
              </div>

              <div className="flashcard flipped">
                <div className="card-content">
                  <div className="chinese-word">公园</div>
                  <div className="pinyin">gōng yuán</div>
                  <div className="english">park</div>
                  <div className="card-controls">
                    <button className="wrong-btn">✕</button>
                    <button className="right-btn">✓</button>
                  </div>
                </div>
              </div>

              <div className="game-stats">
                <div className="timer">0:35</div>
                <div className="score">
                  <span className="wrong">✕ 1</span>
                  <span className="right">✓ 0</span>
                </div>
              </div>
            </div>
            <div className="game-controls-demo">
              <button className="control-btn">Hide Hints</button>
              <button className="control-btn">Flip all</button>
              <button className="control-btn">Show Excluded</button>
            </div>
          </div>

          <div className="learning-example">
            <h3>See How It Works</h3>
            <div className="example-card">
              <div className="word-example">
                <span className="chinese-char">记忆</span>
                <span className="pinyin">jì yì</span>
                <span className="meaning">memory</span>
              </div>
              <p className="ai-hint">AI Hint: Think of 记 (jì) as a "speech" 讠with "self" 己 - speaking to yourself to remember something. 
              忆 (yì) shows a "heart" 心 - memories come from the heart!</p>
            </div>
          </div>

          <div className="future-features">
            <h3>Coming Soon</h3>
            <p>While we're starting with Mandarin Chinese, we're expanding to include more languages in the future. Join us on this learning journey!</p>
          </div>

          <div className="cta-section">
            <Link to="/wordsets" className="cta-button">Start Learning Chinese</Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Home;