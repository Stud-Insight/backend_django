from django.contrib import admin

from .models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("notification_type", "title", "recipient", "is_read", "created")
    list_filter = ("notification_type", "is_read", "created")
    search_fields = ("title", "message", "recipient__email")
    readonly_fields = ("id", "created", "modified")
    raw_id_fields = ("recipient",)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "email_messages", "email_assignments", "email_stages", "email_groups")
    list_filter = ("email_messages", "email_assignments", "email_stages", "email_groups")
    search_fields = ("user__email",)
    raw_id_fields = ("user",)
