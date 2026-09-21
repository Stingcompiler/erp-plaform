from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0012_inflation_pricing'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='reference_cost',
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True),
        ),
    ]
