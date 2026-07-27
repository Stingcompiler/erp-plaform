import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Company",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("legal_name", models.CharField(blank=True, max_length=255)),
                ("slug", models.SlugField(blank=True, max_length=255, unique=True)),
                ("currency", models.CharField(default="SDG", max_length=8)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name_plural": "companies",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Branch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("code", models.CharField(blank=True, max_length=32)),
                ("address", models.TextField(blank=True)),
                ("phone", models.CharField(blank=True, max_length=64)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="branches", to="org.company")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Department",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("branch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="departments", to="org.branch")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="departments", to="org.company")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="TaxProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("country", models.CharField(default="SD", max_length=2)),
                ("invoice_format", models.CharField(choices=[("simple", "Simple / plain invoice")], default="simple", max_length=32)),
                ("flat_tax_rate", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("e_invoicing_enabled", models.BooleanField(default=False)),
                ("invoice_xml_format", models.CharField(blank=True, max_length=32)),
                ("company", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="tax_profile", to="org.company")),
            ],
        ),
        migrations.AddConstraint(
            model_name="branch",
            constraint=models.UniqueConstraint(fields=("company", "name"), name="uniq_branch_name_per_company"),
        ),
        migrations.AddConstraint(
            model_name="department",
            constraint=models.UniqueConstraint(fields=("company", "name"), name="uniq_department_name_per_company"),
        ),
    ]
