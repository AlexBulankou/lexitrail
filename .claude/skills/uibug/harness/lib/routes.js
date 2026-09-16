'use strict';
/**
 * The sweep's route list. Ordered so that public routes are measured before we
 * spend a guest session, and so a BLIND on an authed route still leaves the
 * public findings usable.
 *
 * `auth: true` means PrivateRoute gates it -- the sweep enters a guest session
 * before these and will report BLIND rather than screenshot a login card and
 * call it the practice screen.
 */
const ROUTES = [
  { slug: 'home',          path: '/',                   auth: false, wait: '.wordset-container, .home-container, main' },
  { slug: 'about',         path: '/about',              auth: false },
  { slug: 'privacy',       path: '/privacy',            auth: false },
  { slug: 'terms',         path: '/terms',              auth: false },
  { slug: 'notfound',      path: '/does-not-exist-uibug', auth: false },
  { slug: 'login-wall',    path: '/wordsets',           auth: false, note: 'pre-auth: renders the PrivateRoute login card' },
  { slug: 'wordsets',      path: '/wordsets',           auth: true,  wait: '.wordset-container, .wordsets-grid' },
  { slug: 'practice',      path: '/game/1/PRACTICE',    auth: true,  wait: '.card, .word-card, .cards-area' },
  { slug: 'test',          path: '/game/1/TEST',        auth: true,  wait: '.card, .word-card, .cards-area' },
  { slug: 'due-today',     path: '/game/1/DUE_TODAY',   auth: true,  wait: '.card, .word-card, .cards-area, .completed-container' },
  { slug: 'show-excluded', path: '/game/1/SHOW_EXCLUDED', auth: true, wait: '.cards-area, .empty-state, .completed-container' },
];

/** The two form factors. `env` on the CLI selects one or both. */
const VIEWPORTS = {
  desktop: { name: 'desktop', width: 1440, height: 900, isMobile: false, hasTouch: false },
  mobile:  { name: 'mobile',  width: 390,  height: 844, isMobile: true,  hasTouch: true,
             deviceScaleFactor: 3,
             userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1' },
};

module.exports = { ROUTES, VIEWPORTS };
