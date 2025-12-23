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
        response={201: ConversationSchema, 400: ErrorSchema, 401: ErrorSchema},
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

        conv = get_object_or_404(Conversation, id=conversation_id)

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

        # Mark fetched messages as read
        for msg in messages.exclude(sender=request.user):
            msg.read_by.add(request.user)

        return 200, [message_to_schema(m, request.user) for m in messages]

    @http_post(
        "/conversations/{conversation_id}/messages",
        response={201: MessageSentSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="chat_messages_send",
    )
    def send_message(self, request: HttpRequest, conversation_id: UUID, data: SendMessageSchema):
        """Send a message to a conversation."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not data.content.strip():
            return BadRequestError("Le message ne peut pas être vide.").to_response()

        conv = get_object_or_404(Conversation, id=conversation_id)

        if not conv.participants.filter(id=request.user.id).exists():
            return PermissionDeniedError().to_response()

        message = Message.objects.create(
            conversation=conv,
            sender=request.user,
            content=data.content.strip(),
        )

        # Update conversation modified time
        conv.save()

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
