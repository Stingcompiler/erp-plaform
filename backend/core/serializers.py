from rest_framework import serializers

from core.models import ActivityLog


class ActivityLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True, default=None)
    user_name = serializers.CharField(
        source="user.full_name", read_only=True, default=None
    )
    # The role the person held — "who did this" is only useful in an audit trail
    # once you can see their authority, not just their address. Sent as the raw
    # English role name so the client can localise it the same way it does
    # everywhere else (translateRole).
    user_role = serializers.CharField(
        source="user.role.name", read_only=True, default=None
    )
    company_name = serializers.CharField(
        source="company.name", read_only=True, default=None
    )

    class Meta:
        model = ActivityLog
        fields = [
            "id", "action", "entity_type", "entity_id",
            "user", "user_email", "user_name", "user_role",
            "company", "company_name",
            "ip_address", "metadata", "created_at",
        ]
