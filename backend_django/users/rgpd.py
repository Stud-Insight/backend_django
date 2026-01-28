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
    - Student groups (Group model)
    - TER rankings and favorites
    - Stage rankings and favorites
    - Attachments
    """
    data: dict[str, Any] = {
        "export_date": datetime.now().isoformat(),
        "export_version": "2.0",
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

    # Django Groups (Roles)
    data["roles"] = [
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

    # Student Groups (new Group model)
    data["student_groups"] = []
    for group in user.student_groups.select_related("ter_period", "stage_period", "assigned_subject", "assigned_offer"):
        group_data = {
            "id": str(group.id),
            "name": group.name,
            "status": group.status,
            "is_leader": group.leader_id == user.id,
            "project_type": group.project_type,
            "created": group.created.isoformat(),
        }
        if group.ter_period:
            group_data["ter_period"] = {
                "id": str(group.ter_period.id),
                "name": group.ter_period.name,
                "academic_year": group.ter_period.academic_year,
            }
        if group.stage_period:
            group_data["stage_period"] = {
                "id": str(group.stage_period.id),
                "name": group.stage_period.name,
                "academic_year": group.stage_period.academic_year,
            }
        if group.assigned_subject:
            group_data["assigned_subject"] = {
                "id": str(group.assigned_subject.id),
                "title": group.assigned_subject.title,
            }
        if group.assigned_offer:
            group_data["assigned_offer"] = {
                "id": str(group.assigned_offer.id),
                "title": group.assigned_offer.title,
                "company_name": group.assigned_offer.company_name,
            }
        data["student_groups"].append(group_data)

    # Groups led by user
    data["groups_led"] = []
    for group in user.led_groups.all():
        data["groups_led"].append({
            "id": str(group.id),
            "name": group.name,
            "status": group.status,
            "member_count": group.members.count(),
        })

    # TER Rankings
    data["ter_rankings"] = []
    try:
        from backend_django.ter.models import TERRanking
        for ranking in TERRanking.objects.filter(group__members=user).select_related("group", "subject"):
            data["ter_rankings"].append({
                "id": str(ranking.id),
                "group_name": ranking.group.name,
                "subject_title": ranking.subject.title,
                "rank": ranking.rank,
                "created": ranking.created.isoformat(),
            })
    except Exception as e:
        logger.warning(f"Could not export TER rankings: {e}")

    # TER Favorites
    data["ter_favorites"] = []
    try:
        from backend_django.ter.models import TERFavorite
        for favorite in TERFavorite.objects.filter(student=user).select_related("subject"):
            data["ter_favorites"].append({
                "id": str(favorite.id),
                "subject_title": favorite.subject.title,
                "created": favorite.created.isoformat(),
            })
    except Exception as e:
        logger.warning(f"Could not export TER favorites: {e}")

    # Stage Rankings
    data["stage_rankings"] = []
    try:
        from backend_django.stages.models import StageRanking
        for ranking in StageRanking.objects.filter(student=user).select_related("offer"):
            data["stage_rankings"].append({
                "id": str(ranking.id),
                "offer_title": ranking.offer.title,
                "company_name": ranking.offer.company_name,
                "rank": ranking.rank,
                "created": ranking.created.isoformat(),
            })
    except Exception as e:
        logger.warning(f"Could not export Stage rankings: {e}")

    # Stage Favorites
    data["stage_favorites"] = []
    try:
        from backend_django.stages.models import StageFavorite
        for favorite in StageFavorite.objects.filter(student=user).select_related("offer"):
            data["stage_favorites"].append({
                "id": str(favorite.id),
                "offer_title": favorite.offer.title,
                "company_name": favorite.offer.company_name,
                "created": favorite.created.isoformat(),
            })
    except Exception as e:
        logger.warning(f"Could not export Stage favorites: {e}")

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

    # Group invitations received
    data["group_invitations_received"] = []
    for invitation in user.group_invitations.select_related("group"):
        data["group_invitations_received"].append({
            "id": str(invitation.id),
            "group_name": invitation.group.name,
            "status": invitation.status,
            "message": invitation.message,
            "created": invitation.created.isoformat(),
        })

    # Group invitations sent
    data["group_invitations_sent"] = []
    for invitation in user.sent_invitations.select_related("group", "invitee"):
        data["group_invitations_sent"].append({
            "id": str(invitation.id),
            "group_name": invitation.group.name,
            "invitee_email": invitation.invitee.email,
            "status": invitation.status,
            "created": invitation.created.isoformat(),
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
    3. Removes the user from Django groups (roles)
    4. Anonymizes messages content (optional - keeps structure for other participants)
    5. Removes from student groups
    6. Deletes rankings and favorites
    7. Deactivates the account

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
    user.last_name = "Supprime"
    user.is_active = False
    user.set_unusable_password()

    # Remove avatar
    if user.avatar:
        user.avatar.delete(save=False)
        user.avatar = None
        summary["actions"].append("avatar_deleted")

    user.save()
    summary["actions"].append("profile_anonymized")

    # Remove from all Django groups (roles)
    groups_count = user.groups.count()
    user.groups.clear()
    summary["actions"].append(f"removed_from_{groups_count}_roles")

    # Anonymize sent messages (replace content with placeholder)
    messages_count = user.sent_messages.count()
    user.sent_messages.update(content="[Message supprime - Compte RGPD]")
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

    # Remove from student groups
    student_groups_count = user.student_groups.count()
    for group in user.student_groups.all():
        # If user is the leader, transfer leadership or delete group
        if group.leader_id == user.id:
            other_members = group.members.exclude(id=user.id)
            if other_members.exists():
                # Transfer to first other member
                group.leader = other_members.first()
                group.save()
                summary["actions"].append(f"transferred_leadership_group_{group.id}")
            else:
                # Delete empty group
                group.delete()
                summary["actions"].append(f"deleted_empty_group_{group.id}")
                continue
        group.members.remove(user)
    summary["actions"].append(f"removed_from_{student_groups_count}_student_groups")

    # Delete led groups where no other members exist
    for group in user.led_groups.all():
        if group.members.count() == 1:
            group.delete()

    # Delete TER rankings via groups
    try:
        from backend_django.ter.models import TERRanking
        ter_ranking_count = TERRanking.objects.filter(group__leader=user).count()
        TERRanking.objects.filter(group__leader=user).delete()
        summary["actions"].append(f"deleted_{ter_ranking_count}_ter_rankings")
    except Exception as e:
        logger.warning(f"Could not delete TER rankings: {e}")

    # Delete TER favorites
    try:
        from backend_django.ter.models import TERFavorite
        ter_fav_count = TERFavorite.objects.filter(student=user).count()
        TERFavorite.objects.filter(student=user).delete()
        summary["actions"].append(f"deleted_{ter_fav_count}_ter_favorites")
    except Exception as e:
        logger.warning(f"Could not delete TER favorites: {e}")

    # Delete Stage rankings
    try:
        from backend_django.stages.models import StageRanking
        stage_ranking_count = StageRanking.objects.filter(student=user).count()
        StageRanking.objects.filter(student=user).delete()
        summary["actions"].append(f"deleted_{stage_ranking_count}_stage_rankings")
    except Exception as e:
        logger.warning(f"Could not delete Stage rankings: {e}")

    # Delete Stage favorites
    try:
        from backend_django.stages.models import StageFavorite
        stage_fav_count = StageFavorite.objects.filter(student=user).count()
        StageFavorite.objects.filter(student=user).delete()
        summary["actions"].append(f"deleted_{stage_fav_count}_stage_favorites")
    except Exception as e:
        logger.warning(f"Could not delete Stage favorites: {e}")

    # Delete group invitations
    invitations_received = user.group_invitations.count()
    user.group_invitations.all().delete()
    summary["actions"].append(f"deleted_{invitations_received}_invitations_received")

    invitations_sent = user.sent_invitations.count()
    user.sent_invitations.all().delete()
    summary["actions"].append(f"deleted_{invitations_sent}_invitations_sent")

    # Remove email addresses from allauth
    try:
        from allauth.account.models import EmailAddress
        email_count = EmailAddress.objects.filter(user=user).count()
        EmailAddress.objects.filter(user=user).delete()
        summary["actions"].append(f"deleted_{email_count}_email_addresses")
    except Exception as e:
        logger.warning(f"Could not delete email addresses: {e}")
        summary["actions"].append("failed_to_delete_email_addresses")

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
