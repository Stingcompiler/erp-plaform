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
