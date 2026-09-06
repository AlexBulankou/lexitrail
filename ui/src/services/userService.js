import { getData, postData, putData, deleteData, callMiddleLayer } from './apiService';

// Create a new user
export const createUser = async (email) => {
  const data = { email };
  return await postData('/users', data);
};

// lexitrail#182: getAllUsers removed with the GET /users collection route
// it called -- that route leaked every member's email to any guest token, and
// this helper had zero call sites.

// Get a user by email
export const getUserByEmail = async (email) => {
  return await getData(`/users/${email}`);
};

// Update a user's email
export const updateUserEmail = async (email, newEmail) => {
  const data = { email: newEmail };
  return await putData(`/users/${email}`, data);
};

// Delete a user
export const deleteUser = async (email) => {
  return await deleteData(`/users/${email}`);
};

// Migrate a guest/demo session's progress onto the authenticated member.
// The target is the authenticated caller; only the source demo email is passed.
export const migrateUser = async (fromEmail) => {
  const data = { from_email: fromEmail };
  return await postData('/users/migrate', data);
};

// Fetch userwords for a given user and wordset
export const getUserWordsByWordset = async (userId, wordsetId) => {
  return await getData(`/userwords/query?user_id=${userId}&wordset_id=${wordsetId}`);
};

// issue-384: the Today home's per-wordset due COUNTS, in one request.
//
// `getUserWordsByWordset` above answers "which words", and the Today home only
// ever needed "how many". Asking the row question seven times (once per
// wordset, concurrently) downloaded ~5,600 words with their recall history to
// render seven integers: measured 10s+, then an outright failure, because the
// screen is a `Promise.all` and one slow set fails all of them.
//
// This response does not grow with the size of a wordset, so the screen cannot
// regress into that shape again as the sets grow. Wordsets with nothing due are
// ABSENT from the response rather than present with 0 — the caller defaults.
export const getDueCounts = async (userId) => {
  return await getData(`/userwords/due-counts?user_id=${userId}`);
};

// Update recall state for a word
// `inclusionOnly` (#111): this call changes inclusion and is NOT a recall
// event, so the backend must not append a RecallHistory row for it. Defaults
// false, so every existing caller is unchanged.
//
// The flag travels in the body, which `callMiddleLayer` forwards verbatim
// (`axios.post(url, data)`), so it survives that path too. A backend that
// predates the flag ignores it and behaves exactly as today — i.e. the
// old-server case degrades to the current bug, never to something worse.
export const updateUserWordRecall = async (userId, wordId, recallState, recall, isIncluded, inclusionOnly = false, provenance = null) => {
  const data = { recall_state: recallState, recall, is_included: isIncluded };
  if (inclusionOnly) data.inclusion_only = true;
  // #109 (RD-6): declare HOW this recall was produced, so a bulk "to all" tap
  // is distinguishable from a genuine per-card answer. Omitted rather than
  // defaulted: the server reads an absent flag as UNKNOWN, and a caller that
  // has not been taught the difference must not claim "single".
  // Both transports forward the body verbatim (putData; callMiddleLayer ->
  // middle_layer/app.py `requests.put(json=data)`), so the field survives
  // either path -- checked, because a field that silently vanishes in transit
  // is the expensive failure here.
  if (provenance) data.provenance = provenance;
  if (window.config.MIDDLE_LAYER_ADDRESS === undefined) {
    // If the middle layer is not ready, fall back to call backend directly
    return await putData(`/userwords/${userId}/${wordId}/recall`, data);
  } else {
    // Call the middle layer so the user's recall state can be updated aysnchronously
    return await callMiddleLayer(window.config.MIDDLE_LAYER_ADDRESS, `/userwords/${userId}/${wordId}/recall`, data);
  }
};
