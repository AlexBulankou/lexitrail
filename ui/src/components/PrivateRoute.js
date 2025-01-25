import { useAuth } from '../contexts/AuthContext';
import '../styles/PrivateRoute.css';
import googleIcon from '../styles/assets/google-icon.svg';

const PrivateRoute = ({children}) => {
  const { user, login, tryWithoutSignin } = useAuth();

  const handleTryWithoutSignin = async () => {
    await tryWithoutSignin();
    // Stay on current page, component will re-render with user
  };

  const handleLogin = async () => {
    await login();
    // Stay on current page, component will re-render with user
  };

  // This will re-render when user changes
  if (!user) {
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

          <div className="auth-buttons">
            <button onClick={handleLogin} className="google-signin-button">
              <img src={googleIcon} alt="" className="google-icon" />
              <span>Sign in with Google to get started</span>
            </button>
            <button onClick={handleTryWithoutSignin} className="try-without-signin">
              Try without signing in
            </button>
          </div>
        </div>
      </div>
    );
  }

  return children;
};

export default PrivateRoute;