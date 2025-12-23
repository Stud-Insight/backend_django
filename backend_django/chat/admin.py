from django.contrib import admin

from .models import Conversation
from .models import Message


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "is_group", "created", "modified"]
    list_filter = ["is_group", "created"]
    search_fields = ["name", "participants__email"]
    filter_horizontal = ["participants"]
    readonly_fields = ["id", "created", "modified"]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "sender", "content_preview", "created"]
    list_filter = ["created"]
    search_fields = ["content", "sender__email"]
    readonly_fields = ["id", "created", "modified"]

    def content_preview(self, obj):
        return obj.content[:50] + "..." if len(obj.content) > 50 else obj.content

    content_preview.short_description = "Content"
