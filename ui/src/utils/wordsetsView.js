// lexitrail#52 bug 6: decide which view the wordset picker should render.
//
// The Wordsets component previously showed "Loading wordsets…" whenever the
// list was empty (`wordsets.length > 0 ? grid : loading`), ignoring the actual
// fetch status. So a failed request (which also emptied the list) or a slow /
// hung request both showed "Loading…" indefinitely — the multi-minute hang Alex
// hit on his 07-23 pass. This maps the real (status, hasItems) pair to a view
// so an error surfaces as a retryable error and a genuinely empty result says
// so, instead of a spinner that never ends.
//
// hasItems is preferred first: if we already have (possibly cached) wordsets to
// show, keep showing them even while a background refresh is loading or has
// failed — the user is never interrupted by a loading/error state once there is
// something on screen.
export const resolveWordsetsView = (status, hasItems) => {
  if (hasItems) return 'grid';
  if (status === 'loading') return 'loading';
  if (status === 'error') return 'error';
  return 'empty';
};
