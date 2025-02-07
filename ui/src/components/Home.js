import React from 'react';
import { Link } from 'react-router-dom';
import '../styles/Home.css';
import Logo from './Logo';
import WordSets from './Wordsets';
import { SEO } from '../components/SEO';
import { JsonLd } from '../components/JsonLd';
import { OptimizedImage } from '../components/OptimizedImage';

const Home = () => {
  const structuredData = {
    "@context": "https://schema.org",
    "@type": "WebApplication",
    "name": "Lexitrail",
    "description": "Smart Chinese Learning Platform",
    "applicationCategory": "EducationalApplication",
    "operatingSystem": "Any",
    "offers": {
      "@type": "Offer",
      "price": "0"
    }
  };

  return (
    <>
      <SEO 
        title="Lexitrail - Learn Chinese Smartly"
        description="Master Chinese vocabulary with AI-powered spaced repetition"
        path="/"
      />
      <JsonLd data={structuredData} />
      
      <div className="page-wrapper">
        <div className="page-container">
          <div className="centered-content">
            <div className="hero-section">
              <Logo size="large" />
              <h1>Welcome to Lexitrail</h1>
              <h2>Master Chinese Vocabulary Through Smart Learning</h2>
              <p>Lexitrail is your AI-powered companion for mastering Mandarin Chinese vocabulary. Perfect for beginners to advanced learners looking to expand their Chinese word knowledge.</p>
            </div>
            <WordSets />
            
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
                <div className="feature-card">
                  <h3>Character Breakdown</h3>
                  <p>
                    <span className="example-word">
                      <span className="chinese-char">记忆</span>
                      <span className="pinyin">jì yì</span>
                      <span className="meaning">memory</span>
                    </span>
                    Think of 记 (jì) as a "speech" 讠with "self" 己 - speaking to yourself to remember something. 
                    忆 (yì) shows a "heart" 心 - memories come from the heart!
                  </p>
                </div>
                <div className="feature-card">
                  <h3>Expanding Horizons</h3>
                  <p>Starting with Mandarin Chinese, we're building a platform that will soon support multiple languages. Join our growing community of language learners!</p>
                </div>
              </div>
            </div>

            <div className="cta-section">
              <Link to="/wordsets" className="cta-button">Start Learning Chinese</Link>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default Home;