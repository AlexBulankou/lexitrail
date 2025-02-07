import { useEffect } from 'react';

export const useSEO = ({ title, description, image }) => {
  useEffect(() => {
    if (title) {
      document.title = title;
    }
    if (description) {
      document
        .querySelector('meta[name="description"]')
        ?.setAttribute('content', description);
    }
    if (image) {
      document
        .querySelector('meta[property="og:image"]')
        ?.setAttribute('content', image);
    }
  }, [title, description, image]);
}; 