# Creates the DatabaseCache table as part of the schema, so every path that
# runs `migrate` (Render pre-deploy, upgrade.sh, the standalone runbook, CI)
# gets it without a separate operator step. `createcachetable` is a no-op
# when the table already exists.
from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    call_command("createcachetable", "vezano_cache", database=schema_editor.connection.alias, verbosity=0)


def drop_cache_table(apps, schema_editor):
    schema_editor.execute("DROP TABLE IF EXISTS vezano_cache")


class Migration(migrations.Migration):
    dependencies = [("core", "0003_attention_seen")]
    operations = [migrations.RunPython(create_cache_table, drop_cache_table)]
