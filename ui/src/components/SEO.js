import React from 'react';
import { Helmet } from 'react-helmet';

export const SEO = ({ 
  title = 'Lexitrail - Smart Chinese Learning',
  description = 'Master Chinese vocabulary with AI-powered learning tools, interactive flashcards, and personalized study paths.',
  image = '/images/og/hsk2-practice.png',
  path = ''
}) => {
  const baseUrl = 'https://lexitrail.com';
  const fullUrl = `${baseUrl}${path}`;
  const fullImage = `${baseUrl}${image}`;

  return (
    <Helmet>
      <title>{title}</title>
      <meta name="description" content={description} />
      
      {/* Open Graph */}
      <meta property="og:title" content={title} />
      <meta property="og:description" content={description} />
      <meta property="og:image" content={fullImage} />
      <meta property="og:url" content={fullUrl} />
      <meta property="og:type" content="website" />
      
      {/* Twitter */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={title} />
      <meta name="twitter:description" content={description} />
      <meta name="twitter:image" content={fullImage} />
      
      {/* Additional SEO */}
      <link rel="canonical" href={fullUrl} />
      <meta name="keywords" content="Chinese learning, vocabulary app, Mandarin Chinese, HSK, flashcards, spaced repetition" />
    </Helmet>
  );
};
