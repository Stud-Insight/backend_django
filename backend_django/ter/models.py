from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


# -------------------------
# TER
# -------------------------
class TER(models.Model):
	class Status(models.TextChoices):
		DRAFT = "DRAFT", "Draft"
		OPEN = "OPEN", "Open"
		EN_COURS = "EN_COURS", "In progress"
		CLOSED = "CLOSED", "Closed"

	title = models.CharField(max_length=255)
	code = models.CharField(max_length=50, unique=True)
	year = models.PositiveIntegerField()

	status = models.CharField(
		max_length=20,
		choices=Status.choices,
		default=Status.DRAFT,
	)

	start_date = models.DateField()
	end_date = models.DateField()
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-year", "title"]

	def __str__(self) -> str:
		return f"{self.title} ({self.year})"


# -------------------------
# TER NOTATION
# -------------------------
class TERNotation(models.Model):
	ter = models.ForeignKey(
		TER,
		on_delete=models.CASCADE,
		related_name="notation",
	)

	title = models.CharField(max_length=255)
	max_notation = models.PositiveIntegerField()
	coef = models.FloatField()

	def __str__(self) -> str:
		return f"{self.title} – {self.ter.code}"


# -------------------------
# TER PROJECT
# -------------------------
class TERProject(models.Model):
	class Status(models.TextChoices):
		DRAFT = "DRAFT", "Draft"
		PUBLISHED = "PUBLISHED", "Published"
		ARCHIVED = "ARCHIVED", "Archived"

	ter = models.ForeignKey(
		TER,
		on_delete=models.CASCADE,
		related_name="projects",
	)

	title = models.CharField(max_length=255)
	description = models.TextField()

	authors = models.ManyToManyField(
		User,
		related_name="ter_projects",
	)

	languages = models.JSONField(default=list, blank=True)
	tasks = models.JSONField(default=list, blank=True)

	min_person = models.PositiveIntegerField()
	max_person = models.PositiveIntegerField()

	status = models.CharField(
		max_length=20,
		choices=Status.choices,
		default=Status.DRAFT,
	)

	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self) -> str:
		return self.title


# -------------------------
# TER GROUP
# -------------------------
class TERGroup(models.Model):
	ter = models.ForeignKey(
		TER,
		on_delete=models.CASCADE,
		related_name="groups",
	)

	title = models.CharField(max_length=255)

	leader = models.ForeignKey(
		User,
		on_delete=models.PROTECT,
		related_name="led_ter_groups",
	)

	members = models.ManyToManyField(
		User,
		related_name="ter_groups",
	)

	project = models.ForeignKey(
		TERProject,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="assigned_groups",
	)

	correcteur = models.ForeignKey(
		User,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="corrected_ter_groups",
	)

	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		unique_together = ("ter", "title")

	def __str__(self) -> str:
		return self.title


# -------------------------
# GROUP OBJECTIVE
# -------------------------
class GroupObjective(models.Model):
	group = models.ForeignKey(
		TERGroup,
		on_delete=models.CASCADE,
		related_name="objectives",
	)

	title = models.CharField(max_length=255)
	done = models.BooleanField(default=False)

	def __str__(self) -> str:
		return f"{self.title} ({self.group.title})"

