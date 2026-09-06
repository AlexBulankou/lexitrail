import React from 'react';
import { BrowserRouter as Router, Route, Routes, Navigate } from "react-router-dom";
import {Game} from './components/Game';
import Profile from './components/Profile.js';
import PrivateRoute from './components/PrivateRoute.js';
import NavBar from './components/NavBar.js';
import Wordsets from './components/Wordsets';
import SessionSize from './components/SessionSize';
import PrivacyPolicy from './components/PrivacyPolicy.js';
import TermsOfService from './components/TermsOfService.js';
import './styles/Global.css';
import './styles/App.css';
import './styles/NavBar.css';
import './styles/Policy.css';
import './styles/Home.css';
import Home from './components/Home';
import { AuthProvider } from './contexts/AuthContext';
import About from './components/About';
import NotFound from './components/NotFound';

const App = () => {
  return (
    <AuthProvider>
      <Router>
        <div className="app-container">
          <NavBar />
          <div className="content-container">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route
                path="/wordsets/*"
                element={
                  <PrivateRoute >
                    <div className="page-wrapper">
                      <Wordsets />
                    </div>
                  </PrivateRoute>
                }
              />
              {/* revamp-2026-09: the "How many words?" step. Wordsets sends PRACTICE and
                  DUE_TODAY here; the pick lands on /game/:id/:mode?n=… */}
              <Route path="/session/:wordsetId/:mode?" element={
                <PrivateRoute>
                  <SessionSize />
                </PrivateRoute>
              } />
              <Route path="/game/:wordsetId/:mode?" element={
                <PrivateRoute>
                  <Game />
                </PrivateRoute>
              } />
              <Route path="/game" element={<Navigate to="/wordsets" />} />
              <Route path="/privacy" element={<PrivacyPolicy />} />
              <Route path="/terms" element={<TermsOfService />} />
              <Route path="/about" element={<About />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </div>
        </div>
      </Router>
    </AuthProvider>
  );
};

export default App;
