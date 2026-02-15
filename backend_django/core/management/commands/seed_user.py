from django.contrib.auth.models import Group as AuthGroup
from django.core.management.base import BaseCommand
from backend_django.core.roles import Role
from backend_django.users.models import User


class Command(BaseCommand):
    help = "Seed demo users"

    def handle(self, *args, **options):
        self.stdout.write("Creating demo users...")

        self.create_role_groups()

        # ======================
        # ADMIN
        # ======================
        self.create_user(
            email="admin@exemple.fr",
            first_name="Admin",
            last_name="System",
            role=Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )

        # ======================
        # RESPO TER
        # ======================
        self.create_user(
            email="respoter@exemple.fr",
            first_name="Claire",
            last_name="Martin",
            role=Role.RESPO_TER,
            is_staff=True,
        )

        # ======================
        # ENCADRANTS
        # ======================
        self.create_user(
            email="prof1@exemple.fr",
            first_name="Jean",
            last_name="Dupont",
            role=Role.ENCADRANT,
        )

        self.create_user(
            email="prof2@exemple.fr",
            first_name="Marie",
            last_name="Martin",
            role=Role.ENCADRANT,
        )

        self.create_user(
            email="prof3@exemple.fr",
            first_name="Pierre",
            last_name="Bernard",
            role=Role.ENCADRANT,
        )

        # ======================
        # EXTERNE
        # ======================
        self.create_user(
            email="externe@example.com",
            first_name="Lucas",
            last_name="Morel",
            role=Role.EXTERNE,
            company="TechCorp",
        )

        # ======================
        # STUDENTS
        # ======================
        students_data = [
            ("alice.durand@etu.exemple.fr", "Alice", "Durand"),
            ("bob.petit@etu.exemple.fr", "Bob", "Petit"),
            ("claire.moreau@etu.exemple.fr", "Claire", "Moreau"),
            ("david.roux@etu.exemple.fr", "David", "Roux"),
            ("emma.leroy@etu.exemple.fr", "Emma", "Leroy"),
            ("felix.garcia@etu.exemple.fr", "Felix", "Garcia"),
            ("gabrielle.thomas@etu.exemple.fr", "Gabrielle", "Thomas"),
            ("hugo.robert@etu.exemple.fr", "Hugo", "Robert"),
        ]

        for email, first, last in students_data:
            self.create_user(
                email=email,
                first_name=first,
                last_name=last,
                role=Role.ETUDIANT,
            )

        self.stdout.write(self.style.SUCCESS("Demo users created successfully!"))
        self.stdout.write("Default password: 123")

    # ======================
    # HELPERS
    # ======================

    def create_role_groups(self):
        for role in Role:
            AuthGroup.objects.get_or_create(name=role.value)
        self.stdout.write("Role groups verified")

    def create_user(
        self,
        email,
        first_name,
        last_name,
        *,
        role=None,
        is_staff=False,
        is_superuser=False,
        company=None,
    ):
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
                "is_staff": is_staff,
                "is_superuser": is_superuser,
                "company_name": company or "",
            },
        )

        # If user already exists, update important fields
        if not created:
            user.first_name = first_name
            user.last_name = last_name
            user.is_staff = is_staff
            user.is_superuser = is_superuser
            user.company_name = company or ""
            user.save()

        # Ensure password exists (only set if new)
        if created:
            user.set_password("123")
            user.save()

        # Ensure role group is assigned (even if user already existed)
        if role:
            group, _ = AuthGroup.objects.get_or_create(name=role.value)
            user.groups.add(group)

        if created:
            self.stdout.write(f"  Created user: {email}")
        else:
            self.stdout.write(f"  Verified user: {email}")

        return user
