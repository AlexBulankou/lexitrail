import { getData } from './apiService';
import { markOnce, WORDSETS_REQUESTED_MARK } from '../utils/perfMark';

// issue-297: the one open `GET /wordsets`, shared by every concurrent caller.
// Module scope on purpose -- the callers are in different component trees and
// have no shared React context to hang this on.
let _wordsetsInFlight = null;

// Fetch all wordsets
export const getWordsets = async () => {
  
  // Connect to the match making server
  /*
  const ws = new WebSocket(window.config.MATCH_MAKER_ADDRESS);

  ws.onopen = () => {
    console.log('Connected to WebSocket server');
    ws.send(JSON.stringify({ action: 'hello server' })); 
  };

  ws.onmessage = (event) => {
    // The match making server sends back the address for the allocated middle layer server
    const data = JSON.parse(event.data);
    console.log('Received:', data);
    // Set the middle layer address so the ui client can send requests to it
    if (data.connection !== undefined && window.config.MIDDLE_LAYER_ADDRESS === undefined) {
      console.log('data.connection:', data.connection);
      window.config.MIDDLE_LAYER_ADDRESS = data.connection;
      console.log('MIDDLE_LAYER_ADDRESS:', window.config.MIDDLE_LAYER_ADDRESS);
    }
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
  };
  */

  // issue-266: BEFORE the await, not after. The mark bounds the phase
  // "how long until we ask", so it has to land when the request leaves --
  // marking after the await would fold the API's own response time into the
  // gap and make a slow backend read as a slow app.
  markOnce(WORDSETS_REQUESTED_MARK);
  // issue-297: SHARE the request while one is open. Two components call this --
  // `Wordsets.js` (the picker) and `useDueToday` (the Today home's fan-out) --
  // and neither knows about the other, so a journey issues the same GET more
  // than once. Measured: three per arrival, two of them on `/` before any
  // navigation.
  //
  // 🔴 IN-FLIGHT ONLY, NOT A TTL CACHE, and that boundary is the whole point.
  // Deduping concurrent callers costs nothing: they would each have received
  // the same bytes from the same open request anyway. A TTL would additionally
  // serve a STALE list, which is a trade -- and specifically it would weaken
  // lexitrail#52 bug 6, where `Wordsets.js` refreshes in the background on
  // revisit so the picker is never both instant and wrong. That decision is
  // #297's AC2 and is deliberately not taken here.
  if (!_wordsetsInFlight) {
    const pending = (async () => {
      const response = await getData('/wordsets');
      // Hide the internal "test" and "HSK7" wordsets. Trim first so the match is
      // robust to legacy rows whose descriptions carry a trailing CR from an
      // older CSV import (e.g. "HSK7\r").
      const HIDDEN_DESCRIPTIONS = new Set(['test', 'HSK7']);
      response.data = response.data.filter(
        wordset => !HIDDEN_DESCRIPTIONS.has((wordset.description || '').trim())
      );
      return response;
    })();
    _wordsetsInFlight = pending;
    // Clear on BOTH settle paths, or one failed request poisons every later
    // call. The identity check matters: without it a slow failure could clear
    // a NEWER in-flight request that started after it.
    pending
      .finally(() => { if (_wordsetsInFlight === pending) _wordsetsInFlight = null; })
      // The `finally` chain is a derived promise nothing else awaits, so a
      // rejection here would surface as an unhandled rejection even though
      // every real caller handles its own. Swallow it on the DERIVED promise
      // only -- `pending` itself is returned to callers unchanged.
      .catch(() => {});
  }
  const shared = await _wordsetsInFlight;
  // Hand each caller its OWN shallow copy. No caller mutates the list today
  // (both `.map` over it), but sharing one array across components makes a
  // future mutation in one silently corrupt the other -- a coupling this
  // change would have introduced for free, in a place nothing would look.
  return { ...shared, data: [...(shared.data || [])] };
};

// Fetch words for a given wordset
export const getWordsByWordset = async (wordsetId) => {
  return await getData(`/wordsets/${wordsetId}/words`);
};


