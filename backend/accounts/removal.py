"""Removing a user account, the way an owner means it.

The owner asks to remove someone who left. Two cases, and the difference
matters: an account added by mistake has touched nothing and should simply
disappear, while an account that recorded payments, approved payroll or
signed invoices *is* the evidence that segregation of duties held — deleting
that row would quietly strip the person's name off every one of those
records (the FKs are SET_NULL), leaving documents nobody is accountable for.

So: delete when nothing references the account, otherwise deactivate and say
why. Either way the account can no longer sign in, which is what the owner
actually wanted.
"""

# Rows that belong to the account rather than to the company's history:
# personal settings, this browser's push subscription, an invitation that was
# already used, and the devices the person happened to sign in from.
PERSONAL_ACCESSORS = frozenset({
    # JWT bookkeeping: rows for the sessions this account opened, which say
    # nothing about the company's records and would otherwise make every
    # person who ever signed in un-removable.
    "outstandingtoken_set",
    "preference",
    "push_subscriptions",
    "owner_invitations",
    "devices",
    "last_devices",
    "revoked_devices",
    "activity_logs",
})


def attribution_of(user):
    """Which records would lose this person's name if the row were deleted.

    Returns ``{"model label": count}`` — empty when the account is unused.
    The activity log is deliberately not counted: it keeps its own copy of
    who acted (and is archived by user id), so it never blocks a removal.
    """
    found = {}
    for relation in user._meta.related_objects:
        accessor = relation.get_accessor_name()
        if accessor in PERSONAL_ACCESSORS:
            continue
        manager = getattr(user, accessor, None)
        if manager is None:
            continue
        # A one-to-one accessor raises when absent; a related manager does not.
        try:
            exists = manager.exists() if hasattr(manager, "exists") else True
            count = manager.count() if hasattr(manager, "count") else 1
        except relation.related_model.DoesNotExist:
            continue
        if exists and count:
            found[relation.related_model._meta.label] = count
    return found
