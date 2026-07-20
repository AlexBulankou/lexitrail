import React from 'react';
import { Link } from 'react-router-dom';

const NotFound = () => {
  return (
    <div className="page-wrapper">
      <div className="not-found" style={{ textAlign: 'center', padding: '64px 16px' }}>
        <h1 style={{ fontSize: '48px', margin: '0 0 8px' }}>404</h1>
        <p style={{ fontSize: '18px', margin: '0 0 24px' }}>
          We couldn&rsquo;t find that page.
        </p>
        <Link to="/" className="home-link">Back to home</Link>
      </div>
    </div>
  );
};

export default NotFound;
