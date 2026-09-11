from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.models import Permission, Role, User
from org.store_mode import is_system_mode_owner


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "code", "name", "description"]


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SlugRelatedField(
        slug_field="code",
        queryset=Permission.objects.all(),
        many=True,
        required=False,
    )

    class Meta:
        model = Role
        fields = ["id", "name", "scope_level", "description", "permissions"]


class UserSerializer(serializers.ModelSerializer):
    """Read/write serializer for user administration within a company."""

    password = serializers.CharField(write_only=True, required=False, min_length=10)
    role_name = serializers.SerializerMethodField()

    def get_role_name(self, obj):
        return obj.role.name if obj.role_id else None

    def validate_password(self, value):
        # M10: enforce AUTH_PASSWORD_VALIDATORS on the API surface.
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "company",
            "branch",
            "role",
            "role_name",
            "is_active",
            "password",
        ]
        read_only_fields = ["company"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class MeSerializer(serializers.ModelSerializer):
    role_name = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    is_platform_admin = serializers.BooleanField(read_only=True)

    def get_role_name(self, obj):
        return obj.role.name if obj.role_id else None

    # Shapes how much of the app the client puts on screen. Sent here rather
    # than fetched separately so the shell can render the right navigation on
    # first paint instead of rearranging itself a moment later.
    business_type = serializers.SerializerMethodField()
    # Drives the one-time setup prompt. Sent with the identity call so the
    # shell can ask on first paint rather than after a second round trip.
    business_type_chosen = serializers.SerializerMethodField()
    can_manage_system_mode = serializers.SerializerMethodField()

    def get_company_name(self, obj):
        return obj.company.name if obj.company_id else None

    def get_business_type(self, obj):
        return obj.company.business_type if obj.company_id else None

    def get_business_type_chosen(self, obj):
        # A user with no company has nothing to configure, so nothing to ask.
        return obj.company.business_type_chosen if obj.company_id else True

    def get_can_manage_system_mode(self, obj):
        return is_system_mode_owner(obj)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "company",
            "company_name",
            "business_type",
            "business_type_chosen",
            "can_manage_system_mode",
            "branch",
            "role",
            "role_name",
            "is_platform_admin",
        ]


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        request = self.context.get("request")
        user = authenticate(
            request=request,
            username=attrs["email"],
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")
        attrs["user"] = user
        return attrs
