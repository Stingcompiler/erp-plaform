import test from "node:test";
import assert from "node:assert/strict";
import { installRoute } from "../lib/installRoute.js";

// The install hint must name a route that exists in the visitor's browser.
// Desktop Firefox has none (Mozilla removed PWA install in 2021), and the
// old text sent those users to a menu item that is not there.
const UAS = {
  "firefox-desktop": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:156.0) Gecko/20100101 Firefox/156.0",
  "firefox-android": "Mozilla/5.0 (Android 14; Mobile; rv:156.0) Gecko/156.0 Firefox/156.0",
  "safari-ios": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
  "safari-mac": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
  chromium: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36 Edg/140.0",
};

for (const [expected, ua] of Object.entries(UAS)) {
  test(`installRoute detects ${expected}`, () => {
    assert.equal(installRoute(ua), expected);
  });
}

test("no user agent means no claim", () => {
  assert.equal(installRoute(""), "unknown");
});
