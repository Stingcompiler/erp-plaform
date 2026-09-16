// Turns a platform audit row into one readable sentence in the UI language.
// Rows come from core.ActivityLog: action + entity_type + metadata. Anything
// this file does not recognise falls back to "<action> <entity> #<id>", so a
// new kind of row is never hidden, only less pretty.

const ACTION_KEYS = {
  create: "created",
  update: "updated",
  delete: "deleted",
  approve: "approved",
  reject: "rejected",
  login: "login",
  logout: "logout",
  login_blocked: "loginBlocked",
};

export function describeActivity(row, t, roleLabel) {
  const m = row.metadata || {};
  const T = (key, vars) => t(`platformActivity.events.${key}`, vars);
  const label = m.label || (row.entity_id ? `#${row.entity_id}` : "");

  // Sign-in rows carry no entity; the actor is the subject.
  if (row.action === "login") return T("memberLogin");
  if (row.action === "logout") return T("memberLogout");
  if (row.action === "login_blocked") return t("platformActivity.actions.loginBlocked");

  switch (row.entity_type) {
    case "PlatformMember":
      if (row.action === "create") return T("memberInvited", { email: m.email || label, role: roleLabel(m.role) });
      if (m.role_to) return T("memberRole", { from: roleLabel(m.role_from), to: roleLabel(m.role_to) });
      if (m.is_active === false) return T("memberDeactivated");
      if (m.is_active === true) return T("memberReactivated");
      break;
    case "PlatformInvitation":
      return T(m.event === "accepted" ? "invitationAccepted" : "invitationReissued");
    case "PlatformLead":
      if (m.status_to && m.status_from !== m.status_to) {
        const st = (v) => t(`platformLeads.status${v.charAt(0).toUpperCase()}${v.slice(1)}`);
        return T("leadStatus", { name: label, from: st(m.status_from), to: st(m.status_to) });
      }
      return T("leadUpdated", { name: label });
    case "RegistrationRequest":
      if (row.action === "approve") return T("registrationApproved", { id: row.entity_id });
      if (m.status) return T("registrationStatus", { id: row.entity_id, status: m.status });
      return T("registrationUpdated", { id: row.entity_id });
    case "RegistrationProvision":
      return T("registrationProvisioned", { id: row.entity_id });
    case "OwnerInvitation":
      return T(m.event === "accepted" ? "ownerInvitationAccepted" : m.event === "reissued" ? "ownerInvitationReissued" : "ownerInvitationCreated");
    case "Subscription":
      if (m.status) return T("subscriptionTransition", { id: row.entity_id, status: m.status });
      return T(row.action === "create" ? "subscriptionCreated" : "subscriptionConfigured", { id: row.entity_id });
    case "SubscriptionInvoice":
      return T("invoiceIssued", { id: row.entity_id });
    case "SubscriptionPayment":
      if (row.action === "approve") return T("paymentVerified", { id: row.entity_id });
      if (row.action === "reject") return T("paymentRejected", { id: row.entity_id });
      return T("paymentRecorded", { id: row.entity_id });
    case "Plan":
    case "PlanVersion": {
      const kind = row.entity_type === "Plan" ? T("plan") : T("planVersion");
      const fields = Array.isArray(m.fields) && m.fields.length ? ` (${m.fields.join(", ")})` : "";
      return T(`catalogue_${row.action}`, { kind, label: m.label || label }) + (row.action === "update" ? fields : "");
    }
    default:
      break;
  }
  const actionKey = ACTION_KEYS[row.action];
  const verb = actionKey ? t(`platformActivity.actions.${actionKey}`) : row.action;
  return `${verb} ${row.entity_type || ""} ${row.entity_id ? `#${row.entity_id}` : ""}`.trim();
}

// Group label for the "type" column.
export function activityKind(row, t) {
  if (["login", "logout", "login_blocked"].includes(row.action)) return t("platformActivity.kinds.team");
  const key = {
    PlatformMember: "team",
    PlatformInvitation: "team",
    PlatformLead: "leads",
    RegistrationRequest: "registrations",
    RegistrationProvision: "registrations",
    OwnerInvitation: "registrations",
    Subscription: "subscriptions",
    SubscriptionInvoice: "billing",
    SubscriptionPayment: "billing",
    Plan: "plans",
    PlanVersion: "plans",
  }[row.entity_type];
  return key ? t(`platformActivity.kinds.${key}`) : row.entity_type || t("platformActivity.kinds.other");
}
