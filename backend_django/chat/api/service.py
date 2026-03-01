"""
Chat service functions for messaging permissions and group chats.
"""

from django.db import models

from backend_django.chat.models import Conversation
from backend_django.groups.models import Group, GroupStatus


def get_or_create_academic_chat(group_instance):
    """
    Récupère ou crée la conversation entre le groupe d'étudiants
    et l'encadrant du sujet assigné.

    Args:
        group_instance: Group with assigned_subject

    Returns:
        Conversation or None if no subject/professor assigned
    """
    subject = group_instance.assigned_subject
    if not subject or not subject.professor:
        return None

    encadrant = subject.professor
    participants = list(group_instance.members.all())
    participants.append(encadrant)

    # Use a unique name to find existing conversation
    conv_name = f"TER: {group_instance.name}"

    conv, created = Conversation.objects.get_or_create(
        name=conv_name,
        is_group=True,
    )

    if created:
        conv.participants.set(participants)
        conv.save()

    return conv


def get_role_data(user):
    """
    Get role information for a user.

    Returns:
        dict with boolean flags for each role
    """
    return {
        "is_respo_ter": user.groups.filter(name="Respo TER").exists(),
        "is_respo_stage": user.groups.filter(name="Respo Stage").exists(),
        "is_etudiant": user.groups.filter(name="Étudiant").exists(),
        "is_encadrant": user.groups.filter(name="Encadrant").exists(),
        "is_externe": user.groups.filter(name="Externe").exists(),
        "is_admin": user.groups.filter(name="Admin").exists(),
    }


def can_users_message_each_other(user_a, user_b):
    """
    Vérifie les droits de communication avec cloisonnement strict par rôle et type de projet.

    Rules:
    - Admin peut parler à tout le monde
    - Respo TER peut parler aux encadrants et étudiants TER
    - Respo Stage peut parler aux externes et étudiants Stage
    - Étudiant peut parler à son encadrant (si groupe clôturé avec sujet)
    - Étudiant peut parler à son externe (si stage assigné)

    Returns:
        bool: True if users can message each other
    """
    role_a = get_role_data(user_a)
    role_b = get_role_data(user_b)

    # 1. Bypass Admin: l'Admin système peut parler à tout le monde
    if role_a["is_admin"] or role_b["is_admin"]:
        return True

    # 2. Logique pour les Responsables (Cloisonnement strict)
    # Cas: Un Respo TER veut parler à quelqu'un
    if role_a["is_respo_ter"] or role_b["is_respo_ter"]:
        # Identify who is respo and who is the other
        if role_a["is_respo_ter"]:
            autre_role = role_b
            autre_user = user_b
        else:
            autre_role = role_a
            autre_user = user_a

        # Le Respo TER peut parler aux Encadrants ou aux Étudiants de type TER
        if autre_role["is_encadrant"]:
            return True
        if Group.objects.filter(project_type="TER", members=autre_user).exists():
            return True
        return False

    # Cas: Un Respo Stage veut parler à quelqu'un
    if role_a["is_respo_stage"] or role_b["is_respo_stage"]:
        # Identify who is respo and who is the other
        if role_a["is_respo_stage"]:
            autre_role = role_b
            autre_user = user_b
        else:
            autre_role = role_a
            autre_user = user_a

        # Le Respo Stage peut parler aux Externes ou aux Étudiants de type Stage
        if autre_role["is_externe"]:
            return True
        if Group.objects.filter(project_type="Stage", members=autre_user).exists():
            return True
        return False

    # 3. Logique pour les binômes Projet (Étudiant <-> Encadrant/Externe)
    # On cherche les groupes clôturés pour valider la relation directe
    closed_groups = Group.objects.filter(status=GroupStatus.CLOTURE)

    for group in closed_groups:
        if group.project_type == "TER" and group.assigned_subject:
            # Vérifie la liaison Étudiant <-> Encadrant
            user_a_is_member = group.is_member(user_a)
            user_b_is_member = group.is_member(user_b)
            user_a_is_prof = group.assigned_subject.professor_id == user_a.id
            user_b_is_prof = group.assigned_subject.professor_id == user_b.id

            # One is member, one is professor
            if (user_a_is_member and user_b_is_prof) or (user_b_is_member and user_a_is_prof):
                return True

        elif group.project_type == "Stage" and group.assigned_offer:
            # Vérifie la liaison Étudiant <-> Externe
            user_a_is_member = group.is_member(user_a)
            user_b_is_member = group.is_member(user_b)

            contact = group.assigned_offer.contact_person
            if contact:
                user_a_is_contact = contact.id == user_a.id
                user_b_is_contact = contact.id == user_b.id

                # One is member, one is contact
                if (user_a_is_member and user_b_is_contact) or (user_b_is_member and user_a_is_contact):
                    return True

    return False


def can_student_message_user(student, other_user):
    """
    Check if a student can message another user.
    Wrapper around can_users_message_each_other for clarity.
    """
    return can_users_message_each_other(student, other_user)
