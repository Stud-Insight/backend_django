"""
Seed command to populate database with demo data for frontend development.

Usage:
    python manage.py seed_demo
    python manage.py seed_demo --clear  # Clear existing demo data first
"""

import logging
from datetime import date, timedelta

from django.contrib.auth.models import Group as AuthGroup
from django.core.management.base import BaseCommand

from backend_django.core.roles import Role
from backend_django.groups.models import Group, GroupStatus
from backend_django.ter.models import PeriodStatus, SubjectStatus, TERPeriod, TERSubject
from backend_django.users.models import User

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Seed database with demo data for frontend development"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing demo data before seeding",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.clear_demo_data()

        self.stdout.write("Creating demo data...")

        # Create role groups if they don't exist
        self.create_role_groups()

        # Create users
        respo_ter = self.create_user(
            "respo.ter@univ.fr", "Responsable", "TER", is_staff=True, role=Role.RESPO_TER
        )
        encadrant1 = self.create_user(
            "prof.dupont@univ.fr", "Jean", "Dupont", role=Role.ENCADRANT
        )
        encadrant2 = self.create_user(
            "prof.martin@univ.fr", "Marie", "Martin", role=Role.ENCADRANT
        )
        encadrant3 = self.create_user(
            "prof.bernard@univ.fr", "Pierre", "Bernard", role=Role.ENCADRANT
        )

        # Create students
        students = []
        student_data = [
            ("alice.durand@etu.univ.fr", "Alice", "Durand"),
            ("bob.petit@etu.univ.fr", "Bob", "Petit"),
            ("claire.moreau@etu.univ.fr", "Claire", "Moreau"),
            ("david.roux@etu.univ.fr", "David", "Roux"),
            ("emma.leroy@etu.univ.fr", "Emma", "Leroy"),
            ("felix.garcia@etu.univ.fr", "Felix", "Garcia"),
            ("gabrielle.thomas@etu.univ.fr", "Gabrielle", "Thomas"),
            ("hugo.robert@etu.univ.fr", "Hugo", "Robert"),
            ("isabelle.richard@etu.univ.fr", "Isabelle", "Richard"),
            ("julien.simon@etu.univ.fr", "Julien", "Simon"),
            ("karine.laurent@etu.univ.fr", "Karine", "Laurent"),
            ("lucas.michel@etu.univ.fr", "Lucas", "Michel"),
        ]
        for email, first_name, last_name in student_data:
            student = self.create_user(email, first_name, last_name, role=Role.ETUDIANT)
            students.append(student)

        # Create TER periods
        today = date.today()

        # Period 1: Open (current)
        ter_open = TERPeriod.objects.create(
            name="TER 2025-2026 S1",
            academic_year="2025-2026",
            status=PeriodStatus.OPEN,
            group_formation_start=today - timedelta(days=10),
            group_formation_end=today + timedelta(days=20),
            subject_selection_start=today + timedelta(days=21),
            subject_selection_end=today + timedelta(days=50),
            assignment_date=today + timedelta(days=55),
            project_start=today + timedelta(days=60),
            project_end=today + timedelta(days=180),
            min_group_size=2,
            max_group_size=4,
        )
        self.stdout.write(f"  Created TER period: {ter_open.name} (OPEN)")

        # Period 2: Draft (next semester)
        ter_draft = TERPeriod.objects.create(
            name="TER 2025-2026 S2",
            academic_year="2025-2026",
            status=PeriodStatus.DRAFT,
            group_formation_start=today + timedelta(days=180),
            group_formation_end=today + timedelta(days=210),
            subject_selection_start=today + timedelta(days=211),
            subject_selection_end=today + timedelta(days=240),
            assignment_date=today + timedelta(days=245),
            project_start=today + timedelta(days=250),
            project_end=today + timedelta(days=370),
            min_group_size=2,
            max_group_size=4,
        )
        self.stdout.write(f"  Created TER period: {ter_draft.name} (DRAFT)")

        # Period 3: Closed (previous year)
        ter_closed = TERPeriod.objects.create(
            name="TER 2024-2025 S2",
            academic_year="2024-2025",
            status=PeriodStatus.CLOSED,
            group_formation_start=today - timedelta(days=200),
            group_formation_end=today - timedelta(days=170),
            subject_selection_start=today - timedelta(days=169),
            subject_selection_end=today - timedelta(days=140),
            assignment_date=today - timedelta(days=135),
            project_start=today - timedelta(days=130),
            project_end=today - timedelta(days=10),
            min_group_size=2,
            max_group_size=4,
        )
        self.stdout.write(f"  Created TER period: {ter_closed.name} (CLOSED)")

        # Enroll students in open period
        ter_open.enrolled_students.add(*students)
        self.stdout.write(f"  Enrolled {len(students)} students in {ter_open.name}")

        # Create TER subjects for open period
        subjects_data = [
            {
                "title": "Developpement d'un chatbot IA avec RAG",
                "description": "Conception et implementation d'un chatbot intelligent utilisant la technique de Retrieval-Augmented Generation (RAG) pour repondre aux questions sur une base documentaire.",
                "domain": "IA/ML",
                "prerequisites": "Python, bases en NLP, notions de deep learning",
                "professor": encadrant1,
                "max_groups": 2,
            },
            {
                "title": "Application mobile de suivi sportif",
                "description": "Developpement d'une application mobile cross-platform pour le suivi d'activites sportives avec synchronisation cloud et visualisation de statistiques.",
                "domain": "Mobile",
                "prerequisites": "React Native ou Flutter, API REST",
                "professor": encadrant2,
                "max_groups": 1,
            },
            {
                "title": "Plateforme de detection de fake news",
                "description": "Creation d'un outil d'analyse automatique d'articles de presse pour detecter les potentielles fausses informations en utilisant le NLP et le fact-checking.",
                "domain": "IA/ML",
                "prerequisites": "Python, NLP, web scraping",
                "professor": encadrant1,
                "max_groups": 1,
            },
            {
                "title": "Systeme de recommandation musical",
                "description": "Implementation d'un algorithme de recommandation musicale base sur l'analyse des preferences utilisateur et le filtrage collaboratif.",
                "domain": "IA/ML",
                "prerequisites": "Python, bases de donnees, statistiques",
                "professor": encadrant3,
                "max_groups": 2,
            },
            {
                "title": "Dashboard IoT pour maison connectee",
                "description": "Conception d'une interface web pour la gestion centralisee d'appareils IoT domestiques avec monitoring en temps reel.",
                "domain": "Web/IoT",
                "prerequisites": "JavaScript, MQTT, bases en electronique",
                "professor": encadrant2,
                "max_groups": 1,
            },
            {
                "title": "Analyse de vulnerabilites web automatisee",
                "description": "Developpement d'un outil de scan de securite pour applications web detectant les failles OWASP Top 10.",
                "domain": "Securite",
                "prerequisites": "Python, securite web, HTTP/HTTPS",
                "professor": encadrant3,
                "max_groups": 1,
            },
            {
                "title": "Compilateur pour langage educatif",
                "description": "Creation d'un compilateur pour un mini-langage de programmation a visee pedagogique avec analyse syntaxique et generation de code.",
                "domain": "Systemes",
                "prerequisites": "C/C++, theorie des langages, assembleur",
                "professor": encadrant1,
                "max_groups": 1,
            },
            {
                "title": "Jeu video multijoueur en ligne",
                "description": "Developpement d'un jeu 2D multijoueur avec serveur de matchmaking et synchronisation en temps reel.",
                "domain": "Jeux",
                "prerequisites": "Unity ou Godot, reseaux, C#",
                "professor": encadrant2,
                "max_groups": 2,
            },
        ]

        for i, data in enumerate(subjects_data):
            # Alternate between validated and submitted status
            status = SubjectStatus.VALIDATED if i < 6 else SubjectStatus.SUBMITTED
            subject = TERSubject.objects.create(
                ter_period=ter_open,
                title=data["title"],
                description=data["description"],
                domain=data["domain"],
                prerequisites=data["prerequisites"],
                professor=data["professor"],
                max_groups=data["max_groups"],
                status=status,
            )
            self.stdout.write(f"  Created subject: {subject.title[:40]}... ({status})")

        # Create some groups
        # Group 1: Complete group (3 members)
        group1 = Group.objects.create(
            name="Les Codeurs Fous",
            leader=students[0],  # Alice
            ter_period=ter_open,
            project_type="ter",
        )
        group1.members.add(students[0], students[1], students[2])  # Alice, Bob, Claire
        self.stdout.write(f"  Created group: {group1.name} (3 members)")

        # Group 2: Complete group (2 members)
        group2 = Group.objects.create(
            name="Team ML",
            leader=students[3],  # David
            ter_period=ter_open,
            project_type="ter",
        )
        group2.members.add(students[3], students[4])  # David, Emma
        self.stdout.write(f"  Created group: {group2.name} (2 members)")

        # Group 3: Incomplete group (1 member - leader only)
        group3 = Group.objects.create(
            name="Solo Dev",
            leader=students[5],  # Felix
            ter_period=ter_open,
            project_type="ter",
        )
        group3.members.add(students[5])  # Felix only
        self.stdout.write(f"  Created group: {group3.name} (1 member - incomplete)")

        # Students 6-11 are solitaires (no group yet)
        solitaires = students[6:]
        self.stdout.write(f"  {len(solitaires)} students without groups (solitaires)")

        self.stdout.write(self.style.SUCCESS("\nDemo data created successfully!"))
        self.stdout.write("\nSummary:")
        self.stdout.write(f"  - 1 Respo TER: {respo_ter.email}")
        self.stdout.write(f"  - 3 Encadrants: {encadrant1.email}, {encadrant2.email}, {encadrant3.email}")
        self.stdout.write(f"  - {len(students)} Students enrolled")
        self.stdout.write(f"  - 3 TER periods (1 open, 1 draft, 1 closed)")
        self.stdout.write(f"  - 8 TER subjects (6 validated, 2 submitted)")
        self.stdout.write(f"  - 3 Groups (2 complete, 1 incomplete)")
        self.stdout.write(f"  - {len(solitaires)} Solitaires")
        self.stdout.write("\nDefault password for all users: demo123")

    def create_role_groups(self):
        """Create Django auth groups for roles."""
        for role in Role:
            AuthGroup.objects.get_or_create(name=role.value)
        self.stdout.write("  Role groups created/verified")

    def create_user(self, email, first_name, last_name, is_staff=False, role=None):
        """Create a user if not exists."""
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
                "is_staff": is_staff,
            },
        )
        if created:
            user.set_password("demo123")
            user.save()

            if role:
                try:
                    group = AuthGroup.objects.get(name=role.value)
                    user.groups.add(group)
                except AuthGroup.DoesNotExist:
                    pass

            self.stdout.write(f"  Created user: {email} ({role.value if role else 'no role'})")
        return user

    def clear_demo_data(self):
        """Clear existing demo data."""
        self.stdout.write("Clearing existing demo data...")

        # Delete groups first (due to FK constraints)
        Group.objects.filter(ter_period__name__startswith="TER 202").delete()

        # Delete subjects
        TERSubject.objects.filter(ter_period__name__startswith="TER 202").delete()

        # Delete periods
        TERPeriod.objects.filter(name__startswith="TER 202").delete()

        # Delete demo users
        demo_emails = [
            "respo.ter@univ.fr",
            "prof.dupont@univ.fr",
            "prof.martin@univ.fr",
            "prof.bernard@univ.fr",
        ]
        demo_emails += [f"{name}@etu.univ.fr" for name in [
            "alice.durand", "bob.petit", "claire.moreau", "david.roux",
            "emma.leroy", "felix.garcia", "gabrielle.thomas", "hugo.robert",
            "isabelle.richard", "julien.simon", "karine.laurent", "lucas.michel",
        ]]
        User.objects.filter(email__in=demo_emails).delete()

        self.stdout.write(self.style.WARNING("  Demo data cleared"))
