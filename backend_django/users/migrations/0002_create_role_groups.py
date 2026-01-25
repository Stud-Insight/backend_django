"""
Data migration to create the 6 role groups for Stud'Insight.

Groups:
- Étudiant: Students who form groups, rank subjects, submit deliverables
- Respo TER: TER coordinators who manage periods, validate subjects
- Respo Stage: Internship coordinators who manage periods, validate offers
- Encadrant: Academic supervisors who propose subjects, grade students
- Externe: External supervisors (companies) who create internship offers
- Admin: System administrators with full access
"""

from django.db import migrations


def create_role_groups(apps, schema_editor):
    """Create the 6 role groups."""
    Group = apps.get_model("auth", "Group")

    roles = [
        "Étudiant",
        "Respo TER",
        "Respo Stage",
        "Encadrant",
        "Externe",
        "Admin",
    ]

    for role_name in roles:
        Group.objects.get_or_create(name=role_name)


def remove_role_groups(apps, schema_editor):
    """Remove the role groups (reverse migration)."""
    Group = apps.get_model("auth", "Group")

    roles = [
        "Étudiant",
        "Respo TER",
        "Respo Stage",
        "Encadrant",
        "Externe",
        "Admin",
    ]

    Group.objects.filter(name__in=roles).delete()


class Migration(migrations.Migration):
    """Create role groups for Stud'Insight."""

    dependencies = [
        ("users", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_role_groups, remove_role_groups),
    ]
