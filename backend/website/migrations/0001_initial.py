import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("org", "0001_initial"),
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Website",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("business_name", models.CharField(blank=True, max_length=255)),
                ("tagline", models.CharField(blank=True, max_length=255)),
                ("about_text", models.TextField(blank=True)),
                ("logo_url", models.URLField(blank=True)),
                ("primary_color", models.CharField(default="#111827", max_length=16)),
                ("contact_email", models.EmailField(blank=True, max_length=254)),
                ("contact_phone", models.CharField(blank=True, max_length=64)),
                ("address", models.TextField(blank=True)),
                ("social_links", models.JSONField(blank=True, default=dict)),
                ("is_published", models.BooleanField(default=False)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="website", to="org.company")),
            ],
        ),
        migrations.CreateModel(
            name="Section",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("type", models.CharField(choices=[("hero", "Hero"), ("about", "About"), ("products", "Products"), ("gallery", "Gallery"), ("contact", "Contact"), ("custom", "Custom")], max_length=16)),
                ("title", models.CharField(blank=True, max_length=255)),
                ("order", models.PositiveIntegerField(default=0)),
                ("content", models.JSONField(blank=True, default=dict)),
                ("is_visible", models.BooleanField(default=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="website_sections", to="org.company")),
                ("website", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sections", to="website.website")),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.CreateModel(
            name="FeaturedProduct",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("caption", models.CharField(blank=True, max_length=255)),
                ("order", models.PositiveIntegerField(default=0)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="featured_products", to="org.company")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="featured_on", to="inventory.product")),
                ("website", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="featured_products", to="website.website")),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.AddConstraint(
            model_name="featuredproduct",
            constraint=models.UniqueConstraint(fields=("website", "product"), name="uniq_featured_product_per_site"),
        ),
    ]
