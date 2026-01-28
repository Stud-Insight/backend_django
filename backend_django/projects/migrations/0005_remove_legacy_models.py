# Generated manually on 2026-01-28
# Removes legacy AcademicProject, Proposal, and ProposalApplication models
# These are replaced by Group + TERSubject/StageOffer architecture

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0004_change_student_cascade_to_set_null'),
    ]

    operations = [
        # Remove ProposalApplication first (has FK to Proposal)
        migrations.DeleteModel(
            name='ProposalApplication',
        ),
        # Remove Proposal (has FK to AcademicProject via resulting_project)
        migrations.DeleteModel(
            name='Proposal',
        ),
        # Remove AcademicProject (has M2M to Attachment via files)
        migrations.DeleteModel(
            name='AcademicProject',
        ),
    ]
