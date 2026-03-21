#!/usr/bin/env python3
"""
Message Preview Service - Manage message preview queue for approval workflow
"""

import json
import os
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

from storage.persistent_storage import (
    MESSAGE_PREVIEW_QUEUE_FILE,
    APP_SETTINGS_FILE,
    MESSAGE_TEMPLATES_FILE,
    ensure_dirs,
    get_data_root,
)


class MessagePreviewService:
    """
    Service to manage message preview queue for approval before sending
    """

    def __init__(self):
        ensure_dirs()
        self.preview_queue_file = str(MESSAGE_PREVIEW_QUEUE_FILE)
        self.app_settings_file = str(APP_SETTINGS_FILE)
        self.templates_file = str(MESSAGE_TEMPLATES_FILE)
        self.preview_queue = self._load_preview_queue()
        print(f"MessagePreviewService initialized with {len(self.preview_queue)} pending messages")

    def _load_preview_queue(self) -> List[Dict]:
        """Load preview queue from JSON file"""
        if not os.path.exists(self.preview_queue_file):
            return []
        try:
            with open(self.preview_queue_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading preview queue: {e}")
            return []

    def _save_preview_queue(self) -> bool:
        """Save preview queue to JSON file"""
        try:
            os.makedirs(os.path.dirname(self.preview_queue_file), exist_ok=True)
            with open(self.preview_queue_file, 'w', encoding='utf-8') as f:
                json.dump(self.preview_queue, f, ensure_ascii=False, indent=2, default=str)
            return True
        except Exception as e:
            print(f"Error saving preview queue: {e}")
            return False

    def _merge_legacy_app_settings(self, primary: Dict) -> Dict:
        """
        If smartMessaging was saved under legacy project data/app_settings.json (before
        LINASBOT_DATA_ROOT migration), merge missing fields so Monty header URL is found.
        """
        if not isinstance(primary, dict):
            primary = {}
        try:
            legacy_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "data", "app_settings.json"
            )
            if not os.path.isfile(legacy_path):
                return primary
            with open(legacy_path, "r", encoding="utf-8") as f:
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

    def _load_app_settings(self) -> Dict:
        """Load app settings (persistent root + optional legacy merge)."""
        primary: Dict = {}
        try:
            if os.path.isfile(self.app_settings_file):
                with open(self.app_settings_file, "r", encoding="utf-8") as f:
                    primary = json.load(f) or {}
        except Exception as e:
            print(f"Error loading app settings: {e}")
            primary = {}
        if not isinstance(primary, dict):
            primary = {}
        return self._merge_legacy_app_settings(primary)

    def _save_app_settings(self, settings: Dict) -> bool:
        """Save app settings"""
        try:
            os.makedirs(os.path.dirname(self.app_settings_file), exist_ok=True)
            with open(self.app_settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Error saving app settings: {e}")
            return False

    def _load_templates(self) -> Dict:
        """Load message templates"""
        try:
            with open(self.templates_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading templates: {e}")
            return {}

    def get_settings(self) -> Dict:
        """Get smart messaging settings (merged with defaults for new keys)."""
        settings = self._load_app_settings()
        defaults = {
            'enabled': True,
            'previewBeforeSend': True,
            'autoApproveAfterMinutes': 0,
            # Public HTTPS URL for WhatsApp template IMAGE headers (Monty/Meta require this component).
            'templateHeaderImageUrl': '',
        }
        stored = settings.get('smartMessaging')
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
            with open(path, "r", encoding="utf-8") as f:
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
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            dc = (data.get("api_config") or {}).get("default_header_component") or {}
            if isinstance(dc, dict):
                return str(dc.get("image_link") or dc.get("link") or "").strip()
        except Exception as ex:
            print(f"⚠️ montymobile_templates.json default header: {ex}")
        return ""

    def diagnose_template_header_image_sources(self) -> Dict[str, Any]:
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
            "env_MONTY_TEMPLATE_HEADER_IMAGE_URL_set": bool(
                os.getenv("MONTY_TEMPLATE_HEADER_IMAGE_URL", "").strip()
            ),
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

    def update_settings(self, new_settings: Dict) -> Dict:
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
        if 'smartMessaging' not in settings:
            settings['smartMessaging'] = {}
        settings['smartMessaging'].update(patch)
        if self._save_app_settings(settings):
            self._write_template_header_sidecar(
                (settings.get("smartMessaging") or {}).get("templateHeaderImageUrl") or ""
            )
            return {'success': True, 'settings': settings['smartMessaging']}
        return {'success': False, 'error': 'Failed to save settings'}

    def toggle_smart_messaging(self, enabled: bool) -> Dict:
        """Toggle smart messaging on/off"""
        return self.update_settings({'enabled': enabled})

    def is_preview_mode_enabled(self) -> bool:
        """Check if preview mode is enabled"""
        settings = self.get_settings()
        return settings.get('previewBeforeSend', True)

    def is_smart_messaging_enabled(self) -> bool:
        """Check if smart messaging is globally enabled"""
        settings = self.get_settings()
        return settings.get('enabled', True)

    def add_to_preview_queue(self, message_data: Dict) -> Dict:
        """
        Add message to preview queue with status 'pending_approval'

        Args:
            message_data: Dict containing:
                - customer_phone: str
                - customer_name: str
                - template_id: str
                - language: str
                - placeholders: Dict
                - service_id: int (optional)
                - service_name: str (optional)
                - scheduled_send_time: datetime/str

        Returns:
            Dict with success status and message_id
        """
        # Create a deduplication key based on customer + template + scheduled time
        customer_phone = message_data.get('customer_phone', '')
        template_id = message_data.get('template_id', '')
        scheduled_time = str(message_data.get('scheduled_send_time', ''))
        dedup_key = f"{customer_phone}_{template_id}_{scheduled_time}"

        # Check if this message already exists in the queue
        for existing_msg in self.preview_queue:
            existing_key = f"{existing_msg.get('customer_phone', '')}_{existing_msg.get('template_id', '')}_{existing_msg.get('scheduled_send_time', '')}"
            if existing_key == dedup_key:
                # Message already exists, skip adding
                return {
                    'success': True,
                    'message_id': existing_msg.get('message_id'),
                    'duplicate': True,
                    'validation_result': existing_msg.get('validation_result')
                }

        # Generate unique message ID
        message_id = str(uuid.uuid4())[:8] + "_" + datetime.now().strftime("%Y%m%d%H%M%S")

        # Render message content
        rendered_content = self.render_message_preview(
            template_id=message_data.get('template_id'),
            language=message_data.get('language', 'ar'),
            placeholders=message_data.get('placeholders', {})
        )

        # Validate message
        validation_result = self.validate_message({
            **message_data,
            'rendered_content': rendered_content
        })

        # Create queue entry
        queue_entry = {
            'message_id': message_id,
            'customer_phone': message_data.get('customer_phone'),
            'customer_name': message_data.get('customer_name', 'Unknown'),
            'template_id': message_data.get('template_id'),
            'language': message_data.get('language', 'ar'),
            'placeholders': message_data.get('placeholders', {}),
            'service_id': message_data.get('service_id'),
            'service_name': message_data.get('service_name', 'Unknown Service'),
            'scheduled_send_time': str(message_data.get('scheduled_send_time', datetime.now())),
            'rendered_content': rendered_content,
            'status': 'pending_approval',
            'validation_result': validation_result,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        self.preview_queue.append(queue_entry)
        self._save_preview_queue()

        return {
            'success': True,
            'message_id': message_id,
            'validation_result': validation_result
        }

    def get_pending_messages(self, status: str = 'pending_approval', filters: Dict = None) -> List[Dict]:
        """
        Get all messages pending approval

        Args:
            status: Filter by status (pending_approval, approved, rejected, sent)
            filters: Additional filters (service_id, template_id, date_range)

        Returns:
            List of message dicts
        """
        # Reload from file to get latest
        self.preview_queue = self._load_preview_queue()

        results = []
        for msg in self.preview_queue:
            # Filter by status
            if status and msg.get('status') != status:
                continue

            # Apply additional filters
            if filters:
                if filters.get('service_id') and msg.get('service_id') != filters.get('service_id'):
                    continue
                if filters.get('template_id') and msg.get('template_id') != filters.get('template_id'):
                    continue

            results.append(msg)

        # Sort by scheduled_send_time (earliest first)
        results.sort(key=lambda x: x.get('scheduled_send_time', ''))

        return results

    def get_message_by_id(self, message_id: str) -> Optional[Dict]:
        """Get a specific message by ID"""
        for msg in self.preview_queue:
            if msg.get('message_id') == message_id:
                return msg
        return None

    def approve_message(self, message_id: str) -> Dict:
        """
        Approve a message for sending

        Args:
            message_id: The message ID to approve

        Returns:
            Dict with success status and message data
        """
        for i, msg in enumerate(self.preview_queue):
            if msg.get('message_id') == message_id:
                self.preview_queue[i]['status'] = 'approved'
                self.preview_queue[i]['approved_at'] = datetime.now().isoformat()
                self.preview_queue[i]['updated_at'] = datetime.now().isoformat()
                self._save_preview_queue()

                print(f"Message {message_id} approved for sending")
                return {
                    'success': True,
                    'message': self.preview_queue[i]
                }

        return {'success': False, 'error': f'Message {message_id} not found'}

    def reject_message(self, message_id: str, reason: str = None) -> Dict:
        """
        Reject and remove a message from the queue

        Args:
            message_id: The message ID to reject
            reason: Optional reason for rejection

        Returns:
            Dict with success status
        """
        for i, msg in enumerate(self.preview_queue):
            if msg.get('message_id') == message_id:
                self.preview_queue[i]['status'] = 'rejected'
                self.preview_queue[i]['rejected_at'] = datetime.now().isoformat()
                self.preview_queue[i]['rejection_reason'] = reason
                self.preview_queue[i]['updated_at'] = datetime.now().isoformat()
                self._save_preview_queue()

                print(f"Message {message_id} rejected: {reason}")
                return {'success': True, 'message_id': message_id}

        return {'success': False, 'error': f'Message {message_id} not found'}

    def edit_message(self, message_id: str, new_content: Dict) -> Dict:
        """
        Edit message content before approval

        Args:
            message_id: The message ID to edit
            new_content: Dict with updated fields (rendered_content, placeholders, etc.)

        Returns:
            Dict with success status and updated message
        """
        for i, msg in enumerate(self.preview_queue):
            if msg.get('message_id') == message_id:
                # Update allowed fields
                if 'rendered_content' in new_content:
                    self.preview_queue[i]['rendered_content'] = new_content['rendered_content']
                if 'placeholders' in new_content:
                    self.preview_queue[i]['placeholders'] = new_content['placeholders']
                if 'language' in new_content:
                    self.preview_queue[i]['language'] = new_content['language']
                if 'scheduled_send_time' in new_content:
                    self.preview_queue[i]['scheduled_send_time'] = str(new_content['scheduled_send_time'])

                # Re-validate after edit
                self.preview_queue[i]['validation_result'] = self.validate_message(self.preview_queue[i])
                self.preview_queue[i]['updated_at'] = datetime.now().isoformat()
                self.preview_queue[i]['edited'] = True

                self._save_preview_queue()

                print(f"Message {message_id} edited")
                return {
                    'success': True,
                    'message': self.preview_queue[i]
                }

        return {'success': False, 'error': f'Message {message_id} not found'}

    def batch_approve(self, message_ids: List[str]) -> Dict:
        """Approve multiple messages at once"""
        approved = []
        failed = []

        for message_id in message_ids:
            result = self.approve_message(message_id)
            if result.get('success'):
                approved.append(message_id)
            else:
                failed.append({'id': message_id, 'error': result.get('error')})

        return {
            'success': len(failed) == 0,
            'approved': approved,
            'failed': failed,
            'total_approved': len(approved),
            'total_failed': len(failed)
        }

    def batch_reject(self, message_ids: List[str], reason: str = None) -> Dict:
        """Reject multiple messages at once"""
        rejected = []
        failed = []

        for message_id in message_ids:
            result = self.reject_message(message_id, reason)
            if result.get('success'):
                rejected.append(message_id)
            else:
                failed.append({'id': message_id, 'error': result.get('error')})

        return {
            'success': len(failed) == 0,
            'rejected': rejected,
            'failed': failed,
            'total_rejected': len(rejected),
            'total_failed': len(failed)
        }

    def validate_message(self, message_data: Dict) -> Dict:
        """
        Validate message before sending

        Args:
            message_data: Message data including rendered_content, customer_phone, etc.

        Returns:
            Dict with valid status and list of errors
        """
        errors = []
        settings = self.get_settings()
        validation_rules = settings.get('validationRules', {})

        # 1. Phone number validation
        phone = message_data.get('customer_phone', '')
        phone_clean = str(phone).replace('+', '').replace('-', '').replace(' ', '')

        min_phone_len = validation_rules.get('minPhoneLength', 8)
        max_phone_len = validation_rules.get('maxPhoneLength', 15)

        if len(phone_clean) < min_phone_len:
            errors.append(f"Phone number too short (min {min_phone_len} digits)")
        if len(phone_clean) > max_phone_len:
            errors.append(f"Phone number too long (max {max_phone_len} digits)")
        if phone_clean and not phone_clean.isdigit():
            errors.append("Phone number contains invalid characters")

        # Lebanon format check (961 + 8 digits)
        if phone_clean.startswith('961'):
            local_number = phone_clean[3:]
            if len(local_number) != 8:
                errors.append("Lebanese phone should be 961 + 8 digits")

        # 2. Required variables check
        placeholders = message_data.get('placeholders', {})
        required_vars = validation_rules.get('requiredVariables', ['customer_name'])

        for var in required_vars:
            if not placeholders.get(var):
                errors.append(f"Missing required variable: {var}")

        # 3. Check for unfilled placeholders in rendered content
        rendered_content = message_data.get('rendered_content', '')
        if rendered_content:
            unfilled = re.findall(r'\{(\w+)\}', rendered_content)
            if unfilled:
                errors.append(f"Unfilled placeholders: {', '.join(unfilled)}")

        # 4. Message length check (WhatsApp limit)
        max_msg_len = validation_rules.get('maxMessageLength', 1600)
        if len(rendered_content) > max_msg_len:
            errors.append(f"Message too long: {len(rendered_content)} chars (max {max_msg_len})")

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

    def render_message_preview(self, template_id: str, language: str, placeholders: Dict) -> str:
        """
        Render full message with placeholders filled

        Args:
            template_id: Template ID to use
            language: Language code (ar, en, fr)
            placeholders: Dict of placeholder values

        Returns:
            Rendered message string
        """
        templates = self._load_templates()

        if template_id not in templates:
            return f"[Template '{template_id}' not found]"

        template = templates[template_id]
        template_text = template.get(language, template.get('ar', ''))

        if not template_text:
            return f"[Template '{template_id}' has no content for language '{language}']"

        # Replace placeholders
        rendered = template_text
        for key, value in placeholders.items():
            rendered = rendered.replace(f'{{{key}}}', str(value))

        return rendered

    def get_approved_messages(self) -> List[Dict]:
        """Get messages that have been approved and are ready to send"""
        return self.get_pending_messages(status='approved')

    def mark_as_sent(self, message_id: str) -> Dict:
        """Mark a message as sent after successful delivery"""
        for i, msg in enumerate(self.preview_queue):
            if msg.get('message_id') == message_id:
                self.preview_queue[i]['status'] = 'sent'
                self.preview_queue[i]['sent_at'] = datetime.now().isoformat()
                self.preview_queue[i]['updated_at'] = datetime.now().isoformat()
                self._save_preview_queue()
                return {'success': True}

        return {'success': False, 'error': f'Message {message_id} not found'}

    def get_queue_stats(self) -> Dict:
        """Get statistics about the preview queue"""
        self.preview_queue = self._load_preview_queue()

        stats = {
            'total': len(self.preview_queue),
            'pending_approval': 0,
            'approved': 0,
            'rejected': 0,
            'sent': 0,
            'by_template': {},
            'by_service': {}
        }

        for msg in self.preview_queue:
            status = msg.get('status', 'unknown')
            if status in stats:
                stats[status] += 1

            # Count by template
            template_id = msg.get('template_id', 'unknown')
            if template_id not in stats['by_template']:
                stats['by_template'][template_id] = 0
            stats['by_template'][template_id] += 1

            # Count by service
            service_name = msg.get('service_name', 'Unknown')
            if service_name not in stats['by_service']:
                stats['by_service'][service_name] = 0
            stats['by_service'][service_name] += 1

        return stats

    def cleanup_old_messages(self, days_old: int = 30) -> Dict:
        """Remove messages older than specified days"""
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=days_old)
        removed_count = 0
        new_queue = []

        for msg in self.preview_queue:
            created_at = msg.get('created_at', '')
            try:
                msg_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                if msg_date > cutoff_date:
                    new_queue.append(msg)
                else:
                    removed_count += 1
            except:
                new_queue.append(msg)  # Keep if can't parse date

        self.preview_queue = new_queue
        self._save_preview_queue()

        return {'success': True, 'removed_count': removed_count}


# Singleton instance
message_preview_service = MessagePreviewService()
