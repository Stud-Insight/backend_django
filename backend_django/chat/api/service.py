from django.db import models
from backend_django.chat.models import Conversation
from backend_django.groups.models import Group, GroupStatus

def get_or_create_academic_chat(group_instance):
    """
    Récupère ou crée la conversation entre le groupe d'étudiants 
    et l'encadrant du sujet assigné.
    """
    subject = group_instance.assigned_subject
    if not subject or not subject.professor: # 'owner' ou le champ qui désigne l'encadrant
        return None
    
    encadrant = subject.professor

    participants = list(group_instance.members.all())
    participants.append(encadrant)
    
    
    conv, created = Conversation.objects.get_or_create(
        name=f"Chat : {group_instance.name}",
        is_group=True,
    )
    
    if created:
        conv.participants.set(participants)
        conv.save()
        
    return conv


def can_users_message_each_other(user_a, user_b):
    """
    Vérifie les droits de communication avec cloisonnement strict par rôle et type de projet.
    """
    # 1. Bypass Admin : l'Admin système peut parler à tout le monde
    if user_a.groups.filter(name="Admin").exists() or user_b.groups.filter(name="Admin").exists():
        return True

    # On identifie qui est qui pour simplifier la logique
    def get_role_data(u):
        return {
            "is_respo_ter": u.groups.filter(name="Respo TER").exists(),
            "is_respo_stage": u.groups.filter(name="Respo Stage").exists(),
            "is_etudiant": u.groups.filter(name="Étudiant").exists(),
            "is_encadrant": u.groups.filter(name="Encadrant").exists(),
            "is_externe": u.groups.filter(name="Externe").exists(),
        }

    role_a = get_role_data(user_a)
    role_b = get_role_data(user_b)

    # 2. Logique pour les Responsables (Cloisonnement strict)
    # ------------------------------------------------------
    # Cas : Un Respo TER veut parler à quelqu'un
    if role_a["is_respo_ter"] or role_b["is_respo_ter"]:
        respo = user_a if role_a["is_respo_ter"] else user_b
        autre = user_b if role_a["is_respo_ter"] else user_a
        
        # Le Respo TER peut parler aux Encadrants ou aux Étudiants de type TER
        return Group.objects.filter(project_type="TER", members=autre).exists() or role_autre["is_encadrant"]

    # Cas : Un Respo Stage veut parler à quelqu'un
    if role_a["is_respo_stage"] or role_b["is_respo_stage"]:
        respo = user_a if role_a["is_respo_stage"] else user_b
        autre = user_b if role_a["is_respo_stage"] else user_a
        
        # Le Respo Stage peut parler aux Externes ou aux Étudiants de type Stage
        return Group.objects.filter(project_type="Stage", members=autre).exists() or role_autre["is_externe"]


    # 3. Logique pour les binômes Projet (Étudiant <-> Encadrant/Externe)
    # ------------------------------------------------------------------
    # On cherche les groupes communs clôturés pour valider la relation directe
    user_groups = Group.objects.filter(status=GroupStatus.CLOTURE).filter(
        models.Q(members=user_a) | models.Q(members=user_b)
    )

    for group in user_groups:
        if group.project_type == "TER":
            if group.assigned_subject:
                # Vérifie la liaison Étudiant <-> Encadrant
                is_student = group.is_member(user_a) or group.is_member(user_b)
                is_encadrant = (group.assigned_subject.professor == user_a or group.assigned_subject.professor == user_b)
                if is_student and is_encadrant:
                    return True

        elif group.project_type == "Stage":
            if group.assigned_offer:
                # Vérifie la liaison Étudiant <-> Externe
                is_student = group.is_member(user_a) or group.is_member(user_b)
                is_externe = (group.assigned_offer.contact_person == user_a or group.assigned_offer.contact_person == user_b)
                if is_student and is_externe:
                    return True
        
    return False