# services/settings_service.py
"""
Settings Service
Manages application settings storage and retrieval
"""

import json
import os
import re
from typing import Dict, Any


class SettingsService:
    """Service for managing application settings"""
    
    def __init__(self):
        self.settings_file = 'data/app_settings.json'
        self.settings = self._load_settings()
        print(f"✅ Settings Service initialized")
    
    def _load_settings(self) -> Dict[str, Any]:
        """Load settings from file or create default"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                print(f"✅ Loaded settings from {self.settings_file}")
                return settings
            except Exception as e:
                print(f"⚠️ Error loading settings: {e}, using defaults")
                return self._get_default_settings()
        else:
            print(f"📝 Settings file not found, creating default settings")
            default_settings = self._get_default_settings()
            self._save_settings(default_settings)
            return default_settings
    
    def _get_default_settings(self) -> Dict[str, Any]:
        """Get default settings"""
        return {
            "general": {
                "botName": "Marwa AI Assistant",
                "defaultLanguage": "ar",
                "responseTimeout": 5,
                "enableVoice": True,
                "enableImages": True,
                "enableTraining": True
            },
            "notifications": {
                "notificationsEnabled": True,
                "emailAlerts": True,
                "humanTakeoverNotifyMobiles": ""
            },
            "security": {
                "sessionTimeout": 24
            }
        }
    
    def _save_settings(self, settings: Dict[str, Any]) -> bool:
        """Save settings to file"""
        try:
            # Ensure data directory exists
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            
            print(f"✅ Settings saved to {self.settings_file}")
            return True
        except Exception as e:
            print(f"❌ Error saving settings: {e}")
            return False
    
    def get_all_settings(self) -> Dict[str, Any]:
        """Get all settings"""
        return self.settings
    
    def get_setting(self, category: str, key: str, default=None) -> Any:
        """
        Get a specific setting value
        
        Args:
            category: Settings category (e.g., 'general', 'notifications')
            key: Setting key
            default: Default value if not found
            
        Returns:
            Setting value or default
        """
        return self.settings.get(category, {}).get(key, default)
    
    def update_settings(self, category: str, updates: Dict[str, Any]) -> bool:
        """
        Update settings in a category
        
        Args:
            category: Settings category
            updates: Dictionary of key-value pairs to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if category not in self.settings:
                self.settings[category] = {}

            if category == "notifications" and "humanTakeoverNotifyMobiles" in updates:
                updates = dict(updates)
                updates["humanTakeoverNotifyMobiles"] = self.normalize_human_takeover_notify_mobiles(
                    updates.get("humanTakeoverNotifyMobiles", "")
                )
            
            # Update the settings
            self.settings[category].update(updates)
            
            # Save to file
            return self._save_settings(self.settings)
        except Exception as e:
            print(f"❌ Error updating settings: {e}")
            return False
    
    def get_human_takeover_notify_mobiles(self) -> str:
        """Get the mobile numbers for human takeover notifications"""
        raw_numbers = self.get_setting('notifications', 'humanTakeoverNotifyMobiles', '')
        return self.normalize_human_takeover_notify_mobiles(raw_numbers)

    def normalize_human_takeover_notify_mobiles(self, mobile_numbers: str) -> str:
        """
        Normalize and deduplicate configured handoff notification numbers.

        Accepted separators: comma, semicolon, or newline.
        Returns a comma-separated string in normalized international format.
        """
        if not mobile_numbers:
            return ""

        raw_items = re.split(r"[,;\n]+", str(mobile_numbers))
        normalized_items = []
        seen = set()

        for raw_item in raw_items:
            normalized = self._normalize_single_mobile(raw_item)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            normalized_items.append(normalized)

        return ", ".join(normalized_items)

    def _normalize_single_mobile(self, mobile_number: str) -> str:
        """Normalize one phone number to +<country><number> format."""
        if not mobile_number:
            return ""

        cleaned = str(mobile_number).strip()
        if not cleaned:
            return ""

        # Keep only digits and leading plus
        cleaned = re.sub(r"[^\d+]", "", cleaned)
        if not cleaned:
            return ""

        if cleaned.startswith("00"):
            cleaned = "+" + cleaned[2:]

        if not cleaned.startswith("+"):
            if cleaned.startswith("961"):
                cleaned = "+" + cleaned
            elif cleaned.startswith("0"):
                cleaned = "+961" + cleaned[1:]
            else:
                cleaned = "+961" + cleaned

        return cleaned

    def get_human_takeover_notify_mobiles_list(self):
        """Get normalized notification numbers as a list."""
        raw = self.get_human_takeover_notify_mobiles()
        normalized = self.normalize_human_takeover_notify_mobiles(raw)
        if not normalized:
            return []
        return [item.strip() for item in normalized.split(",") if item.strip()]
    
    def set_human_takeover_notify_mobiles(self, mobile_numbers: str) -> bool:
        """Set the mobile numbers for human takeover notifications"""
        normalized_numbers = self.normalize_human_takeover_notify_mobiles(mobile_numbers)
        return self.update_settings('notifications', {
            'humanTakeoverNotifyMobiles': normalized_numbers
        })


# Global instance
settings_service = SettingsService()
