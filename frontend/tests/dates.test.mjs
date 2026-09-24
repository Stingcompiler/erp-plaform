import assert from "node:assert/strict";
import test from "node:test";

import { localToday } from "../lib/dates.js";

test("the local calendar day, not the UTC one", () => {
  // 00:30 local on 1 Oct: whatever the machine's zone, the local fields win.
  const d = new Date(2026, 9, 1, 0, 30);
  assert.equal(localToday(d), "2026-10-01");
});
