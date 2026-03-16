"""
Tests for Story 6-4: 10MB file size limit on chat upload.
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from backend_django.chat.models import Conversation
from backend_django.users.models import User


@pytest.fixture
def user_a(db):
    return User.objects.create_user(email="a@test.com", password="p", is_active=True)


@pytest.fixture
def user_b(db):
    return User.objects.create_user(email="b@test.com", password="p", is_active=True)


@pytest.fixture
def conversation(user_a, user_b):
    conv = Conversation.objects.create(name="Test", is_group=False)
    conv.participants.add(user_a, user_b)
    return conv


class TestChatFileSize:
    def test_small_file_accepted(self, client: Client, user_a, conversation):
        client.force_login(user_a)
        small_file = SimpleUploadedFile("doc.pdf", b"x" * 1024, content_type="application/pdf")
        r = client.post(
            f"/api/chat/conversations/{conversation.id}/messages?content=voici",
            data={"file": small_file},
        )
        assert r.status_code == 201

    def test_file_at_limit_accepted(self, client: Client, user_a, conversation):
        client.force_login(user_a)
        # Exactly 10 MB
        file_10mb = SimpleUploadedFile("big.pdf", b"x" * (10 * 1024 * 1024), content_type="application/pdf")
        r = client.post(
            f"/api/chat/conversations/{conversation.id}/messages?content=doc",
            data={"file": file_10mb},
        )
        assert r.status_code == 201

    def test_file_over_limit_rejected(self, client: Client, user_a, conversation):
        client.force_login(user_a)
        # 10 MB + 1 byte
        file_too_big = SimpleUploadedFile("huge.pdf", b"x" * (10 * 1024 * 1024 + 1), content_type="application/pdf")
        r = client.post(
            f"/api/chat/conversations/{conversation.id}/messages?content=doc",
            data={"file": file_too_big},
        )
        assert r.status_code == 413
        assert "volumineux" in r.json()["message"]

    def test_text_only_message_no_size_check(self, client: Client, user_a, conversation):
        client.force_login(user_a)
        r = client.post(
            f"/api/chat/conversations/{conversation.id}/messages?content=hello",
        )
        assert r.status_code == 201
