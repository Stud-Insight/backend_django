"""
Celery tasks for TER deliverables.

Handles async file processing for large uploads.
"""

import logging
from uuid import UUID

from celery import shared_task
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_deliverable_upload(
    self,
    deliverable_id: str,
    file_content: bytes,
    filename: str,
    content_type: str,
) -> dict:
    """
    Process a deliverable file upload asynchronously.

    This task:
    1. Updates deliverable status to PROCESSING
    2. Saves the file to MinIO/S3
    3. Updates deliverable status to COMPLETED (or FAILED)

    Args:
        deliverable_id: UUID of the TERDeliverable
        file_content: File bytes to upload
        filename: Original filename
        content_type: MIME type

    Returns:
        Dict with upload result
    """
    from backend_django.ter.models import TERDeliverable, UploadStatus

    deliverable_uuid = UUID(deliverable_id)

    try:
        deliverable = TERDeliverable.objects.get(id=deliverable_uuid)

        # Update status to processing
        deliverable.upload_status = UploadStatus.PROCESSING
        deliverable.save(update_fields=["upload_status", "modified"])

        logger.info(
            "Processing deliverable upload: %s (%s bytes)",
            filename,
            len(file_content),
        )

        # Save file to storage
        file_obj = ContentFile(file_content, name=filename)
        deliverable.file.save(filename, file_obj, save=False)
        deliverable.size = len(file_content)
        deliverable.upload_status = UploadStatus.COMPLETED
        deliverable.upload_error = ""
        deliverable.save()

        logger.info("Deliverable upload completed: %s", deliverable.id)

        return {
            "success": True,
            "deliverable_id": str(deliverable.id),
            "filename": filename,
            "size": len(file_content),
        }

    except TERDeliverable.DoesNotExist:
        logger.error("Deliverable not found: %s", deliverable_id)
        return {
            "success": False,
            "error": f"Deliverable not found: {deliverable_id}",
        }
    except Exception as e:
        logger.exception("Error processing deliverable upload: %s", e)

        # Update status to failed
        try:
            deliverable = TERDeliverable.objects.get(id=deliverable_uuid)
            deliverable.upload_status = UploadStatus.FAILED
            deliverable.upload_error = str(e)
            deliverable.save(update_fields=["upload_status", "upload_error", "modified"])
        except TERDeliverable.DoesNotExist:
            pass

        # Retry on failure
        raise self.retry(exc=e, countdown=60)


@shared_task
def cleanup_failed_uploads() -> dict:
    """
    Cleanup deliverables with failed uploads older than 24 hours.

    This periodic task removes orphaned deliverable records
    where the upload failed and was never retried.

    Returns:
        Dict with cleanup results
    """
    from datetime import timedelta

    from django.utils import timezone

    from backend_django.ter.models import TERDeliverable, UploadStatus

    cutoff = timezone.now() - timedelta(hours=24)

    failed_deliverables = TERDeliverable.objects.filter(
        upload_status=UploadStatus.FAILED,
        created__lt=cutoff,
    )

    count = failed_deliverables.count()

    for deliverable in failed_deliverables:
        logger.info("Cleaning up failed deliverable: %s", deliverable.id)
        if deliverable.file:
            deliverable.file.delete(save=False)
        deliverable.delete()

    logger.info("Cleaned up %d failed deliverables", count)

    return {
        "success": True,
        "cleaned_up": count,
    }
