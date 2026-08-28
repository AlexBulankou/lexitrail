import React from 'react';
import { Link } from 'react-router-dom';
import '../styles/Home.css';
import Logo from './Logo';
import WordSets from './Wordsets';
import Today from './Today';
import { useAuth } from '../contexts/AuthContext';
import { SEO } from '../components/SEO';
import { JsonLd } from '../components/JsonLd';
import { OptimizedImage } from '../components/OptimizedImage';

const Home = () => {
  const { user } = useAuth();
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
      
      {/* issue-107 (RD-3): signed in, `/` is the Today home — the day's due
          count, the streak, one Start. Signed out it stays the marketing page
          below, unchanged.

          Branching HERE rather than adding a `/today` route, on purpose: the
          habit surface has to be what the app OPENS on. A separate route makes
          Today a place you can navigate to, which is what the wordset list
          already was, and leaves `/` still answering with a list.

          The SEO tag and structured data stay outside the branch: crawlers are
          signed out, so they keep getting the marketing description either way,
          and this cannot regress the landing page's indexing. */}
      {user ? (
        <div className="page-wrapper">
          <div className="page-container">
            <Today userId={user.email} />
          </div>
        </div>
      ) : (
      <div className="page-wrapper">
        <div className="page-container">
          <div className="centered-content">
            <div className="hero-section">
              <Logo size="large" />
              <h1>Welcome to Lexitrail</h1>
              <h2>Master Chinese Vocabulary Through Smart Learning</h2>
              <p>Lexitrail is your AI-powered companion for mastering Mandarin Chinese vocabulary. Perfect for beginners to advanced learners looking to expand their Chinese word knowledge.</p>
              {/* issue-194: an above-the-fold CTA + one-line SRS value prop.
                  Previously the first CTA was the one at the page bottom, past
                  the wordset grid and the features section -- ~4.5 viewport
                  heights down on mobile (measured ~3630px at 390x844), with
                  nothing above the fold stating what spaced repetition buys a
                  visitor. This one is deliberately a SECOND `.cta-button` to
                  the same `/wordsets` destination, not a replacement for the
                  bottom one -- a long scroller still gets a CTA where they
                  stop. */}
              <div className="hero-cta">
                <p className="hero-value-prop">
                  Spaced repetition shows you each word right before you'd
                  forget it, so review time goes to the words you actually
                  need — not a fixed daily list.
                </p>
                <Link to="/wordsets" className="cta-button" data-cta="hero">Start Learning Chinese</Link>
              </div>
            </div>
            <WordSets />
            
            <div className="features-section">
              <div className="features-grid">
                <div className="feature-card">
                  <h3>智能 Smart Word Sets</h3>
                  {/* lexitrail#191: was "Create and organize ...". Same nonexistent
                      create-wordset feature as the login card claimed -- the issue named
                      only the card, and fixing one surface of a claim while its sibling
                      keeps making it is how a "fixed" issue stays true on the site. */}
                  <p>Study curated HSK 1-6 vocabulary lists with Pinyin, characters, and English translations. More languages coming soon!</p>
                </div>
                <div className="feature-card">
                  <h3>AI Memory Hints</h3>
                  <p>Our AI generates clever memory aids and etymology explanations for Chinese characters, making them stick in your memory naturally.</p>
                </div>
                <div className="feature-card">
                  <h3>Interactive Practice</h3>
                  <p>Test your knowledge with character recognition, pronunciation, and meaning exercises. Track your progress with spaced repetition.</p>
                </div>
                {/* lexitrail#191: the "Cultural Context" card is REMOVED, not reworded.
                    It promised "example sentences and usage notes"; #118 deliberately removed
                    the sentences view and never touched the marketing copy. The ~450 curated
                    sentences are still served by the API and rendered nowhere (#192).
                    Rewording it to describe the AI hints would have been true but would have
                    made it a second card about the feature the card above already sells.
                    RESTORE THIS with #192, copy and all -- it becomes accurate the moment a
                    sentence surface ships. */}
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
              <Link to="/wordsets" className="cta-button" data-cta="footer">Start Learning Chinese</Link>
            </div>
          </div>
        </div>
      </div>
      )}
    </>
  );
};

export default Home;