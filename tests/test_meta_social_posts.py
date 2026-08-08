"""Tests for Meta social post creator (explicit user-confirmed publishing)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.meta_app_registry import APP_A_KEY, MetaAssetBinding, MetaBindingCredential
from services.meta_social_media_store import save_uploaded_media
from services.meta_social_post_confirm import SocialPostConfirmError, build_preview, verify_preview_token
from services.meta_social_publish import credential_has_publish_scopes, required_publish_scopes


def _binding(
    *,
    binding_id: str = "fb-1",
    tenant_id: str = "tenant-a",
    channel: str = "facebook",
    asset_id: str = "page-1",
    scopes: list[str] | None = None,
) -> MetaAssetBinding:
    return MetaAssetBinding(
        binding_id=binding_id,
        tenant_id=tenant_id,
        channel=channel,
        asset_id=asset_id,
        page_id=asset_id if channel == "facebook" else "page-linked",
        instagram_account_id="ig-1" if channel == "instagram" else "",
        page_name="Test Page",
        instagram_username="testig" if channel == "instagram" else "",
        app_key=APP_A_KEY,
        status="active",
        generation=1,
        created_at=1.0,
        updated_at=1.0,
        credential_id="cred-1",
        authorized_meta_user_id_hash="hash",
        previous_binding_id="",
        superseded_by_binding_id="",
    )


class MetaSocialPostConfirmTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["META_APP_A_SECRET"] = "unit-test-secret-for-social-posts"

    def test_preview_requires_platform(self) -> None:
        with self.assertRaises(SocialPostConfirmError):
            build_preview(
                tenant_id="tenant-a",
                actor_id="user-1",
                facebook_binding_id="",
                instagram_binding_id="",
                caption="Hello",
                media_id="",
                publish_facebook=False,
                publish_instagram=False,
            )

    def test_preview_token_round_trip(self) -> None:
        _, token = build_preview(
            tenant_id="tenant-a",
            actor_id="user-1",
            facebook_binding_id="fb-1",
            instagram_binding_id="",
            caption="Hello world",
            media_id="",
            publish_facebook=True,
            publish_instagram=False,
        )
        preview = verify_preview_token(token)
        self.assertEqual(preview.tenant_id, "tenant-a")
        self.assertTrue(preview.publish_facebook)
        self.assertFalse(preview.publish_instagram)

    def test_instagram_preview_requires_media(self) -> None:
        with self.assertRaises(SocialPostConfirmError):
            build_preview(
                tenant_id="tenant-a",
                actor_id="user-1",
                facebook_binding_id="",
                instagram_binding_id="ig-1",
                caption="Hello",
                media_id="",
                publish_facebook=False,
                publish_instagram=True,
            )


class MetaSocialPublishScopeTests(unittest.TestCase):
    def test_required_publish_scopes(self) -> None:
        self.assertIn("pages_manage_posts", required_publish_scopes("facebook"))
        self.assertIn("instagram_content_publish", required_publish_scopes("instagram"))

    def test_publish_scope_detection(self) -> None:
        binding = _binding(channel="facebook")
        registry = mock.Mock()
        registry.get_credential.return_value = MetaBindingCredential(
            access_token="token",
            token_app_id="2963733803971681",
            token_profile_id="page-1",
            scopes=("pages_manage_posts", "pages_messaging"),
        )
        self.assertTrue(credential_has_publish_scopes(binding, registry))


class MetaSocialPostsApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_requires_confirmation(self) -> None:
        from modules import meta_social_posts_api

        class Session:
            tenant_id = "tenant-a"
            user_id = "user-1"
            email = "user-1"

        request = mock.Mock()
        with mock.patch.object(meta_social_posts_api, "require_permission", return_value=Session()):
            from fastapi import HTTPException

            with self.assertRaises(HTTPException) as ctx:
                await meta_social_posts_api.publish_social_post(
                    request,
                    {"preview_token": "bad", "confirmed": False},
                )
            self.assertEqual(ctx.exception.status_code, 400)

    async def test_workspace_isolation_on_publish(self) -> None:
        from modules import meta_social_posts_api

        os.environ["META_APP_A_SECRET"] = "unit-test-secret-for-social-posts"
        _, token = build_preview(
            tenant_id="tenant-a",
            actor_id="user-1",
            facebook_binding_id="fb-1",
            instagram_binding_id="",
            caption="Hello",
            media_id="",
            publish_facebook=True,
            publish_instagram=False,
        )

        class Session:
            tenant_id = "tenant-b"
            user_id = "user-1"
            email = "user-1"

        request = mock.Mock()
        with mock.patch.object(meta_social_posts_api, "require_permission", return_value=Session()):
            from fastapi import HTTPException

            with self.assertRaises(HTTPException) as ctx:
                await meta_social_posts_api.publish_social_post(
                    request,
                    {"preview_token": token, "confirmed": True},
                )
            self.assertEqual(ctx.exception.status_code, 403)


class MetaSocialMediaStoreTests(unittest.TestCase):
    def test_save_and_resolve_media(self) -> None:
        os.environ["META_APP_A_SECRET"] = "unit-test-secret-for-social-posts"
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("services.meta_social_media_store._MEDIA_ROOT", Path(tmp) / "media"):
                media_id = save_uploaded_media(
                    tenant_id="tenant-a",
                    filename="photo.jpg",
                    content=b"fake-image",
                    content_type="image/jpeg",
                )
                from services.meta_social_media_store import resolve_media_path

                path = resolve_media_path(tenant_id="tenant-a", media_id=media_id)
                self.assertIsNotNone(path)
                self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
