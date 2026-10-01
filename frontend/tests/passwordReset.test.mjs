import test from "node:test";
import assert from "node:assert/strict";

import { passwordChecks, passwordReady, resetDeepLink } from "../lib/passwordReset.js";
import { codeError } from "../lib/otpCode.js";

test("strength hints", () => {
  assert.deepEqual(passwordChecks("", ""), { length: false, notNumeric: false, mix: false, match: false });
  assert.deepEqual(passwordChecks("1234567890", "1234567890"), { length: true, notNumeric: false, mix: false, match: true });
  assert.deepEqual(passwordChecks("abcdefghij", "abcdefghiJ"), { length: true, notNumeric: true, mix: false, match: false });
  assert.deepEqual(passwordChecks("كلمةسر2026آمنة", "كلمةسر2026آمنة"), { length: true, notNumeric: true, mix: true, match: true });
  assert.ok(passwordReady(passwordChecks("abcdefghij", "abcdefghij")));
  assert.ok(!passwordReady(passwordChecks("1234567890", "1234567890")));
  assert.ok(!passwordReady(passwordChecks("short1", "short1")));
});

test("admin reset deep link", () => {
  const challenge = "AbC_dEf-123456789012345678901234";
  assert.deepEqual(resetDeepLink(`?email=a%40b.test&challenge=${challenge}`), { email: "a@b.test", challenge });
  assert.equal(resetDeepLink("?email=a%40b.test"), null);
  assert.equal(resetDeepLink(`?email=nobody&challenge=${challenge}`), null);
  assert.equal(resetDeepLink("?email=a%40b.test&challenge=<script>"), null);
  assert.equal(resetDeepLink(""), null);
});

test("reset error codes are recognised", () => {
  const response = (status, data) => ({ response: { status, data, headers: {} } });
  assert.equal(codeError(response(400, { code: "reset_expired" })).code, "reset_expired");
  assert.equal(codeError(response(410, { code: "link_flow_retired" })).code, "link_flow_retired");
  assert.equal(codeError(response(400, { password: ["Too common."] })).code, "invalid");
});
