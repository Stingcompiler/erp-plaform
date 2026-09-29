// The walkthrough form on the home page (components/landing/LandingPage.jsx,
// ContactCTA): its own field checks and how a failed send is explained.
//
// The rules mirror website.serializers.DemoRequestSerializer, so a visitor
// hears about a mistake next to the field, in the page's language, before
// anything is sent; the server still decides. The phone is required on the
// form (the owner's call), the email optional. Every message is an i18n key
// under home.formErrors.

export const DEMO_FIELDS = ["name", "phone", "email", "message"];

export const LIMITS = { name: 255, phone: 32, email: 254, message: 4000 };

// Digits the way the server counts them (validate_phone): 7 to 15, spaces,
// dashes, brackets and a leading + allowed around them.
export function phoneDigits(value) {
  return (String(value || "").match(/\d/g) || []).length;
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// { field: messageKey } for every field that would not be accepted.
export function validateDemoRequest(values) {
  const errors = {};
  const name = String(values.name || "").trim();
  const phone = String(values.phone || "").trim();
  const email = String(values.email || "").trim();
  const message = String(values.message || "");
  if (!name) errors.name = "nameRequired";
  else if (name.length > LIMITS.name) errors.name = "nameInvalid";
  if (!phone) errors.phone = "phoneRequired";
  else if (phoneDigits(phone) < 7 || phoneDigits(phone) > 15 || phone.length > LIMITS.phone) errors.phone = "phoneInvalid";
  if (email && (!EMAIL.test(email) || email.length > LIMITS.email)) errors.email = "emailInvalid";
  if (message.length > LIMITS.message) errors.message = "messageTooLong";
  return errors;
}

// The server's field names → the message the form shows next to that field.
// Its own wording is English or Arabic depending on a cookie; this keeps the
// page's language and a message the visitor can act on.
const SERVER_FIELD_MESSAGE = {
  name: "nameInvalid",
  phone: "phoneInvalid",
  email: "emailInvalid",
  message: "messageTooLong",
};

// What a failed send means for the visitor:
//   { kind: "fields", fields }  a 400 naming fields: fix them, no retry;
//   { kind: "rejected" }        a 400/4xx about nothing they can fix here;
//   { kind: "throttled" }       429: too many sends from this address;
//   { kind: "retry", key }      5xx or no answer: the only case to retry.
export function classifyDemoError(error) {
  const response = error?.response;
  if (!response) return { kind: "retry", key: "improvements.contactError" };
  const { status, data } = response;
  if (status >= 500) {
    return { kind: "retry", key: status === 503 ? "improvements.contactUnavailable" : "improvements.contactError" };
  }
  if (status === 429) return { kind: "throttled" };
  if (status === 400 && data && typeof data === "object") {
    const fields = {};
    for (const [field, key] of Object.entries(SERVER_FIELD_MESSAGE)) {
      if (data[field]) fields[field] = key;
    }
    if (Object.keys(fields).length) return { kind: "fields", fields };
  }
  return { kind: "rejected" };
}

// The first field (in the form's order) that has an error, to move focus to.
export function firstInvalidField(errors) {
  return DEMO_FIELDS.find((field) => errors && errors[field]) || null;
}
