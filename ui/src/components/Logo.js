import React from 'react';

// Replace the existing SVG logo with the new image logo
const Logo = ({ size = 'medium' }) => {
  const sizes = {
    small: '32px',
    medium: '48px',
    large: '64px'
  };
  
  return (
    <img 
      src="/images/brand/logo-symbol.png" 
      alt="Lexitrail" 
      style={{ 
        width: sizes[size], 
        height: sizes[size],
        objectFit: 'contain'
      }}
    />
  );
};

export default Logo;