from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import AcademicProject
from .models import Attachment


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ["original_filename", "owner", "content_type", "size", "created"]
    list_filter = ["content_type", "created"]
    search_fields = ["original_filename", "owner__email"]
    readonly_fields = ["created", "modified", "size", "content_type"]
    raw_id_fields = ["owner"]


@admin.register(AcademicProject)
class AcademicProjectAdmin(admin.ModelAdmin):
    list_display = ["subject", "student", "project_type", "start_date", "end_date"]
    list_filter = ["project_type", "start_date", "end_date"]
    search_fields = ["subject", "student__email", "referent__email", "supervisor__email"]
    raw_id_fields = ["student", "referent", "supervisor"]
    filter_horizontal = ["files"]
    fieldsets = (
        (None, {"fields": ("subject", "project_type")}),
        (_("People"), {"fields": ("student", "referent", "supervisor")}),
        (_("Dates"), {"fields": ("start_date", "end_date")}),
        (_("Files"), {"fields": ("files",)}),
    )
