// lexitrail#195: the signup funnel is unmeasurable without an auth-success
// signal. This wraps `window.gtag` so a blocked or not-yet-loaded analytics
// script (common: ad-blockers frequently block gtag.js on auth-adjacent
// pages) cannot throw INSIDE the auth flow -- the existing call sites in
// PrivateRoute/NavBar call `window.gtag` unguarded, which is fine for a
// click-tracking event that fires before anything load-bearing happens, but
// the callers of this helper fire AFTER a real sign-in/sign-up succeeded, so
// a missing gtag must never be mistaken for (or cause) a failed auth.
export const trackEvent = (name, params) => {
  try {
    if (typeof window.gtag === 'function') {
      window.gtag('event', name, params);
    }
  } catch (_) {
    // Analytics is best-effort; a broken/blocked gtag must never surface as
    // an auth failure to the user or to the calling flow's own error handling.
  }
};
