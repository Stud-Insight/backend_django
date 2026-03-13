"""Core Celery tasks — cross-module scheduled jobs."""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# Retention period: archived periods older than this are anonymized
RETENTION_YEARS = 2  # N+1 years (graduation year + 1)


@shared_task(ignore_result=True)
def rgpd_anonymize_expired_archives():
    """
    RGPD retention cleanup (FR91, NFR-C4).

    Anonymizes personal data in archived periods older than RETENTION_YEARS.
    Preserves academic records (subjects, grades) but removes personal identifiers.
    """
    from backend_django.stages.models import StagePeriod
    from backend_django.ter.models import TERPeriod

    cutoff = timezone.now() - timedelta(days=RETENTION_YEARS * 365)
    total_anonymized = 0

    # TER periods
    ter_periods = TERPeriod.objects.filter(status="archived", modified__lt=cutoff)
    for period in ter_periods:
        count = _anonymize_ter_period(period)
        total_anonymized += count

    # Stage periods
    stage_periods = StagePeriod.objects.filter(status="archived", modified__lt=cutoff)
    for period in stage_periods:
        count = _anonymize_stage_period(period)
        total_anonymized += count

    if total_anonymized > 0:
        logger.info("RGPD cleanup: anonymized %d user references.", total_anonymized)
    else:
        logger.info("RGPD cleanup: no expired archives to process.")

    return total_anonymized


def _anonymize_ter_period(period) -> int:
    """Anonymize personal data for an expired TER period."""
    from backend_django.groups.models import Group
    from backend_django.notifications.models import Notification
    from backend_django.users.models import User

    count = 0

    # Get all students enrolled in this period
    students = period.enrolled_students.all()
    student_ids = list(students.values_list("id", flat=True))

    # Get all groups in this period
    groups = Group.objects.filter(ter_period=period)
    group_member_ids = set()
    for group in groups:
        group_member_ids.update(group.members.values_list("id", flat=True))

    # Anonymize notifications for period participants
    all_user_ids = set(student_ids) | group_member_ids
    notif_count = Notification.objects.filter(
        recipient_id__in=all_user_ids,
        data__period_id=str(period.id),
    ).update(
        title="[Anonymisé]",
        message="[Données supprimées conformément à la politique RGPD]",
        data=None,
    )
    count += notif_count

    # Remove enrolled students from period (break M2M, don't delete users)
    period.enrolled_students.clear()
    count += len(student_ids)

    # Remove professors from period
    prof_count = period.professors.count()
    period.professors.clear()
    count += prof_count

    logger.info(
        "RGPD: Anonymized TER period '%s' — %d students, %d professors, %d notifications",
        period.name,
        len(student_ids),
        prof_count,
        notif_count,
    )
    return count


def _anonymize_stage_period(period) -> int:
    """Anonymize personal data for an expired Stage period."""
    from backend_django.stages.models import StageApplication

    count = 0

    # Anonymize application motivations (personal data)
    apps = StageApplication.objects.filter(offer__stage_period=period)
    app_count = apps.update(motivation="[Anonymisé]")
    count += app_count

    logger.info(
        "RGPD: Anonymized Stage period '%s' — %d applications",
        period.name,
        app_count,
    )
    return count
