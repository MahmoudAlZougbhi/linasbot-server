"""Durable social booking preferences share the existing Firestore user profile."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services import user_persistence_service
from services.social_contact_routing import SOCIAL_BOOKING_PREFERENCES_FIELD
from services.user_persistence_service import UserPersistenceService


@pytest.mark.asyncio
async def test_social_preference_updates_only_its_scoped_field_in_existing_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "a" * 64
    document = Mock()
    document.get.return_value = SimpleNamespace(exists=True)
    users = Mock()
    users.document.return_value = document
    app_document = Mock()
    app_document.collection.return_value = users
    artifacts = Mock()
    artifacts.document.return_value = app_document
    database = Mock()
    database.collection.return_value = artifacts
    monkeypatch.setattr(user_persistence_service, "get_firestore_db", lambda: database)

    saved = await UserPersistenceService().save_social_booking_preference("facebook:sender", key, "female")

    assert saved is True
    document.update.assert_called_once()
    update_payload = document.update.call_args.args[0]
    record = update_payload[f"{SOCIAL_BOOKING_PREFERENCES_FIELD}.{key}"]
    assert record["value"] == "female"
    assert "gender" not in update_payload


@pytest.mark.asyncio
async def test_social_preference_creates_backward_compatible_existing_profile_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "b" * 64
    document = Mock()
    document.get.return_value = SimpleNamespace(exists=False)
    users = Mock()
    users.document.return_value = document
    app_document = Mock()
    app_document.collection.return_value = users
    artifacts = Mock()
    artifacts.document.return_value = app_document
    database = Mock()
    database.collection.return_value = artifacts
    monkeypatch.setattr(user_persistence_service, "get_firestore_db", lambda: database)

    saved = await UserPersistenceService().save_social_booking_preference("instagram:sender", key, "male")

    assert saved is True
    document.set.assert_called_once()
    create_payload = document.set.call_args.args[0]
    assert create_payload[SOCIAL_BOOKING_PREFERENCES_FIELD][key]["value"] == "male"
    assert "gender" not in create_payload
