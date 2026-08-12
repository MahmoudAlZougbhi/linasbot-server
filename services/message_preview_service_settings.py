"""Smart-messaging settings and Monty/WhatsApp template header adapters."""

from __future__ import annotations

import json
import os
from typing import Any, cast

from storage.persistent_storage import get_data_root


class MessagePreviewSettingsMixin:
    """App settings, Monty header URL resolution, and smart-messaging toggles."""

    def _merge_legacy_app_settings(self, primary: dict) -> dict:
        """
        If smartMessaging was saved under legacy project data/app_settings.json (before
        LINASBOT_DATA_ROOT migration), merge missing fields so Monty header URL is found.
        """
        if not isinstance(primary, dict):
            primary = {}
        try:
            legacy_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "app_settings.json")
            if not os.path.isfile(legacy_path):
                return primary
            with open(legacy_path, encoding="utf-8") as f:
                legacy_root = json.load(f) or {}
            leg_sm = legacy_root.get("smartMessaging")
            if not isinstance(leg_sm, dict):
                return primary
            pri_sm = primary.get("smartMessaging")
            if not isinstance(pri_sm, dict):
                primary["smartMessaging"] = dict(leg_sm)
                return primary
            for k, v in leg_sm.items():
                cur = pri_sm.get(k)
                if cur is None or (isinstance(cur, str) and not cur.strip()):
                    if v is not None and (not isinstance(v, str) or v.strip()):
                        pri_sm[k] = v
        except Exception as ex:
            print(f"⚠️ Legacy app_settings merge skipped: {ex}")
        return primary

    def _load_app_settings(self) -> dict:
        """Load app settings (persistent root + optional legacy merge)."""
        primary: dict = {}
        try:
            if os.path.isfile(self.app_settings_file):
                with open(self.app_settings_file, encoding="utf-8") as f:
                    primary = json.load(f) or {}
        except Exception as e:
            print(f"Error loading app settings: {e}")
            primary = {}
        if not isinstance(primary, dict):
            primary = {}
        return self._merge_legacy_app_settings(primary)

    def _save_app_settings(self, settings: dict) -> bool:
        """Save app settings"""
        try:
            os.makedirs(os.path.dirname(self.app_settings_file), exist_ok=True)
            with open(self.app_settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Error saving app settings: {e}")
            return False

    def _load_templates(self) -> dict:
        """Load message templates"""
        try:
            with open(self.templates_file, encoding="utf-8") as f:
                return cast(dict[Any, Any], json.load(f))
        except Exception as e:
            print(f"Error loading templates: {e}")
            return {}

    def get_settings(self) -> dict:
        """Get smart messaging settings (merged with defaults for new keys)."""
        settings = self._load_app_settings()
        defaults = {
            "enabled": True,
            "previewBeforeSend": False,
            "autoApproveAfterMinutes": 0,
            # Public HTTPS URL for WhatsApp template IMAGE headers (Monty/Meta require this component).
            "templateHeaderImageUrl": "",
        }
        stored = settings.get("smartMessaging")
        if not isinstance(stored, dict):
            return dict(defaults)
        return {**defaults, **stored}

    def _template_header_sidecar_path(self) -> str:
        return os.path.join(os.path.dirname(self.app_settings_file), "template_header_image_url.txt")

    def _read_template_header_sidecar(self) -> str:
        path = self._template_header_sidecar_path()
        if not os.path.isfile(path):
            return ""
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = (line or "").strip()
                    if line and not line.startswith("#"):
                        return line
        except Exception as ex:
            print(f"⚠️ Could not read template_header_image_url.txt: {ex}")
        return ""

    def _write_template_header_sidecar(self, url: str) -> None:
        path = self._template_header_sidecar_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            u = str(url or "").strip()
            if not u:
                if os.path.isfile(path):
                    os.remove(path)
                return
            with open(path, "w", encoding="utf-8") as f:
                f.write(u + "\n")
        except Exception as ex:
            print(f"⚠️ Could not write template_header_image_url.txt: {ex}")

    def _montymobile_templates_config_path(self) -> str:
        envp = os.getenv("MONTYMOBILE_TEMPLATES_CONFIG_PATH", "").strip()
        if envp:
            return envp
        return os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config",
            "montymobile_templates.json",
        )

    def _default_header_url_from_montymobile_templates_file(self) -> str:
        """api_config.default_header_component.image_link in config/montymobile_templates.json."""
        try:
            path = self._montymobile_templates_config_path()
            if not os.path.isfile(path):
                return ""
            with open(path, encoding="utf-8") as f:
                data = json.load(f) or {}
            dc = (data.get("api_config") or {}).get("default_header_component") or {}
            if isinstance(dc, dict):
                return str(dc.get("image_link") or dc.get("link") or "").strip()
        except Exception as ex:
            print(f"⚠️ montymobile_templates.json default header: {ex}")
        return ""

    def diagnose_template_header_image_sources(self) -> dict[str, Any]:
        """
        Why "no header URL" — shows which sources exist on THIS server (no secrets: URL only prefix/length).
        """
        resolved = self.get_template_header_image_url()
        sidecar = self._template_header_sidecar_path()
        mpath = self._montymobile_templates_config_path()
        sm = self.get_settings() or {}
        dash = str(sm.get("templateHeaderImageUrl") or "").strip()
        return {
            "problem_summary": (
                "WhatsApp approved your template with an IMAGE header. Monty needs a public HTTPS link to that "
                "image in every API request. This server builds that link from env, sidecar file, dashboard save, "
                "or montymobile_templates.json — if all are empty, you see the error."
            ),
            "has_resolved_url": bool(resolved),
            "resolved_url_length": len(resolved),
            "resolved_url_prefix": (resolved[:32] + "…") if len(resolved) > 32 else resolved,
            "env_MONTY_TEMPLATE_HEADER_IMAGE_URL_set": bool(os.getenv("MONTY_TEMPLATE_HEADER_IMAGE_URL", "").strip()),
            "env_WHATSAPP_TEMPLATE_HEADER_IMAGE_URL_set": bool(
                os.getenv("WHATSAPP_TEMPLATE_HEADER_IMAGE_URL", "").strip()
            ),
            "sidecar_path": sidecar,
            "sidecar_file_exists": os.path.isfile(sidecar),
            "app_settings_path": self.app_settings_file,
            "app_settings_exists": os.path.isfile(self.app_settings_file),
            "dashboard_templateHeaderImageUrl_nonempty": bool(dash),
            "montymobile_templates_config_path": mpath,
            "montymobile_templates_config_exists": os.path.isfile(mpath),
            "montymobile_default_header_link_nonempty": bool(
                self._default_header_url_from_montymobile_templates_file()
            ),
            "linasbot_data_root": str(get_data_root()),
        }

    def get_template_header_image_url(self) -> str:
        """
        Public HTTPS image URL for WhatsApp template headers.
        Order: env → sidecar → dashboard JSON → montymobile_templates.json default → raw smartMessaging case-insensitive.
        """
        for envk in ("MONTY_TEMPLATE_HEADER_IMAGE_URL", "WHATSAPP_TEMPLATE_HEADER_IMAGE_URL"):
            v = os.getenv(envk, "").strip()
            if v:
                return v

        sc = self._read_template_header_sidecar()
        if sc:
            return sc

        sm = self.get_settings() or {}
        for key in (
            "templateHeaderImageUrl",
            "template_header_image_url",
            "header_image_url",
        ):
            raw = sm.get(key)
            if raw is None:
                continue
            s = str(raw).strip()
            if s:
                return s

        cfg_url = self._default_header_url_from_montymobile_templates_file()
        if cfg_url:
            return cfg_url

        raw_root = self._load_app_settings()
        rsm = raw_root.get("smartMessaging")
        if isinstance(rsm, dict):
            by_lower = {str(k).lower(): v for k, v in rsm.items()}
            for cand in (
                "templateheaderimageurl",
                "template_header_image_url",
                "header_image_url",
            ):
                val = by_lower.get(cand)
                if val is not None and str(val).strip():
                    return str(val).strip()
        return ""

    def update_settings(self, new_settings: dict) -> dict:
        """Update smart messaging settings"""
        if not isinstance(new_settings, dict):
            new_settings = {}
        patch = dict(new_settings)
        hdr = (
            patch.pop("templateHeaderImageUrl", None)
            or patch.pop("template_header_image_url", None)
            or patch.pop("header_image_url", None)
        )
        if hdr is not None:
            patch["templateHeaderImageUrl"] = str(hdr).strip()
        settings = self._load_app_settings()
        if "smartMessaging" not in settings:
            settings["smartMessaging"] = {}
        settings["smartMessaging"].update(patch)
        if self._save_app_settings(settings):
            self._write_template_header_sidecar(
                (settings.get("smartMessaging") or {}).get("templateHeaderImageUrl") or ""
            )
            return {"success": True, "settings": settings["smartMessaging"]}
        return {"success": False, "error": "Failed to save settings"}

    def toggle_smart_messaging(self, enabled: bool) -> dict:
        """Toggle smart messaging on/off"""
        return self.update_settings({"enabled": enabled})

    def is_preview_mode_enabled(self) -> bool:
        """Check if preview mode is enabled"""
        settings = self.get_settings()
        return cast(bool, settings.get("previewBeforeSend", False))

    def is_smart_messaging_enabled(self) -> bool:
        """Check if smart messaging is globally enabled"""
        settings = self.get_settings()
        return cast(bool, settings.get("enabled", True))
