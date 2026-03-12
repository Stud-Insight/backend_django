"""
Chat API controller.
"""

from uuid import UUID

from django.db.models import Max
from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller
from ninja_extra import http_get
from ninja_extra import http_post
from ninja import File
from ninja.files import UploadedFile
from datetime import datetime

from backend_django.chat.models import Conversation
from backend_django.chat.models import Message
from backend_django.chat.schemas import ConversationDetailSchema
from backend_django.chat.schemas import ConversationSchema
from backend_django.chat.schemas import CreateConversationSchema
from backend_django.chat.schemas import MessageSchema
from backend_django.chat.schemas import MessageSentSchema
from backend_django.chat.schemas import ParticipantSchema
from backend_django.chat.schemas import SendMessageSchema
from backend_django.core.api import BaseAPI
from backend_django.core.api import IsAuthenticated
from backend_django.core.exceptions import BadRequestError
from backend_django.core.exceptions import ErrorSchema
from backend_django.core.exceptions import NotAuthenticatedError
from backend_django.core.exceptions import PermissionDeniedError
from backend_django.users.models import User
from backend_django.groups.models import Group


def user_to_participant(user: User) -> ParticipantSchema:
    """Convert a User to ParticipantSchema."""
    return ParticipantSchema(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
    )


def message_to_schema(message: Message, current_user: User) -> MessageSchema:
    """Convert a Message to MessageSchema."""
    return MessageSchema(
        id=message.id,
        sender=user_to_participant(message.sender),
        content=message.content,
        file_url=message.file.url if message.file else None, # Ajout
        file_name=message.file_name,
        created=message.created,
        is_read=message.read_by.filter(id=current_user.id).exists() or message.sender_id == current_user.id,
    )


@api_controller("/chat", tags=["Chat"], permissions=[IsAuthenticated])
class ChatController(BaseAPI):
    """API endpoints for chat functionality."""

    @http_get(
        "/conversations",
        response={200: list[ConversationSchema], 401: ErrorSchema},
        url_name="chat_conversations_list",
    )
    def list_conversations(self, request: HttpRequest):
        """List all conversations for the current user."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        conversations = (
            Conversation.objects.filter(participants=request.user)
            .annotate(last_activity=Max("messages__created"))
            .order_by("-last_activity", "-modified")
            .prefetch_related("participants", "messages")
        )

        result = []
        for conv in conversations:
            last_msg = conv.get_last_message()
            result.append(
                ConversationSchema(
                    id=conv.id,
                    name=conv.name or str(conv),
                    is_group=conv.is_group,
                    participants=[user_to_participant(p) for p in conv.participants.all()],
                    last_message=message_to_schema(last_msg, request.user) if last_msg else None,
                    unread_count=conv.messages.exclude(sender=request.user)
                    .exclude(read_by=request.user)
                    .count(),
                    created=conv.created,
                    modified=conv.modified,
                )
            )

        return 200, result

    @http_post(
        "/conversations",
        response={201: ConversationSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="chat_conversations_create",
    )
    def create_conversation(self, request: HttpRequest, data: CreateConversationSchema):
        """Create a new conversation."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not data.participant_ids:
            return BadRequestError("Au moins un participant requis.").to_response()

        # Get participants
        participants = list(User.objects.filter(id__in=data.participant_ids))
        if len(participants) != len(data.participant_ids):
            return BadRequestError("Un ou plusieurs participants introuvables.").to_response()
        
        # Check messaging permissions for 1-on-1 conversations
        if not data.is_group and not request.user.is_staff:
            other_user = participants[0]
            from backend_django.chat.api.service import can_users_message_each_other

            if not can_users_message_each_other(request.user, other_user):
                return PermissionDeniedError(
                    "Vous ne pouvez pas contacter cet utilisateur."
                ).to_response()

        # Add current user to participants
        all_participant_ids = set(data.participant_ids) | {request.user.id}

        # For 1-on-1 conversations, check if one already exists
        if not data.is_group and len(all_participant_ids) == 2:
            other_user = participants[0]  # Already fetched above
            # Find conversation with exactly these 2 participants
            # Note: Django ManyToMany COUNT annotation doesn't work correctly with filters,
            # so we check participant count separately for each candidate
            candidate_convs = Conversation.objects.filter(
                is_group=False,
                participants=request.user,
            ).filter(participants=other_user)

            existing = None
            for conv in candidate_convs:
                if conv.participants.count() == 2:
                    existing = conv
                    break
            if existing:
                last_msg = existing.get_last_message()
                # Return existing conversation
                return 201, ConversationSchema(
                    id=existing.id,
                    name=existing.name or str(existing),
                    is_group=existing.is_group,
                    participants=[user_to_participant(p) for p in existing.participants.all()],
                    last_message=message_to_schema(last_msg, request.user) if last_msg else None,
                    unread_count=existing.messages.exclude(sender=request.user).exclude(read_by=request.user).count(),
                    created=existing.created,
                    modified=existing.modified,
                )

        # Create new conversation
        conv = Conversation.objects.create(
            name=data.name if data.is_group else "",
            is_group=data.is_group,
        )
        conv.participants.add(request.user, *participants)

        return 201, ConversationSchema(
            id=conv.id,
            name=conv.name or str(conv),
            is_group=conv.is_group,
            participants=[user_to_participant(p) for p in conv.participants.all()],
            last_message=None,
            unread_count=0,
            created=conv.created,
            modified=conv.modified,
        )

    @http_get(
        "/conversations/{conversation_id}",
        response={200: ConversationDetailSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="chat_conversation_detail",
    )
    def get_conversation(self, request: HttpRequest, conversation_id: UUID):
        """Get a conversation with its messages."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        conv = get_object_or_404(
            Conversation.objects.prefetch_related("participants", "messages__sender", "messages__read_by"), 
            id=conversation_id
        )

        if not conv.participants.filter(id=request.user.id).exists():
            return PermissionDeniedError("Vous n'êtes pas participant de cette conversation.").to_response()

        # Mark all messages as read
        unread_messages = conv.messages.exclude(sender=request.user).exclude(read_by=request.user)
        for msg in unread_messages:
            msg.read_by.add(request.user)

        return ConversationDetailSchema(
            id=conv.id,
            name=conv.name or str(conv),
            is_group=conv.is_group,
            participants=[user_to_participant(p) for p in conv.participants.all()],
            messages=[message_to_schema(m, request.user) for m in conv.messages.all()],
            created=conv.created,
            modified=conv.modified,
        )

    @http_get(
        "/conversations/{conversation_id}/messages",
        response={200: list[MessageSchema], 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="chat_messages_list",
    )
    def list_messages(
        self,
        request: HttpRequest,
        conversation_id: UUID,
        before: datetime | None = None,
        after: UUID | None = None,
    ):
        """
        List messages in a conversation.
        Use 'after' parameter to get messages after a specific message ID (for polling).
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        conv = get_object_or_404(Conversation, id=conversation_id)

        if not conv.participants.filter(id=request.user.id).exists():
            return PermissionDeniedError().to_response()

        messages = conv.messages.all()

        if after:
            # Get messages after the specified message
            after_msg = conv.messages.filter(id=after).first()
            if after_msg:
                messages = messages.filter(created__gt=after_msg.created)
        
        if before:
            messages = messages.filter(created__lt=before)

        # Mark fetched messages as read
        for msg in messages.exclude(sender=request.user):
            msg.read_by.add(request.user)

        return 200, [message_to_schema(m, request.user) for m in messages]

    @http_post(
        "/conversations/{conversation_id}/messages",
        response={201: MessageSentSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="chat_messages_send",
    )
    def send_message(
        self, 
        request: HttpRequest, 
        conversation_id: UUID, 
        content: str = None, # Devient optionnel
        file: UploadedFile = File(None) # Ajout du fichier
    ):
        """Send a message (text and/or file) to a conversation."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        # On vérifie qu'il y a AU MOINS du texte ou un fichier
        if not content and not file:
            return BadRequestError("Le message ne peut pas être vide.").to_response()

        conv = get_object_or_404(Conversation, id=conversation_id)

        if not conv.participants.filter(id=request.user.id).exists():
            return PermissionDeniedError().to_response()

        # Création du message avec les nouveaux champs
        message = Message.objects.create(
            conversation=conv,
            sender=request.user,
            content=content.strip() if content else "",
            file=file,
            file_name=file.name if file else None
        )

        # Update conversation modified time
        conv.save()

        # Notify other participants
        from backend_django.notifications.services import send_bulk_notifications

        other_participants = conv.participants.exclude(id=request.user.id)
        if other_participants.exists():
            sender_name = request.user.get_full_name() or request.user.email
            send_bulk_notifications(
                recipients=list(other_participants),
                notification_type="chat.new_message",
                title="Nouveau message",
                message=f"{sender_name} vous a envoyé un message.",
                data={"conversation_id": str(conv.id), "message_id": str(message.id)},
            )

        return 201, MessageSentSchema(
            success=True,
            message=message_to_schema(message, request.user),
        )

    @http_get(
        "/users",
        response={200: list[ParticipantSchema], 401: ErrorSchema},
        url_name="chat_users_list",
    )
    def list_users(self, request: HttpRequest, search: str = ""):
        """List users available for chat (for starting new conversations)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        users = User.objects.exclude(id=request.user.id).filter(is_active=True)

        if search:
            users = users.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        users = users[:20]  # Limit results

        return 200, [user_to_participant(u) for u in users]

    @http_post(
        "/groups/{group_id}/chat",
        response={
            200: ConversationSchema,
            201: ConversationSchema,
            400: ErrorSchema,
            401: ErrorSchema,
            403: ErrorSchema,
            404: ErrorSchema,
        },
        url_name="chat_group_academic",
    )
    def get_or_create_group_chat(self, request: HttpRequest, group_id: UUID):
        """
        Get or create the academic chat between a group and its assigned subject's professor.

        Story 6.1: Étendre le chat pour messagerie Encadrant-Groupe

        Returns existing conversation or creates a new one with:
        - All group members as participants
        - The professor of the assigned subject as participant

        Only accessible to:
        - Group members
        - The professor assigned to the group's subject
        - TER admins
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(
            Group.objects.select_related("assigned_subject", "assigned_subject__professor")
            .prefetch_related("members"),
            id=group_id,
        )

        # Check permissions: must be member, professor, or admin
        is_member = group.is_member(request.user)
        is_professor = (
            group.assigned_subject
            and group.assigned_subject.professor_id == request.user.id
        )
        is_admin = request.user.is_staff or request.user.groups.filter(
            name__in=["Admin", "Respo TER"]
        ).exists()

        if not (is_member or is_professor or is_admin):
            return PermissionDeniedError(
                "Vous n'êtes pas autorisé à accéder au chat de ce groupe."
            ).to_response()

        # Check group has assigned subject with professor
        if not group.assigned_subject:
            return BadRequestError(
                "Ce groupe n'a pas de sujet assigné."
            ).to_response()

        if not group.assigned_subject.professor:
            return BadRequestError(
                "Le sujet assigné n'a pas d'encadrant."
            ).to_response()

        # Get or create the conversation
        from backend_django.chat.api.service import get_or_create_academic_chat

        conv = get_or_create_academic_chat(group)

        if not conv:
            return BadRequestError(
                "Impossible de créer la conversation."
            ).to_response()

        # Determine if it was just created (no messages yet)
        was_created = conv.messages.count() == 0
        status_code = 201 if was_created else 200

        last_msg = conv.get_last_message()
        return status_code, ConversationSchema(
            id=conv.id,
            name=conv.name or str(conv),
            is_group=conv.is_group,
            participants=[user_to_participant(p) for p in conv.participants.all()],
            last_message=message_to_schema(last_msg, request.user) if last_msg else None,
            unread_count=conv.messages.exclude(sender=request.user)
            .exclude(read_by=request.user)
            .count(),
            created=conv.created,
            modified=conv.modified,
        )
