/**
 * AC2 guard for lexitrail#63 — no capture-environment artifact may reach a
 * published creative.
 *
 * The replaced asset was a raw screenshot of a live practice session, so it
 * shipped a demo-account email, "recalled 0 out of 149", zeroed score counters
 * and a running timer into every impression. Those cannot recur by accident in
 * a composed asset, but "cannot recur by accident" is exactly the kind of claim
 * that rots the moment someone adds a data source. This module is the standing
 * check, and it runs as part of generation rather than as a separate step you
 * can forget.
 *
 * It checks the RESOLVED TEXT — copy plus every sample card — not the template
 * source, because the artifacts would arrive through data, which is how they
 * arrived the first time.
 *
 * Limitation, stated plainly: this reads text, not pixels. It cannot catch an
 * artifact baked into an embedded raster (the logo, or a screenshot someone
 * adds later as a background). It closes the path the defect actually took; it
 * is not proof the rendered PNG is clean. The PNG still gets looked at.
 */

/** Each rule is [label, RegExp]. Kept explicit rather than one mega-pattern so
 *  a failure message names which artifact class was hit. */
export const FORBIDDEN = [
  // Capture the local part too, so the failure message names the whole address
  // rather than just the domain — the person reading it needs to know WHICH
  // account leaked, not merely that one did.
  ["demo-account address", /\S*@lexitrail\.demo\b/i],
  ["demo user label", /\bdemo\s+user\b/i],
  // The original leak. Matches the app's phrasing and the generic shape, since
  // "recalled 0 out of 149" and "0 of 149" are the same disclosure.
  ["recall counter", /\b(?:recalled\s+)?\d+\s+(?:out\s+)?of\s+\d+\b/i],
  // A bare score pair ("✗ 0", "✓ 0") is chrome from the practice screen.
  ["score chrome", /[✓✗×]\s*\d+/],
  // "0:17" — the live timer that was mid-session in the old capture.
  ["session timer", /\b\d{1,2}:\d{2}\b/],
  ["exclude affordance", /\bexclude\b/i],
  // Placeholder text that must never ship as real copy.
  ["placeholder text", /\b(?:lorem ipsum|TODO|FIXME|XXX)\b/i],
];

/**
 * @param {string[]} strings every user-visible string that will be rendered.
 * @returns {{label: string, pattern: string, offending: string}[]} empty if clean.
 */
export function findForbidden(strings) {
  const hits = [];
  for (const s of strings) {
    if (typeof s !== "string") continue;
    for (const [label, pattern] of FORBIDDEN) {
      const m = s.match(pattern);
      if (m) hits.push({ label, pattern: String(pattern), offending: m[0] });
    }
  }
  return hits;
}

/** Throw with an actionable message, or return the count checked. */
export function assertClean(strings) {
  const hits = findForbidden(strings);
  if (hits.length) {
    const lines = hits.map(
      (h) => `  - ${h.label}: matched ${JSON.stringify(h.offending)} (${h.pattern})`,
    );
    throw new Error(
      `lexitrail#63 AC2: ${hits.length} capture-environment artifact(s) in the ` +
        `creative's text. These shipped to production once already — refusing ` +
        `to generate.\n${lines.join("\n")}`,
    );
  }
  return strings.length;
}
