import test from "node:test";
import assert from "node:assert/strict";
import { telUrl, whatsappNumber, whatsappUrl } from "../lib/phone.js";

test("local numbers get the country's dialling code", () => {
  assert.equal(whatsappNumber("0912 345 678"), "249912345678");
  assert.equal(whatsappNumber("0912345678", "SD"), "249912345678");
  assert.equal(whatsappNumber("0501234567", "SA"), "966501234567");
  assert.equal(whatsappNumber("01001234567", "eg"), "201001234567");
  // Unknown country falls back to the platform's home market.
  assert.equal(whatsappNumber("0912345678", "ZZ"), "249912345678");
});

test("international forms are trusted as written", () => {
  assert.equal(whatsappNumber("+249 91 234 5678"), "249912345678");
  assert.equal(whatsappNumber("00966 50 123 4567", "SD"), "966501234567");
  assert.equal(whatsappNumber("249912345678"), "249912345678");
});

test("nonsense yields no link", () => {
  assert.equal(whatsappNumber(""), "");
  assert.equal(whatsappNumber("   "), "");
  assert.equal(whatsappNumber("12345"), "");
  assert.equal(whatsappNumber("call me"), "");
  assert.equal(whatsappUrl("call me"), "");
  assert.equal(whatsappUrl("0912345678"), "https://wa.me/249912345678");
});

test("tel: keeps the plus and drops formatting", () => {
  assert.equal(telUrl("+249 91 234 5678"), "tel:+249912345678");
  assert.equal(telUrl("0912-345-678"), "tel:0912345678");
  assert.equal(telUrl(""), "");
});
