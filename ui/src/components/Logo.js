import React from 'react';

const Logo = ({ width = 32, height = 32, color = "currentColor" }) => {
  return (
    <svg 
      width={width} 
      height={height} 
      viewBox="0 0 32 32" 
      fill="none" 
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Stylized "L" character that also resembles a Chinese stroke */}
      <path 
        d="M8 6v16h16" 
        stroke={color} 
        strokeWidth="2.5" 
        strokeLinecap="round"
      />
      {/* Dot representing the trail/journey */}
      <circle 
        cx="24" 
        cy="22" 
        r="2" 
        fill={color}
      />
      {/* Horizontal stroke representing a Chinese character element */}
      <path 
        d="M12 12h8" 
        stroke={color} 
        strokeWidth="2" 
        strokeLinecap="round"
      />
    </svg>
  );
};

export default Logo;