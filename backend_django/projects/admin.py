from django.contrib import admin

from .models import Attachment


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ["original_filename", "owner", "content_type", "size", "created"]
    list_filter = ["content_type", "created"]
    search_fields = ["original_filename", "owner__email"]
    readonly_fields = ["created", "modified", "size", "content_type"]
    raw_id_fields = ["owner"]
