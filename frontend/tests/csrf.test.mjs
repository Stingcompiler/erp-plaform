import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// A cookie-authenticated write is refused by the API unless it echoes the
// csrftoken cookie in X-CSRFToken (backend accounts.authentication). The one
// axios instance every call goes through — screens, the offline queue's
// pushes, the platform console — must be the thing that adds it, so nobody
// has to remember it per call. This reads the source rather than importing
// it: api.js pulls in the app's path aliases, which node's loader lacks.
const source = readFileSync(fileURLToPath(new URL("../lib/api.js", import.meta.url)), "utf8");

test("the shared axios instance echoes Django's CSRF cookie in the header Django reads", () => {
  assert.match(source, /export const CSRF_COOKIE = "csrftoken"/);
  assert.match(source, /export const CSRF_HEADER = "X-CSRFToken"/);
  const instance = source.slice(source.indexOf("axios.create({"), source.indexOf("});", source.indexOf("axios.create({")));
  assert.match(instance, /withCredentials: true/);
  assert.match(instance, /xsrfCookieName: CSRF_COOKIE/);
  assert.match(instance, /xsrfHeaderName: CSRF_HEADER/);
  // Also across the dev split (:3000 page, :8000 API), not only same-origin.
  assert.match(instance, /withXSRFToken: true/);
});

test("a csrf_failed refusal is repaired once through the identity call, never looped", () => {
  assert.match(source, /response\.data\?\.code !== "csrf_failed"/);
  assert.match(source, /config\._csrfRetried/);
  assert.match(source, /\.get\("\/auth\/me\/"\)/);
});

test("no other module talks to the API with its own credentials-bearing fetch", () => {
  // The service worker and the reachability probe only GET; anything that
  // writes must go through lib/api.js so the token travels with it.
  for (const file of ["../lib/syncQueue.js", "../lib/syncRetry.js", "../components/sync/SyncProvider.jsx"]) {
    const text = readFileSync(fileURLToPath(new URL(file, import.meta.url)), "utf8");
    for (const match of text.matchAll(/fetch\(([^)]*)\)/g)) {
      assert.doesNotMatch(match[0], /method:\s*"(POST|PUT|PATCH|DELETE)"/i, `${file}: ${match[0]}`);
    }
  }
});
