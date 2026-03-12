import json
import time

from django.http import HttpRequest, StreamingHttpResponse
from ninja_extra import api_controller, http_get
from ninja_extra.permissions import IsAuthenticated

from backend_django.core.api.base import BaseAPI
from backend_django.core.exceptions import ErrorSchema, NotAuthenticatedError
from backend_django.notifications.models import Notification

# Maximum SSE connection duration before client must reconnect (30 minutes)
SSE_MAX_DURATION_SECONDS = 30 * 60

# SCALING NOTE: Each SSE connection holds a sync worker thread (time.sleep polling).
# This is acceptable for MVP (<50 concurrent users). For production scale, migrate to
# ASGI (Uvicorn/Daphne) with async generators, or use Redis pub/sub to avoid DB polling.


@api_controller(
    "/notifications",
    tags=["Notifications"],
    permissions=[IsAuthenticated],
)
class NotificationStreamController(BaseAPI):

    @http_get(
        "/stream",
        response={401: ErrorSchema},
        exclude_unset=True,
    )
    def notification_stream(self, request: HttpRequest):
        """
        Server-Sent Events (SSE) endpoint for real-time notifications.

        The connection auto-closes after 30 minutes; the client should reconnect.

        Frontend usage:
            const eventSource = new EventSource('/api/notifications/stream',
                                                 {withCredentials: true});
            eventSource.onmessage = (e) => handleNotification(JSON.parse(e.data));
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        user = request.user

        def event_stream():
            last_created = None
            seen_ids = set()
            heartbeat_counter = 0
            start_time = time.monotonic()
            try:
                while True:
                    # Timeout: close connection after max duration
                    elapsed = time.monotonic() - start_time
                    if elapsed >= SSE_MAX_DURATION_SECONDS:
                        yield ": timeout\n\n"
                        return

                    filters = {"recipient": user}
                    if last_created is not None:
                        filters["created__gte"] = last_created

                    notifications = Notification.objects.filter(**filters).order_by(
                        "created"
                    )

                    for notif in notifications:
                        if notif.id in seen_ids:
                            continue
                        payload = {
                            "id": str(notif.id),
                            "notification_type": notif.notification_type,
                            "title": notif.title,
                            "message": notif.message,
                            "data": notif.data,
                            "is_read": notif.is_read,
                            "read_at": notif.read_at.isoformat() if notif.read_at else None,
                            "created": notif.created.isoformat(),
                        }
                        yield f"data: {json.dumps(payload)}\n\n"
                        seen_ids.add(notif.id)
                        last_created = notif.created

                    # Heartbeat every ~15 seconds (15 / 2 = ~7 iterations)
                    heartbeat_counter += 1
                    if heartbeat_counter >= 7:
                        yield ": heartbeat\n\n"
                        heartbeat_counter = 0

                    time.sleep(2)
            except GeneratorExit:
                return

        response = StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
