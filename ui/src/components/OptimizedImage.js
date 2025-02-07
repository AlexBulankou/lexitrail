import React from 'react';

export const OptimizedImage = ({
  src,
  alt,
  width,
  height,
  className,
  priority = false
}) => {
  return (
    <img
      src={src}
      alt={alt}
      width={width}
      height={height}
      loading={priority ? 'eager' : 'lazy'}
      className={className}
    />
  );
}; 