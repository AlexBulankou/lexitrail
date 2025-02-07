import { useAuth } from '../contexts/AuthContext';
import '../styles/PrivateRoute.css';
import googleIcon from '../styles/assets/google-icon.svg';

const PrivateRoute = ({children}) => {
  const { user, login, tryWithoutSignin } = useAuth();

  const handleTryWithoutSignin = async () => {
    // Track demo account attempt
    window.gtag('event', 'try_with_demo_account', {
      'event_category': 'authentication',
      'event_label': 'private_route'
    });
    
    await tryWithoutSignin();
    // Stay on current page, component will re-render with user
  };

  const handleLogin = async () => {
    // Track Google login click
    window.gtag('event', 'login_to_google_click', {
      'event_category': 'authentication',
      'event_label': 'private_route'
    });
    
    await login();
    // Stay on current page, component will re-render with user
  };

  // This will re-render when user changes
  if (!user) {
    return (
      <div className="private-login-container">
        <div className="login-card">
          <h2>Ready to Start Learning?</h2>
          <p>Sign in to save your progress and unlock personalized features for this word set.</p>
          <div className="features-list">
            <div className="feature-item">Track your learning progress</div>
            <div className="feature-item">Get AI-powered memory hints</div>
            <div className="feature-item">Create custom word sets</div>
          </div>

          <div className="auth-buttons">
            <button onClick={handleTryWithoutSignin} className="try-without-signin primary-button">
              Try without signing in
            </button>
            <button onClick={handleLogin} className="google-signin-button">
              <img src={googleIcon} alt="" className="google-icon" />
              <span>Sign in with Google</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  return children;
};

export default PrivateRoute;