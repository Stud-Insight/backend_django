# Generated manually on 2026-01-28
# Adds assigned_offer FK to Group model for Stage workflow

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0002_initial'),
        ('stages', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='group',
            name='assigned_offer',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='assigned_groups',
                to='stages.stageoffer',
                verbose_name='assigned offer',
            ),
        ),
    ]
