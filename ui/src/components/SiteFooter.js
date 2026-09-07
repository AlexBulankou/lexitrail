import React from 'react';
import '../styles/SiteFooter.css';

// pigeon 2026-09-07: same strip the static pages carry via hskPages.js SITE_FOOTER — the
// support address is the site's one contact channel and must be visible on every public
// surface. Mounted PER PAGE (not in App.js): every public page is its own fixed-position
// scroll container, so an App-level footer would never be visible.
const SiteFooter = () => (
  <footer className="site-footer">
    <a href="mailto:support@lexitrail.com">Support: support@lexitrail.com</a>
    <span>© LexiTrail</span>
  </footer>
);

export default SiteFooter;
