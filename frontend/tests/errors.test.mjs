import assert from "node:assert/strict";
import test from "node:test";

import { errorText, errorDetail } from "../lib/errors.js";
import { translate } from "../lib/i18n.js";

const t = (key, vars) => translate("ar", key, vars);
const withResponse = (status, data) => ({ response: { status, data } });

test("a request that never reached the server reads as a connection problem", () => {
  assert.equal(errorText(new Error("boom"), t), translate("ar", "errors.network"));
});

test("a coded failure is translated, not dumped", () => {
  const message = errorText(
    withResponse(403, { code: "module_not_in_plan", detail: "This module is not included..." }),
    t,
  );
  assert.equal(message, translate("ar", "errors.codes.module_not_in_plan"));
  assert.ok(!message.includes("module"));
});

test("statuses map onto sentences, 5xx carries the status for support", () => {
  assert.equal(errorText(withResponse(403, {}), t), translate("ar", "errors.forbidden"));
  assert.equal(errorText(withResponse(404, {}), t), translate("ar", "errors.notFound"));
  assert.equal(errorText(withResponse(429, {}), t), translate("ar", "errors.tooMany"));
  assert.equal(errorText(withResponse(500, {}), t), `${translate("ar", "errors.server")} (HTTP 500)`);
});

test("a validation failure uses the caller's own sentence, never the payload", () => {
  const error = withResponse(400, { phone_number_id: ["This field is required."] });
  assert.equal(errorText(error, t, "settings.saveFailed"), translate("ar", "settings.saveFailed"));
  // The API's words stay available for a secondary line.
  assert.equal(errorDetail(error), "This field is required.");
});

test("an unknown code falls back instead of showing the code", () => {
  const message = errorText(withResponse(400, { code: "not_a_known_code" }), t, "finance.saveError");
  assert.equal(message, translate("ar", "finance.saveError"));
});

test("the server's own sentence wins when it is in the reader's language", () => {
  const arabic = withResponse(400, { amount: ["المبلغ يتجاوز المستحق (250.00)."] });
  assert.equal(errorText(arabic, t, "finance.saveError"), "المبلغ يتجاوز المستحق (250.00).");
  const detail = withResponse(403, { detail: "دورك لا يسمح بتعديل هذا الفرع." });
  assert.equal(errorText(detail, t), "دورك لا يسمح بتعديل هذا الفرع.");
});

test("an untranslated English message never reaches an Arabic screen", () => {
  const english = withResponse(400, { detail: "Target company already has products." });
  assert.equal(errorText(english, t, "settings.restoreFailed"), translate("ar", "settings.restoreFailed"));
});

test("on an English screen the English message is shown", () => {
  const en = (key, vars) => translate("en", key, vars);
  const english = withResponse(400, { detail: "Target company already has products." });
  assert.equal(errorText(english, en, "settings.restoreFailed"), "Target company already has products.");
});
