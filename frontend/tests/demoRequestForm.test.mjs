import test from "node:test";
import assert from "node:assert/strict";

import { classifyDemoError, firstInvalidField, phoneDigits, validateDemoRequest } from "../lib/demoRequestForm.js";
import { homeAr, homeEn } from "../lib/marketingI18n.js";

test("the phone is always required and must hold 7 to 15 digits", () => {
  assert.equal(validateDemoRequest({ name: "Amna" }).phone, "phoneRequired");
  assert.equal(validateDemoRequest({ name: "Amna", email: "a@b.co" }).phone, "phoneRequired");
  assert.equal(validateDemoRequest({ name: "Amna", phone: "call me" }).phone, "phoneInvalid");
  assert.equal(validateDemoRequest({ name: "Amna", phone: "+1 234 567 890 123 456" }).phone, "phoneInvalid");
  assert.deepEqual(validateDemoRequest({ name: "Amna", phone: "+249 91 234 5678" }), {});
  assert.equal(phoneDigits("+249 (91) 234-5678"), 12);
});

test("name is required, email optional but checked when given", () => {
  assert.equal(validateDemoRequest({ name: "  ", phone: "0912345678" }).name, "nameRequired");
  assert.equal(validateDemoRequest({ name: "Amna", phone: "0912345678", email: "not-an-email" }).email, "emailInvalid");
  assert.equal(validateDemoRequest({ name: "Amna", phone: "0912345678", email: "" }).email, undefined);
  assert.equal(validateDemoRequest({ name: "Amna", phone: "0912345678", message: "x".repeat(4001) }).message, "messageTooLong");
});

test("a 400 naming fields is shown at the fields, with no retry", () => {
  const verdict = classifyDemoError({ response: { status: 400, data: { phone: ["Enter a phone number we can call."] } } });
  assert.deepEqual(verdict, { kind: "fields", fields: { phone: "phoneInvalid" } });
  assert.equal(firstInvalidField({ email: "emailInvalid", phone: "phoneInvalid" }), "phone");
});

test("only 5xx and network failures offer a retry", () => {
  assert.equal(classifyDemoError({}).kind, "retry");
  assert.equal(classifyDemoError({ response: { status: 502 } }).kind, "retry");
  assert.equal(classifyDemoError({ response: { status: 503 } }).key, "improvements.contactUnavailable");
  assert.equal(classifyDemoError({ response: { status: 429 } }).kind, "throttled");
  assert.equal(classifyDemoError({ response: { status: 400, data: { website: ["Leave this field empty."] } } }).kind, "rejected");
  assert.equal(classifyDemoError({ response: { status: 403, data: { detail: "CSRF" } } }).kind, "rejected");
});

test("every message the form can show exists in both languages", () => {
  const keys = ["nameRequired", "nameInvalid", "phoneRequired", "phoneInvalid", "emailInvalid", "messageTooLong", "summary", "throttled", "rejected", "retry"];
  for (const dict of [homeEn, homeAr]) {
    for (const key of keys) assert.equal(typeof dict.formErrors[key], "string", key);
  }
});
