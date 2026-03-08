from django.urls import path
from .api.stream import notification_stream  # Import depuis le sous-dossier api

urlpatterns = [
    # Le chemin sera : /notification/api/stream/
    path('api/stream/', notification_stream, name='notification-stream-api'),
]