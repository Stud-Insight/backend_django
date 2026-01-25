"""
RGPD (GDPR) compliance module for personal data export and account deletion.

This module implements:
- Personal data export (Article 20 - Right to data portability)
- Account deletion with anonymization (Article 17 - Right to erasure)
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from django.contrib.auth.models import Group
from django.db import transaction

from backend_django.users.models import User

logger = logging.getLogger(__name__)


def collect_user_data(user: User) -> dict[str, Any]:
    """
    Collect all personal data for a user for RGPD export.

    Returns a dictionary containing:
    - Profile information
    - Groups/roles
    - Conversations and messages
    - Projects (as student, referent, supervisor)
    - Attachments
    - Proposals and applications
    """
    data: dict[str, Any] = {
        "export_date": datetime.now().isoformat(),
        "export_version": "1.0",
        "user_id": str(user.id),
    }

    # Profile information
    data["profile"] = {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "date_joined": user.date_joined.isoformat() if user.date_joined else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "avatar": user.avatar.url if user.avatar else None,
    }

    # Groups/Roles
    data["groups"] = [
        {"id": g.id, "name": g.name}
        for g in user.groups.all()
    ]

    # Conversations and messages
    data["conversations"] = []
    for conversation in user.conversations.prefetch_related("messages", "participants"):
        conv_data = {
            "id": str(conversation.id),
            "name": conversation.name,
            "is_group": conversation.is_group,
            "created": conversation.created.isoformat(),
            "participants": [
                {"id": str(p.id), "email": p.email, "name": p.get_full_name()}
                for p in conversation.participants.all()
            ],
            "messages": [],
        }

        # Messages sent by this user in this conversation
        for message in conversation.messages.filter(sender=user):
            conv_data["messages"].append({
                "id": str(message.id),
                "content": message.content,
                "created": message.created.isoformat(),
            })

        data["conversations"].append(conv_data)

    # Projects as student
    data["projects_as_student"] = []
    for project in user.projects_as_student.all():
        data["projects_as_student"].append({
            "id": str(project.id),
            "subject": project.subject,
            "project_type": project.project_type,
            "status": project.status,
            "description": project.description,
            "academic_year": project.academic_year,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
            "company_name": project.company_name,
            "created": project.created.isoformat(),
        })

    # Projects as referent
    data["projects_as_referent"] = []
    for project in user.projects_as_referent.all():
        data["projects_as_referent"].append({
            "id": str(project.id),
            "subject": project.subject,
            "project_type": project.project_type,
            "status": project.status,
            "academic_year": project.academic_year,
            "student_email": project.student.email if project.student else None,
        })

    # Projects as supervisor
    data["projects_as_supervisor"] = []
    for project in user.projects_as_supervisor.all():
        data["projects_as_supervisor"].append({
            "id": str(project.id),
            "subject": project.subject,
            "project_type": project.project_type,
            "status": project.status,
            "academic_year": project.academic_year,
            "student_email": project.student.email if project.student else None,
        })

    # Attachments (files owned by user)
    data["attachments"] = []
    for attachment in user.attachments.all():
        data["attachments"].append({
            "id": str(attachment.id),
            "original_filename": attachment.original_filename,
            "content_type": attachment.content_type,
            "size": attachment.size,
            "created": attachment.created.isoformat(),
            "file_url": attachment.file.url if attachment.file else None,
        })

    # Proposals created by user
    data["proposals_created"] = []
    for proposal in user.created_proposals.all():
        data["proposals_created"].append({
            "id": str(proposal.id),
            "title": proposal.title,
            "description": proposal.description,
            "project_type": proposal.project_type,
            "status": proposal.status,
            "academic_year": proposal.academic_year,
            "created": proposal.created.isoformat(),
        })

    # Proposals supervised by user
    data["proposals_supervised"] = []
    for proposal in user.supervised_proposals.all():
        data["proposals_supervised"].append({
            "id": str(proposal.id),
            "title": proposal.title,
            "project_type": proposal.project_type,
            "status": proposal.status,
            "academic_year": proposal.academic_year,
        })

    # Proposal applications
    data["proposal_applications"] = []
    for application in user.proposal_applications.select_related("proposal"):
        data["proposal_applications"].append({
            "id": str(application.id),
            "proposal_title": application.proposal.title,
            "motivation": application.motivation,
            "status": application.status,
            "created": application.created.isoformat(),
        })

    return data


def export_user_data_json(user: User) -> str:
    """
    Export all user data as a JSON string.

    Args:
        user: The user whose data to export

    Returns:
        JSON string containing all user data
    """
    data = collect_user_data(user)
    return json.dumps(data, indent=2, ensure_ascii=False)


@transaction.atomic
def anonymize_user(user: User, deleted_by: User | None = None) -> dict[str, Any]:
    """
    Anonymize a user's personal data for RGPD deletion.

    This function:
    1. Replaces personal identifiers with anonymous placeholders
    2. Removes the user's avatar
    3. Removes the user from groups
    4. Anonymizes messages content (optional - keeps structure for other participants)
    5. Deactivates the account

    Academic records (projects, proposals) are preserved but with anonymized identifiers.

    Args:
        user: The user to anonymize
        deleted_by: The admin who performed the deletion (for audit)

    Returns:
        Dictionary with anonymization summary
    """
    original_email = user.email
    anonymized_id = f"deleted_{uuid.uuid4().hex[:8]}"

    summary = {
        "user_id": str(user.id),
        "original_email": original_email,
        "anonymized_at": datetime.now().isoformat(),
        "deleted_by": str(deleted_by.id) if deleted_by else None,
        "actions": [],
    }

    # Anonymize profile
    user.email = f"{anonymized_id}@deleted.studinsight.local"
    user.first_name = "Utilisateur"
    user.last_name = "Supprimé"
    user.is_active = False
    user.set_unusable_password()

    # Remove avatar
    if user.avatar:
        user.avatar.delete(save=False)
        user.avatar = None
        summary["actions"].append("avatar_deleted")

    user.save()
    summary["actions"].append("profile_anonymized")

    # Remove from all groups
    groups_count = user.groups.count()
    user.groups.clear()
    summary["actions"].append(f"removed_from_{groups_count}_groups")

    # Anonymize sent messages (replace content with placeholder)
    messages_count = user.sent_messages.count()
    user.sent_messages.update(content="[Message supprimé - Compte RGPD]")
    summary["actions"].append(f"anonymized_{messages_count}_messages")

    # Remove from conversations (but keep conversation structure for other participants)
    conversations_count = user.conversations.count()
    for conversation in user.conversations.all():
        # Only remove from 1-on-1 conversations
        if not conversation.is_group and conversation.participants.count() <= 2:
            conversation.delete()
        else:
            conversation.participants.remove(user)
    summary["actions"].append(f"removed_from_{conversations_count}_conversations")

    # Delete user's attachments/files
    attachments_count = user.attachments.count()
    for attachment in user.attachments.all():
        if attachment.file:
            attachment.file.delete(save=False)
        attachment.delete()
    summary["actions"].append(f"deleted_{attachments_count}_attachments")

    # Anonymize proposals created by user
    proposals_count = user.created_proposals.count()
    # Keep proposals but they're now linked to anonymized user
    summary["actions"].append(f"anonymized_{proposals_count}_created_proposals")

    # Delete proposal applications
    applications_count = user.proposal_applications.count()
    user.proposal_applications.all().delete()
    summary["actions"].append(f"deleted_{applications_count}_proposal_applications")

    # Projects as student - anonymize but keep academic record
    projects_student_count = user.projects_as_student.count()
    # The student FK will now point to an anonymized user
    summary["actions"].append(f"anonymized_{projects_student_count}_projects_as_student")

    # Clear referent/supervisor relationships on projects
    referent_count = user.projects_as_referent.count()
    user.projects_as_referent.update(referent=None)
    summary["actions"].append(f"cleared_{referent_count}_referent_relationships")

    supervisor_count = user.projects_as_supervisor.count()
    user.projects_as_supervisor.update(supervisor=None)
    summary["actions"].append(f"cleared_{supervisor_count}_supervisor_relationships")

    # Clear supervisor relationships on proposals
    proposal_supervisor_count = user.supervised_proposals.count()
    user.supervised_proposals.update(supervisor=None)
    summary["actions"].append(f"cleared_{proposal_supervisor_count}_proposal_supervisor_relationships")

    # Remove email addresses from allauth
    try:
        from allauth.account.models import EmailAddress
        email_count = EmailAddress.objects.filter(user=user).count()
        EmailAddress.objects.filter(user=user).delete()
        summary["actions"].append(f"deleted_{email_count}_email_addresses")
    except Exception as e:
        logger.warning(f"Could not delete email addresses: {e}")

    logger.info(
        f"User {original_email} anonymized by {deleted_by.email if deleted_by else 'system'}. "
        f"Actions: {', '.join(summary['actions'])}"
    )

    return summary


def can_delete_user(user: User, requester: User) -> tuple[bool, str]:
    """
    Check if a user can be deleted.

    Args:
        user: The user to delete
        requester: The user requesting the deletion

    Returns:
        Tuple of (can_delete, reason)
    """
    # Cannot delete yourself
    if user.id == requester.id:
        return False, "Vous ne pouvez pas supprimer votre propre compte."

    # Only superusers can delete other superusers
    if user.is_superuser and not requester.is_superuser:
        return False, "Seul un superutilisateur peut supprimer un autre superutilisateur."

    # Staff can only be deleted by superusers
    if user.is_staff and not requester.is_superuser:
        return False, "Seul un superutilisateur peut supprimer un membre du staff."

    return True, ""
