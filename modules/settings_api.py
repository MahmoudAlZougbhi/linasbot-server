"""
Settings API Module
Handles application settings endpoints for the dashboard
"""

from fastapi import HTTPException
from typing import Dict, Any

from modules.core import app
from services.settings_service import settings_service


@app.get("/api/settings")
async def get_settings():
    """Get all application settings"""
    try:
        settings = settings_service.get_all_settings()
        return {
            "success": True,
            "settings": settings
        }
    except Exception as e:
        print(f"❌ Error getting settings: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/settings/{category}")
async def update_settings(category: str, updates: Dict[str, Any]):
    """
    Update settings in a specific category
    
    Args:
        category: Settings category (general, notifications, security)
        updates: Dictionary of settings to update
    """
    try:
        # Validate category
        valid_categories = ['general', 'notifications', 'security']
        if category not in valid_categories:
            return {
                "success": False,
                "error": f"Invalid category. Must be one of: {valid_categories}"
            }
        
        # Update settings
        success = settings_service.update_settings(category, updates)
        
        if success:
            return {
                "success": True,
                "message": f"Settings updated successfully",
                "category": category,
                "updated": updates
            }
        else:
            return {
                "success": False,
                "error": "Failed to save settings"
            }
    except Exception as e:
        print(f"❌ Error updating settings: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/settings/notifications/human-takeover-mobiles")
async def get_human_takeover_mobiles():
    """Get mobile numbers for human takeover notifications"""
    try:
        mobile_numbers = settings_service.get_human_takeover_notify_mobiles()
        return {
            "success": True,
            "mobile_numbers": mobile_numbers
        }
    except Exception as e:
        print(f"❌ Error getting human takeover mobiles: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/settings/notifications/human-takeover-mobiles")
async def set_human_takeover_mobiles(data: Dict[str, Any]):
    """Set mobile numbers for human takeover notifications"""
    try:
        mobile_numbers = data.get('mobile_numbers', '')
        
        success = settings_service.set_human_takeover_notify_mobiles(mobile_numbers)
        
        if success:
            return {
                "success": True,
                "message": "Mobile numbers updated successfully",
                "mobile_numbers": mobile_numbers
            }
        else:
            return {
                "success": False,
                "error": "Failed to save mobile numbers"
            }
    except Exception as e:
        print(f"❌ Error setting human takeover mobiles: {e}")
        return {
            "success": False,
            "error": str(e)
        }
