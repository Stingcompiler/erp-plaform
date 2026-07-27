from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class Permission(models.Model):
    """
    Application-level permission (distinct from Django's auth.Permission).
    Fine-grained per-action enforcement is wired progressively; M1 ships the
    model + seed data so roles can be described precisely from the start.
    """

    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class Role(models.Model):
    """
    The fixed role set from the build plan. `scope_level` records whether a
    role is platform-, business-, or branch-level so later milestones can gate
    visibility (M6) without re-deriving it.
    """

    SCOPE_PLATFORM = "platform"
    SCOPE_BUSINESS = "business"
    SCOPE_BRANCH = "branch"
    SCOPE_CHOICES = [
        (SCOPE_PLATFORM, "Platform"),
        (SCOPE_BUSINESS, "Business"),
        (SCOPE_BRANCH, "Branch"),
    ]

    name = models.CharField(max_length=100, unique=True)
    scope_level = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Email-login custom user. `company` is nullable because platform-level
    Super Administrators exist outside any single tenant; every other user is
    bound to exactly one company, which drives Rule #1 scoping everywhere.
    """

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, blank=True)

    company = models.ForeignKey(
        "org.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="users",
    )
    branch = models.ForeignKey(
        "org.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )

    is_active = models.BooleanField(default=True)
    # is_staff controls Django admin access only, not app permissions.
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.email

    @property
    def is_platform_admin(self):
        """
        True for platform-level Super Administrators, who are NOT company
        scoped. Django superusers also count so a bootstrap admin works before
        any Role rows exist.
        """
        if self.is_superuser:
            return True
        return bool(self.role and self.role.scope_level == Role.SCOPE_PLATFORM)
