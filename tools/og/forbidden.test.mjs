/**
 * Tests for the AC2 artifact guard (lexitrail#63).
 *
 * The point of these is the FIRING direction. A guard that only ever gets
 * exercised against clean input is indistinguishable from a guard that does
 * nothing, and that is precisely the failure this issue is about: the broken
 * creative shipped for weeks while everything reported healthy. So each real
 * artifact from the replaced asset gets its own case asserting the guard TRIPS
 * on it, and only then a case asserting it stays quiet on the real copy.
 *
 * Run: npm test   (in tools/og)
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { findForbidden, assertClean } from "./forbidden.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));

/* ---------- firing direction: every artifact the old asset actually shipped ---------- */

// Each string below was READ OFF the replaced creative
// (ui/public/images/og/hsk2-practice.png), not invented as a plausible example.
// That PNG was deleted in issue-172 (unreferenced demo capture); the strings
// stay because they are what shipped, and this file reads text, never the PNG.
const REAL_ARTIFACTS = [
  ["demo account email", "4usvy@lexitrail.demo"],
  ["demo display name", "Demo User"],
  ["recall counter, app phrasing", "recalled 0 out of 149"],
  ["recall counter, short form", "0 of 149"],
  ["zeroed score chrome", "✗ 0"],
  ["session timer", "0:17"],
  ["exclude affordance", "Exclude 0"],
];

for (const [label, artifact] of REAL_ARTIFACTS) {
  test(`FIRES on ${label}: ${JSON.stringify(artifact)}`, () => {
    const hits = findForbidden([artifact]);
    assert.ok(
      hits.length > 0,
      `guard did not trip on ${JSON.stringify(artifact)}, which shipped to production`,
    );
  });
}

test("FIRES when an artifact arrives buried in otherwise-good copy", () => {
  // The realistic shape: nobody adds "Demo User" as the headline. It arrives
  // appended to a legitimate string by a data source.
  const hits = findForbidden([
    "Flashcards with image hints — recalled 0 out of 149",
  ]);
  assert.ok(hits.length > 0, "guard must scan within strings, not just whole-string match");
});

test("assertClean THROWS and names the artifact class", () => {
  assert.throws(
    () => assertClean(["Lexitrail", "4usvy@lexitrail.demo"]),
    (err) => {
      assert.match(err.message, /AC2/);
      assert.match(err.message, /demo-account address/);
      assert.match(err.message, /4usvy@lexitrail\.demo/);
      return true;
    },
  );
});

/* ---------- quiet direction: a guard stuck ON is as useless as one stuck OFF ---------- */

test("STAYS QUIET on the real shipped copy", () => {
  const copy = JSON.parse(readFileSync(join(HERE, "copy.json"), "utf8"));
  const strings = [copy.badge, copy.wordmark, copy.headline, copy.mechanism, copy.coverage];
  const hits = findForbidden(strings);
  assert.deepEqual(
    hits,
    [],
    `guard tripped on approved copy: ${JSON.stringify(hits)} — a guard stuck in the ` +
      `firing position blocks all generation and reads as "working"`,
  );
});

test("STAYS QUIET on real HSK vocabulary rows", () => {
  // Guards against an over-broad pattern rejecting legitimate glosses. The
  // recall-counter rule matches "N of M", and English glosses in these decks
  // contain phrases like "out of" — so this is a live risk, not a hypothetical.
  const hits = findForbidden(["让", "ràng", "to let, to allow", "千", "qiān", "thousand"]);
  assert.deepEqual(hits, [], `guard tripped on vocabulary data: ${JSON.stringify(hits)}`);
});

test("STAYS QUIET on an empty list, and counts what it checked", () => {
  assert.equal(assertClean([]), 0);
  assert.equal(assertClean(["Lexitrail", "HSK 1 · HSK 2"]), 2);
});

test("ignores non-strings rather than throwing on them", () => {
  assert.deepEqual(findForbidden([null, undefined, 42, {}]), []);
});
