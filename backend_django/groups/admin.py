from django.contrib import admin

from .models import Group, GroupInvitation


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ["name", "leader", "status", "project_type", "member_count", "created"]
    list_filter = ["status", "project_type"]
    search_fields = ["name", "leader__email"]
    ordering = ["-created"]

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = "Members"


@admin.register(GroupInvitation)
class GroupInvitationAdmin(admin.ModelAdmin):
    list_display = ["group", "invitee", "invited_by", "status", "created"]
    list_filter = ["status"]
    search_fields = ["group__name", "invitee__email", "invited_by__email"]
    ordering = ["-created"]
