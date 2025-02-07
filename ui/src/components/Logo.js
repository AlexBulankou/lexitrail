import React from 'react';
import { OptimizedImage } from './OptimizedImage';

// Replace the existing SVG logo with the new image logo
const Logo = ({ size = 'medium' }) => {
  const sizes = {
    small: '32px',
    medium: '48px',
    large: '64px'
  };
  
  return (
    <OptimizedImage 
      src="/images/brand/logo-symbol.png"
      alt="Lexitrail"
      width={parseInt(sizes[size])}
      height={parseInt(sizes[size])}
      priority={true}
      className="logo"
      style={{ objectFit: 'contain' }}
    />
  );
};

export default Logo;