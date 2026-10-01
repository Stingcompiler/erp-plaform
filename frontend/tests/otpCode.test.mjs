import test from "node:test";
import assert from "node:assert/strict";

import {
  codeError, fieldErrors, formatCountdown, isCompleteCode, isRequestReference, liveView,
  normaliseCode, secondsUntil, viewRecord,
} from "../lib/otpCode.js";

test("codes are six ASCII digits, whatever was typed or pasted", () => {
  assert.equal(normaliseCode("123 456"), "123456");
  assert.equal(normaliseCode("١٢٣٤٥٦"), "123456");
  assert.equal(normaliseCode("۱۲۳-۴۵۶"), "123456");
  assert.equal(normaliseCode("Your code: 987654."), "987654");
  assert.equal(normaliseCode("12345678"), "123456");
  assert.equal(normaliseCode(null), "");
  assert.ok(isCompleteCode(" 12 34 56 "));
  assert.ok(!isCompleteCode("12345"));
});

test("countdowns", () => {
  assert.equal(secondsUntil(10_500, 10_000), 1);
  assert.equal(secondsUntil(70_000, 10_000), 60);
  assert.equal(secondsUntil(5_000, 10_000), 0);
  assert.equal(formatCountdown(45), "0:45");
  assert.equal(formatCountdown(605), "10:05");
  assert.equal(formatCountdown(-3), "0:00");
});

test("API errors map to stable codes", () => {
  assert.deepEqual(codeError({}), { code: "network" });
  assert.deepEqual(
    codeError({ response: { status: 400, data: { code: "wrong_code", attempts_left: 3 } } }),
    { code: "wrong_code", attemptsLeft: 3, retryAfter: 0, whatsapp: "" },
  );
  assert.equal(
    codeError({ response: { status: 429, data: { code: "resend_cooldown", retry_after: 42 } } }).retryAfter, 42,
  );
  assert.equal(
    codeError({ response: { status: 409, data: { code: "duplicate_request", whatsapp: "+249 9" } } }).whatsapp, "+249 9",
  );
  assert.deepEqual(codeError({ response: { status: 429, data: { detail: "x" }, headers: { "retry-after": "60" } } }),
    { code: "throttled", retryAfter: 60 });
  assert.equal(codeError({ response: { status: 400, data: { email: ["Bad"] } } }).code, "invalid");
  assert.equal(codeError({ response: { status: 500, data: "boom" } }).code, "network");
});

test("field errors sit next to their field", () => {
  assert.deepEqual(fieldErrors({ email: ["Enter a valid email."], phone: "Too short", n: [1] }),
    { email: "Enter a valid email.", phone: "Too short" });
  assert.deepEqual(fieldErrors(null), {});
});

test("trial and demo references go to the request flow", () => {
  assert.ok(isRequestReference("R4P9XT2"));
  assert.ok(isRequestReference(" #d4p9xt2 "));
  assert.ok(!isRequestReference("W7K3MQ2"));
  // "Rashida" has the shape of one: the page only suggests the request flow.
  assert.ok(isRequestReference("Rashida"));
  assert.ok(!isRequestReference("Rashid"));
  assert.ok(!isRequestReference("0912345678"));
});

test("the verified view lasts until its token expires", () => {
  const record = viewRecord("tok", 1800, 1_000);
  assert.equal(record.until, 1_801_000);
  assert.equal(liveView(record, 1_800_999), record);
  assert.equal(liveView(record, 1_801_000), null);
  assert.equal(liveView({ until: 9e15 }, 0), null);
  assert.equal(liveView(null), null);
});
