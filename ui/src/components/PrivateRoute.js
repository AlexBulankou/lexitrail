import React from 'react';
import '../styles/PrivateRoute.css';
import googleIcon from '../styles/assets/google-icon.svg';

const PrivateRoute = ({ children, profileDetails, login }) => {
  if (!profileDetails) {
    return (
      <div className="private-login-container">
        <div className="login-card">
          <h2>Explore Word Sets</h2>
          <p>Log in to create and practice with custom vocabulary sets for Chinese language learning.</p>
          <div className="features-list">
            <div className="feature-item">HSK-based wordsets</div>
            <div className="feature-item">Track your learning progress</div>
            <div className="feature-item">Get AI-powered memory hints</div>
          </div>
          <button 
            onClick={login} 
            className="google-signin-button"
          >
            <img 
              src={googleIcon} 
              alt="" 
              className="google-icon"
            />
            <span>Sign in with Google to get started</span>
          </button>
        </div>
      </div>
    );
  }

  return children;
};

export default PrivateRoute;
