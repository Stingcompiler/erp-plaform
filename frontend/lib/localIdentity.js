// Local data belongs to a specific company, user and branch. Old unscoped
// data is deliberately left untouched: its owner cannot be inferred safely.
let activeScope = null;
export function identityScope(user) {
  return user?.id && user?.company
    ? `${user.company}:${user.id}:${user.branch ?? "shared"}` : null;
}
export function setLocalIdentity(user) { activeScope = identityScope(user); }
export function localScope() { return activeScope; }
export function storageKey(name, scope = activeScope) {
  if (!scope) throw new Error("A signed-in company is required for local storage.");
  return `erp.${name}.v2:${scope}`;
}
