# ADR 0001: one product with SaaS and standalone delivery

Status: accepted — 12 September 2026

Vezano remains one Django monolith, one migration graph and one frontend. The
installation setting `VEZANO_DEPLOYMENT_MODE` selects hosted SaaS subscriptions
or a customer-managed standalone licence. It is immutable operational
configuration, not a company setting and not store/company presentation mode.

Commercial entitlement, user RBAC, company/branch scoping, and store mode are
independent checks. A subscription or licence may reduce available modules and
writes, but never grants a user an operation their role could not perform.

Existing companies receive explicit unlimited `legacy` subscriptions. The
commercial gate starts disabled, progresses through observe, then enforce after
review. This preserves behavior during deployment and makes rollback a policy
change without deleting subscription events or business data.

Standalone licences use an asymmetric signature. Customer installations contain
trusted public keys only. Permanent licences keep covered versions operational
after maintenance ends; fixed-term licences become read-only after their grace
period. No licence path deletes operational records or requires daily vendor
connectivity.
