from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext as _
from rest_framework import serializers

from accounts.models import Permission, Role, User
from core.rbac import (
    can_approve_high_value, can_review_price_flags, can_see_cost, report_areas_for,
)
from core.platform_roles import platform_capabilities_for
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


# Authority ladder for company user administration. An actor may administer
# only accounts whose CURRENT role ranks below their own (owners may also
# administer other owners), and may assign only roles at or below their own
# rank. Every other business role ranks 0; platform roles sit outside the
# ladder and are refused to tenant actors separately.
ROLE_RANK = {"Business Owner": 3, "General Manager": 2, "Branch Manager": 1}


def role_rank(role):
    if role is None:
        return 0
    return ROLE_RANK.get(role.name, 0)


def invalidate_sessions(user):
    """Blacklist every refresh token the user holds, so a password change
    (their own, or an administrator's reset) ends any session the old
    credential opened. Access tokens expire on their own within minutes."""
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


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

    def validate(self, attrs):
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        role = attrs.get("role", getattr(self.instance, "role", None))
        branch = attrs.get("branch", getattr(self.instance, "branch", None))
        actor_role_name = getattr(getattr(actor, "role", None), "name", None)
        actor_company_id = getattr(actor, "company_id", None)

        # A tenant administrator must never be able to turn a tenant account
        # into a platform account. Platform roles are provisioned only by an
        # existing platform administrator.
        if (
            role is not None
            and role.scope_level == Role.SCOPE_PLATFORM
            and not getattr(actor, "is_platform_admin", False)
        ):
            raise serializers.ValidationError(
                {"role": _("Only a platform administrator may assign a platform role.")}
            )

        if actor_company_id is not None:
            actor_rank = role_rank(getattr(actor, "role", None))
            current_role = getattr(self.instance, "role", None) if self.instance else None
            editing_other = (
                self.instance is not None and self.instance.pk != getattr(actor, "pk", None)
            )
            if editing_other and (
                role_rank(current_role) > actor_rank
                or (actor_role_name == "Branch Manager" and role_rank(current_role) >= 1)
            ):
                raise serializers.ValidationError(
                    {"role": _("You cannot modify an account with equal or higher authority.")}
                )
            if role is not None and role_rank(role) > actor_rank:
                raise serializers.ValidationError(
                    {"role": _("You cannot assign a role above your own authority.")}
                )
            if actor_role_name == "General Manager":
                if role and role.name == "Business Owner":
                    raise serializers.ValidationError(
                        {"role": _("Only a Business Owner may assign the owner role.")}
                    )
                if (
                    self.instance
                    and self.instance.role
                    and self.instance.role.name == "Business Owner"
                ):
                    raise serializers.ValidationError(
                        {"role": _("A General Manager cannot modify a Business Owner.")}
                    )
            elif actor_role_name == "Branch Manager":
                if branch is None or branch.pk != getattr(actor, "branch_id", None):
                    raise serializers.ValidationError(
                        {"branch": _("A Branch Manager may manage only their own branch.")}
                    )
                if self.instance and self.instance.branch_id != actor.branch_id:
                    raise serializers.ValidationError(
                        {"branch": _("This user is outside your branch.")}
                    )
                if (
                    role is None
                    or role.scope_level != Role.SCOPE_BRANCH
                    or role.name == "Branch Manager"
                ):
                    raise serializers.ValidationError(
                        {"role": _("A Branch Manager may assign only branch staff roles.")}
                    )
            elif actor_role_name != "Business Owner":
                raise serializers.ValidationError(_("Your role cannot administer company users."))

        target_company_id = (
            self.instance.company_id if self.instance is not None else actor_company_id
        )
        if target_company_id is not None and role is None:
            raise serializers.ValidationError(
                {"role": _("A company user must have an assigned role.")}
            )
        if role is not None and role.scope_level == Role.SCOPE_BRANCH:
            if branch is None:
                raise serializers.ValidationError(
                    {"branch": _("A branch-scoped role requires an assigned branch.")}
                )
            if not branch.is_active:
                raise serializers.ValidationError({"branch": _("The assigned branch is inactive.")})
        if (
            branch is not None
            and actor_company_id is not None
            and branch.company_id != actor_company_id
        ):
            raise serializers.ValidationError(
                {"branch": _("The branch must belong to your company.")}
            )

        if (
            self.instance is not None
            and actor is not None
            and self.instance.pk == actor.pk
            and attrs.get("is_active") is False
        ):
            raise serializers.ValidationError(
                {"is_active": _("You cannot deactivate your own account.")}
            )
        if (
            self.instance is not None
            and actor is not None
            and self.instance.pk == actor.pk
            and "role" in attrs
            and role != self.instance.role
        ):
            raise serializers.ValidationError({"role": _("You cannot change your own role.")})
        return attrs

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
            # Someone else chose this password: it is provisional until the
            # person replaces it with one only they know.
            actor = getattr(self.context.get("request"), "user", None)
            instance.must_change_password = (
                actor is None or getattr(actor, "pk", None) != instance.pk
            )
        instance.save()
        if password:
            invalidate_sessions(instance)
        return instance


class UserDetailSerializer(UserSerializer):
    """One company user in full for the people page: the profile fields plus
    when the account was created and last used, the changes made to it, and
    (for audit viewers) their own recent actions."""

    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    history = serializers.SerializerMethodField()
    activity = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + [
            "created_at", "updated_at", "last_login", "branch_name", "history", "activity",
        ]
        read_only_fields = UserSerializer.Meta.read_only_fields + [
            "created_at", "updated_at", "last_login", "branch_name", "history", "activity",
        ]

    @staticmethod
    def _person(user):
        if user is None:
            return None
        return {"id": user.pk, "full_name": user.full_name, "email": user.email}

    def _entry(self, row):
        return {
            "id": row.pk, "action": row.action, "entity_type": row.entity_type,
            "entity_id": row.entity_id, "metadata": row.metadata,
            "created_at": row.created_at, "user": self._person(row.user),
        }

    def get_history(self, obj):
        from core.models import ActivityLog

        rows = (
            ActivityLog.objects.filter(
                company_id=obj.company_id, entity_type="User", entity_id=str(obj.pk)
            )
            .select_related("user").order_by("-created_at")[:50]
        )
        return [self._entry(row) for row in rows]

    def get_activity(self, obj):
        from core.models import ActivityLog
        from core.rbac import can_view_audit_log

        request = self.context.get("request")
        if request is None or not can_view_audit_log(request.user):
            return None
        rows = (
            ActivityLog.objects.filter(company_id=obj.company_id, user=obj)
            .select_related("user").order_by("-created_at")[:50]
        )
        return [self._entry(row) for row in rows]


class MeSerializer(serializers.ModelSerializer):
    role_name = serializers.SerializerMethodField()
    # "branch" for a role limited to one branch: screens hide what the server
    # only offers company-wide (e.g. average/FIFO valuation).
    role_scope = serializers.SerializerMethodField()
    must_change_password = serializers.BooleanField(read_only=True)
    company_name = serializers.SerializerMethodField()
    is_platform_admin = serializers.BooleanField(read_only=True)
    report_areas = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()

    def get_report_areas(self, obj):
        areas = report_areas_for(obj)
        # Every report endpoint sits in the `reports` module: a plan without
        # it refuses them all (module_not_in_plan), so the role's areas are
        # empty here — the reports screen and the HR payroll tab used to ask
        # anyway and showed four "failed" reports to an owner on such a plan.
        if areas and not self._plan_allows(obj, "reports"):
            return []
        return areas

    def _plan_allows(self, obj, module):
        if not obj.company_id:
            return True
        from core.entitlements import resolve_entitlements

        return resolve_entitlements(obj.company).allows_module(module)

    currency = serializers.SerializerMethodField()

    def get_currency(self, obj):
        """The company's own currency, so every screen labels money alike."""
        return obj.company.currency if obj.company_id else None

    def get_role_name(self, obj):
        return obj.role.name if obj.role_id else None

    def get_role_scope(self, obj):
        return obj.role.scope_level if obj.role_id else None

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

    # The POS computes what the customer owes before the server confirms the
    # sale (offline included), so it must apply the same tax rate the server
    # will. Sent with the identity call: one source, no extra round trip.
    tax_rate = serializers.SerializerMethodField()

    def get_tax_rate(self, obj):
        if not obj.company_id:
            return "0"
        profile = getattr(obj.company, "tax_profile", None)
        return str(profile.flat_tax_rate) if profile else "0"

    # The till warns before a discount it would refuse (see
    # Company.max_discount_percent); None = no limit.
    max_discount_percent = serializers.SerializerMethodField()

    def get_max_discount_percent(self, obj):
        if not obj.company_id:
            return None
        limit = obj.company.max_discount_percent
        return None if limit is None else str(limit)

    # The access decision the shell needs on first paint: whether writes are
    # open, why not, and when the current state ends — so a licence in grace
    # or a lapsed subscription is announced on every screen, not discovered
    # on the first rejected save.
    entitlements = serializers.SerializerMethodField()
    deployment_mode = serializers.SerializerMethodField()

    def get_deployment_mode(self, obj):
        from config.deployment import get_deployment_config

        return get_deployment_config().mode

    def get_entitlements(self, obj):
        from core.entitlements import resolve_entitlements

        if not obj.company_id and not getattr(obj, "is_platform_admin", False):
            return None
        decision = resolve_entitlements(obj.company if obj.company_id else None)
        return {
            "source": decision.source,
            "state": decision.state,
            "allow_writes": decision.allow_writes,
            "valid_until": decision.valid_until.isoformat() if decision.valid_until else None,
            "reason": decision.reason,
            # What the plan includes ("*" = everything), so a screen can say
            # "not in your plan" instead of failing request by request.
            "modules": sorted(decision.modules),
        }

    def get_capabilities(self, obj):
        role_name = obj.role.name if obj.role_id else None
        owner = role_name == "Business Owner"
        general_manager = role_name == "General Manager"
        branch_manager = role_name == "Branch Manager"
        return {
            "users.assign_owner": owner,
            "users.manage_company": owner or general_manager,
            "users.manage_branch": owner or general_manager or branch_manager,
            "org.manage_all_branches": owner or general_manager,
            "org.manage_own_branch": branch_manager,
            "org.change_system_mode": self.get_can_manage_system_mode(obj),
            "subscriptions.manage": owner,
            # Voiding documents, overriding credit limits, signing off tills:
            # the same approver roles core.rbac.can_approve_high_value names.
            "finance.approve": can_approve_high_value(obj),
            # Sees what goods cost (product cost fields are hidden otherwise).
            "inventory.see_cost": can_see_cost(obj),
            # Reviews sales an offline till kept with a refused price.
            "sales.review_prices": can_review_price_flags(obj),
            "scope.branch_id": obj.branch_id,
            **{name: True for name in platform_capabilities_for(obj)},
        }

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
            "role_scope",
            "tax_rate",
            "max_discount_percent",
            "currency",
            "entitlements",
            "deployment_mode",
            "is_platform_admin",
            "report_areas",
            "capabilities",
            "must_change_password",
        ]


class ChangePasswordSerializer(serializers.Serializer):
    """A signed-in person replacing their own password. The current one is
    required so a walked-away session cannot be turned into a lockout."""

    current_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError(_("The current password is incorrect."))
        return value

    def validate_new_password(self, value):
        try:
            validate_password(value, self.context["request"].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


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
            raise serializers.ValidationError(_("Invalid email or password."))
        if not user.is_active:
            raise serializers.ValidationError(_("This account is inactive."))
        attrs["user"] = user
        return attrs
