from rest_framework import serializers

from licensing.models import Installation, LicenseActivation


class InstallationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Installation
        fields = [
            "installation_id",
            "organisation_name",
            "deployment_mode",
            "application_version",
            "installed_at",
        ]


class LicenseActivationSerializer(serializers.ModelSerializer):
    class Meta:
        model = LicenseActivation
        fields = [
            "license_id",
            "organisation_name",
            "kind",
            "key_id",
            "modules",
            "limits",
            "usable_until",
            "grace_until",
            "maintenance_until",
            "max_application_version",
            "activated_at",
        ]


class LicenseImportSerializer(serializers.Serializer):
    payload = serializers.JSONField()
    signature = serializers.CharField()
