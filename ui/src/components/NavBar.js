import React, { useState, useRef, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import Logo from './Logo';
import '../styles/NavBar.css';
import googleGIcon from '../styles/assets/google-g.svg';
import { useAuth } from '../contexts/AuthContext';

const NavBar = () => {
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [legalMenuOpen, setLegalMenuOpen] = useState(false);
  const userDropdownRef = useRef(null);
  const legalDropdownRef = useRef(null);
  const location = useLocation();
  const navigate = useNavigate();
  const { user, login, logOut, tryWithoutSignin } = useAuth();

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (userDropdownRef.current && !userDropdownRef.current.contains(event.target)) {
        setUserMenuOpen(false);
      }
      if (legalDropdownRef.current && !legalDropdownRef.current.contains(event.target)) {
        setLegalMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogin = () => {
    login();
    if (!location.pathname.startsWith('/game')) {
      navigate('/wordsets');
    }
  };

  const handleLogout = () => {
    logOut();
    setUserMenuOpen(false);
    navigate('/');
  };

  const isActive = (path) => {
    // Don't highlight anything on game pages
    if (location.pathname.startsWith('/game')) {
      return false;
    }
    return location.pathname === path;
  };

  return (
    <nav className="navbar">
      <div className="nav-left">
        <Link to="/" className="nav-logo">
          <Logo size="small" />
          <span className="logo-text">Lexitrail</span>
        </Link>
      </div>
      <div className="nav-center">
        {user && (
          <Link 
            to="/wordsets" 
            className={location.pathname === '/wordsets' ? 'nav-link-active' : ''}
          >
            Word Sets
          </Link>
        )}
      </div>
      <div className="nav-right">
        {/* Legal Dropdown */}
        <div className="dropdown" ref={legalDropdownRef}>
          <button 
            className="dropdown-trigger"
            onClick={() => setLegalMenuOpen(!legalMenuOpen)}
          >
            Privacy
            <span className="dropdown-arrow">▼</span>
          </button>
          {legalMenuOpen && (
            <div className="dropdown-menu">
              <Link to="/privacy" className="dropdown-item" onClick={() => setLegalMenuOpen(false)}>
                Privacy Policy
              </Link>
              <Link to="/terms" className="dropdown-item" onClick={() => setLegalMenuOpen(false)}>
                Terms of Service
              </Link>
            </div>
          )}
        </div>

        {/* User Menu */}
        {user ? (
          <div className="dropdown" ref={userDropdownRef}>
            <button 
              className="dropdown-trigger user-dropdown-trigger"
              onClick={() => setUserMenuOpen(!userMenuOpen)}
            >
              <img src={user.picture} alt="" className="user-avatar" />
              <div className="user-info-compact">
                <span className="name">{user.name}</span>
                <span className="email">{user.email}</span>
              </div>
            </button>
            {userMenuOpen && (
              <div className="dropdown-menu">
                <div 
                  className="dropdown-item" 
                  onClick={handleLogout}
                >
                  Log Out
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="auth-buttons">
            <button onClick={tryWithoutSignin} className="try-button">
              Try
            </button>
            <button onClick={login} className="google-signin-compact">
              <img src={googleGIcon} alt="" />
              Sign in
            </button>
          </div>
        )}
      </div>
    </nav>
  );
};

export default NavBar;
