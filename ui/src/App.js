import React from 'react';
import { BrowserRouter as Router, Route, Routes, Navigate } from "react-router-dom";
import {Game} from './components/Game';
import Profile from './components/Profile.js';
import PrivateRoute from './components/PrivateRoute.js';
import NavBar from './components/NavBar.js';
import { useAuth } from './hooks/useAuth';
import Wordsets from './components/Wordsets';
import PrivacyPolicy from './components/PrivacyPolicy.js';
import TermsOfService from './components/TermsOfService.js';
import './styles/Global.css';
import './styles/App.css';
import './styles/NavBar.css';
import './styles/Policy.css';
import Home from './components/Home';

const App = () => {
  const { user, login, logOut } = useAuth();

  return (
    <Router>
      <div className="app-container">
        <NavBar user={user} login={login} logOut={logOut} />
        <div className="content-container">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/profile" element={
              <PrivateRoute profileDetails={user} login={login} logOut={logOut}>
                <Profile profileDetails={user} />
              </PrivateRoute>
            } />
            <Route
              path="/wordsets/*"
              element={
                <PrivateRoute profileDetails={user} login={login} logOut={logOut}>
                  <Wordsets />
                </PrivateRoute>
              }
            />
            <Route path="/game/:wordsetId/:mode?" element={
              <PrivateRoute profileDetails={user} login={login} logOut={logOut}>
                <Game />
              </PrivateRoute>
            } />
            <Route path="/game" element={<Navigate to="/wordsets" />} />
            <Route path="/privacy" element={<PrivacyPolicy />} />
            <Route path="/terms" element={<TermsOfService />} />
          </Routes>
        </div>
      </div>
    </Router>
  );
};

export default App;
