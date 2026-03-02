"""
Enable PostgreSQL unaccent extension for accent-insensitive searches.
"""

from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_add_company_name"),
    ]

    operations = [
        UnaccentExtension(),
    ]
