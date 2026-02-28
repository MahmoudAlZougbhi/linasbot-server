# services/montymobile_template_service.py
"""
MontyMobile Template Message Service
Handles sending WhatsApp template messages via MontyMobile API
"""

import httpx
import json
import os
from typing import Dict, List, Optional


class MontyMobileTemplateService:
    """Service for sending WhatsApp template messages via MontyMobile"""
    
    def __init__(self):
        # Load template configuration
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'montymobile_templates.json')
        try:
            if not os.path.exists(config_path):
                print(f"❌ MontyMobile config not found at: {config_path}")
                self.config = {}
                self.templates = {}
                self.api_config = {}
                return
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.templates = self.config.get('templates', {})
            self.api_config = self.config.get('api_config', {})
            print(f"✅ Loaded {len(self.templates)} MontyMobile templates")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"❌ Error loading MontyMobile config: {e}")
            self.config = {}
            self.templates = {}
            self.api_config = {}
    
    def get_template_info(self, template_id: str) -> Optional[Dict]:
        """Get template information by ID"""
        return self.templates.get(template_id)
    
    def build_template_payload(
        self,
        template_id: str,
        phone_number: str,
        language: str = "ar",
        parameters: Dict[str, str] = None
    ) -> Optional[Dict]:
        """
        Build the payload for sending a template message
        
        Args:
            template_id: Template identifier (e.g., 'reminder_24h')
            phone_number: Recipient phone number
            language: Language code (ar, en, fr)
            parameters: Dictionary of parameter values
            
        Returns:
            Payload dict or None if template not found
        """
        # Debug: Print what we received
        print(f"🔍 DEBUG build_template_payload:")
        print(f"   template_id: {template_id} (type: {type(template_id)})")
        print(f"   phone_number: {phone_number} (type: {type(phone_number)})")
        print(f"   language: {language} (type: {type(language)})")
        print(f"   parameters: {parameters}")
        
        if not self.templates or not self.api_config:
            print("❌ MontyMobile templates not loaded")
            return None
        template = self.templates.get(template_id)
        if not template:
            print(f"❌ Template '{template_id}' not found")
            return None
        
        # Ensure language is a string, not a dict
        if isinstance(language, dict):
            print(f"⚠️ WARNING: language is a dict: {language}")
            print(f"   Converting to string...")
            # Try to extract language code if it's a dict
            if 'code' in language:
                language = language['code']
            else:
                language = 'ar'  # Default fallback
            print(f"   Using language: {language}")
        
        # Check if language is available
        if language not in template['languages']:
            print(f"⚠️ Language '{language}' not available for template '{template_id}', using 'ar'")
            language = 'ar'
        
        template_lang = template['languages'][language]
        
        # Build parameters array in correct order
        param_values = []
        if parameters:
            for param_name in template_lang['parameters']:
                value = parameters.get(param_name, "")
                param_values.append({"type": "text", "text": str(value)})
        
        # Build payload according to MontyMobile API spec
        # Try using wa_message_id if name doesn't work
        template_identifier = template.get('wa_message_id') or template['name']
        
        payload = {
            "to": phone_number,
            "type": "template",
            "source": self.api_config['source'],
            "template": {
                "name": template['name'],  # Use template name
                "language": {
                    "code": language
                },
                "components": []
            },
            "apiId": self.api_config['api_id']
        }
        
        print(f"   Template Name: {template['name']}")
        print(f"   Template WA ID: {template.get('wa_message_id', 'N/A')}")
        
        # Add header component (required by MontyMobile even if empty)
        payload['template']['components'].append({
            "type": "header",
            "parameters": []
        })
        
        # Add body parameters if any
        if param_values:
            payload['template']['components'].append({
                "type": "body",
                "parameters": param_values
            })
        
        return payload
    
    async def send_template_message(
        self,
        template_id: str,
        phone_number: str,
        language: str = "ar",
        parameters: Dict[str, str] = None
    ) -> Dict:
        """
        Send a template message via MontyMobile API
        
        Args:
            template_id: Template identifier
            phone_number: Recipient phone number
            language: Language code
            parameters: Template parameter values
            
        Returns:
            Response dict with success status and data
        """
        try:
            # Build payload
            payload = self.build_template_payload(template_id, phone_number, language, parameters)
            if not payload:
                return {
                    "success": False,
                    "error": f"Template '{template_id}' not found or invalid"
                }
            
            # Prepare headers
            headers = {
                "Tenant": self.api_config['tenant'],
                "api-key": self.api_config['api_key'],
                "Content-Type": "application/json"
            }
            
            # Send request
            url = self.api_config['base_url'] + self.api_config['endpoint']
            
            print(f"📤 Sending template '{template_id}' to {phone_number} (lang: {language})")
            print(f"   URL: {url}")
            print(f"   Tenant: {self.api_config['tenant']}")
            print(f"   API ID: {self.api_config['api_id']}")
            print(f"   API Key: {self.api_config['api_key'][:20]}...")
            print(f"   Payload: {json.dumps(payload, ensure_ascii=False)[:200]}...")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                
                print(f"   Response: {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        response_data = response.json()
                        
                        if response_data.get("success"):
                            message_id = response_data.get("data", {}).get("messageId", "unknown")
                            print(f"✅ Template sent successfully! Message ID: {message_id}")
                            
                            return {
                                "success": True,
                                "message_id": message_id,
                                "template_id": template_id,
                                "phone_number": phone_number,
                                "language": language,
                                "response": response_data
                            }
                        else:
                            error_msg = response_data.get("message", "Unknown error")
                            print(f"❌ Template send failed: {error_msg}")
                            
                            return {
                                "success": False,
                                "error": error_msg,
                                "response": response_data
                            }
                    except json.JSONDecodeError:
                        print(f"⚠️ Could not parse response JSON")
                        return {
                            "success": True,  # Assume success if 200 OK
                            "message_id": "unknown",
                            "response_text": response.text
                        }
                else:
                    error_text = response.text[:500]
                    print(f"❌ HTTP Error {response.status_code}: {error_text}")
                    
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}",
                        "response_text": error_text
                    }
                    
        except httpx.TimeoutException:
            print(f"❌ Request timeout after 30 seconds")
            return {
                "success": False,
                "error": "Request timeout"
            }
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_all_templates(self) -> Dict:
        """Get all available templates"""
        return {
            template_id: {
                "name": template['name'],
                "status": template['status'],
                "category": template['category'],
                "languages": list(template['languages'].keys()),
                "parameters": template['languages'].get('ar', {}).get('parameters', [])
            }
            for template_id, template in self.templates.items()
        }
    
    def is_template_approved(self, template_id: str) -> bool:
        """Check if a template is approved by WhatsApp"""
        template = self.templates.get(template_id)
        if not template:
            return False
        return template.get('status') == 'APPROVED'


# Global instance
montymobile_template_service = MontyMobileTemplateService()
