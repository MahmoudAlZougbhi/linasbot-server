"""
Qiscus WhatsApp Adapter
Qiscus Omnichannel Chat integration for WhatsApp messaging
"""
import json
from typing import Dict, Any, Optional
from .base_adapter import WhatsAppAdapter

class QiscusAdapter(WhatsAppAdapter):
    """Qiscus WhatsApp API adapter"""
    
    def __init__(self, api_token: str, app_code: str, sender_email: str, **kwargs):
        """
        Initialize the Qiscus adapter
        
        Args:
            api_token: QISCUS_SDK_SECRET for authentication
            app_code: Qiscus App Code (AppCode)
            sender_email: Admin email for sending messages
            **kwargs: Additional Qiscus-specific configuration
        """
        super().__init__(api_token, app_code)  # Use app_code as phone_number_id equivalent
        
        # Qiscus API configuration
        self.base_url = kwargs.get('base_url', 'https://omnichannel.qiscus.com')
        self.app_code = app_code
        self.sender_email = sender_email
        
        # Qiscus authentication headers
        self.headers = {
            "Content-Type": "application/json",
            "QISCUS_SDK_SECRET": api_token
        }
        
        # Store additional configuration
        self.api_version = kwargs.get('api_version', 'v1')
        
        # Store room mapping (user_id -> room_id)
        self.room_mapping = {}
    
    async def send_text_message(self, to_number: str, message: str) -> Dict[str, Any]:
        """
        Send a text message via Qiscus
        
        Args:
            to_number: Room ID in Qiscus (not phone number)
            message: Text message to send
        """
        url = f"{self.base_url}/{self.app_code}/bot"
        
        payload = {
            "sender_email": self.sender_email,
            "message": message,
            "type": "text",
            "room_id": to_number  # In Qiscus, this is the room_id
        }
        
        try:
            print(f"🔄 Sending Qiscus message to room {to_number}")
            print(f"📤 URL: {url}")
            print(f"📤 Payload: {payload}")
            
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            
            # Check if response has content
            response_text = response.text
            print(f"📥 Response status: {response.status_code}")
            print(f"📥 Response text: {response_text}")
            
            if response_text:
                try:
                    result = response.json()
                    print(f"✅ Qiscus message sent to room {to_number}. Response: {result}")
                    return {"success": True, "data": result}
                except json.JSONDecodeError as json_err:
                    print(f"⚠️ Response is not JSON: {json_err}")
                    # If response is not JSON but status is 200, consider it success
                    if response.status_code == 200:
                        print(f"✅ Message sent successfully (non-JSON response)")
                        return {"success": True, "message": "Message sent"}
                    else:
                        return {"success": False, "error": f"Invalid JSON response: {response_text}"}
            else:
                # Empty response but 200 status
                if response.status_code == 200:
                    print(f"✅ Message sent successfully (empty response)")
                    return {"success": True, "message": "Message sent"}
                else:
                    return {"success": False, "error": "Empty response from Qiscus"}
                    
        except Exception as e:
            print(f"❌ ERROR sending Qiscus message: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    async def send_image_message(self, to_number: str, image_url: str, caption: str = None) -> Dict[str, Any]:
        """
        Send an image message via Qiscus for WhatsApp
        
        Tries both file_attachment type and text URL approach.
        Since Qiscus might not forward file_attachment to WhatsApp clients,
        we fall back to sending URL directly. WhatsApp will auto-detect
        image extension and display as gallery item.
        
        Args:
            to_number: Room ID in Qiscus
            image_url: URL of the image to send
            caption: Optional caption for the image
        """
        url = f"{self.base_url}/{self.app_code}/bot"
        
        # Approach 1: Try file_attachment type first
        payload_attachment = {
            "sender_email": self.sender_email,
            "message": caption or "Image",
            "type": "file_attachment",
            "room_id": to_number,
            "payload": {
                "url": image_url,
                "caption": caption or ""
            }
        }
        
        # Approach 2: Fallback - send as text message with URL (WhatsApp auto-detects image)
        payload_text = {
            "sender_email": self.sender_email,
            "message": f"{caption}\n{image_url}" if caption else image_url,  # URL with optional caption
            "type": "text",
            "room_id": to_number
        }
        
        try:
            print(f"🔄 Sending Qiscus image to room {to_number}")
            print(f"📤 Image URL: {image_url}")
            if caption:
                print(f"📤 Caption: {caption}")
            
            # First, try with file_attachment type
            print(f"📤 Attempt 1: Trying file_attachment type...")
            print(f"📤 Payload: {payload_attachment}")
            
            response = await self.client.post(url, headers=self.headers, json=payload_attachment)
            
            # Check response
            response_text = response.text
            print(f"📥 Response status: {response.status_code}")
            print(f"📥 Response text: {response_text[:200]}")  # Truncate long responses
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    print(f"✅ Image sent via file_attachment. Response: {result}")
                    return {"success": True, "data": result, "method": "file_attachment"}
                except json.JSONDecodeError:
                    # 200 status but non-JSON response is still success
                    print(f"✅ Image sent via file_attachment (non-JSON response)")
                    return {"success": True, "message": "Message sent", "method": "file_attachment"}
            else:
                # If file_attachment fails, try sending as text URL
                print(f"⚠️ file_attachment failed with status {response.status_code}, trying text URL...")
                print(f"📤 Attempt 2: Trying text message with image URL...")
                print(f"📤 Payload: {payload_text}")
                
                response2 = await self.client.post(url, headers=self.headers, json=payload_text)
                response_text2 = response2.text
                print(f"📥 Response status: {response2.status_code}")
                print(f"📥 Response text: {response_text2[:200]}")
                
                if response2.status_code == 200:
                    try:
                        result = response2.json()
                        print(f"✅ Image sent as text URL. Response: {result}")
                        return {"success": True, "data": result, "method": "text_url"}
                    except json.JSONDecodeError:
                        print(f"✅ Image sent as text URL (non-JSON response)")
                        return {"success": True, "message": "Message sent", "method": "text_url"}
                else:
                    return {"success": False, "error": f"Both methods failed. Statuses: {response.status_code}, {response2.status_code}"}
                    
        except Exception as e:
            print(f"❌ ERROR sending Qiscus image: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    async def send_audio_message(self, to_number: str, audio_url: str) -> Dict[str, Any]:
        """
        Send an audio message via Qiscus for WhatsApp
        
        Since Qiscus Bot API might not forward file_attachment type to WhatsApp,
        we send the URL directly as text message. WhatsApp will auto-detect
        .opus extension and convert it to playable audio icon.
        
        Args:
            to_number: Room ID in Qiscus
            audio_url: URL of the audio file (.opus format)
        """
        url = f"{self.base_url}/{self.app_code}/bot"
        
        # Try BOTH approaches: first file_attachment, then fallback to URL text
        # This gives us the best chance of working across different Qiscus configs
        
        # Approach 1: Try file_attachment type first
        payload_attachment = {
            "sender_email": self.sender_email,
            "message": "🎙️ Voice Message",  # Fallback text if media fails
            "type": "file_attachment",
            "room_id": to_number,
            "payload": {
                "url": audio_url,
                "caption": "Voice Message"
            }
        }
        
        # Approach 2: Fallback - send as text message with URL (WhatsApp auto-detects .opus)
        payload_text = {
            "sender_email": self.sender_email,
            "message": audio_url,  # Just the URL - WhatsApp recognizes .opus extension
            "type": "text",
            "room_id": to_number
        }
        
        try:
            print(f"🔄 Sending Qiscus audio message to room {to_number}")
            print(f"📤 Audio URL: {audio_url}")
            
            # First, try with file_attachment type
            print(f"📤 Attempt 1: Trying file_attachment type...")
            print(f"📤 Payload: {payload_attachment}")
            
            response = await self.client.post(url, headers=self.headers, json=payload_attachment)
            
            # Check response
            response_text = response.text
            print(f"📥 Response status: {response.status_code}")
            print(f"📥 Response text: {response_text[:200]}")  # Truncate long responses
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    print(f"✅ Audio sent via file_attachment. Response: {result}")
                    return {"success": True, "data": result, "method": "file_attachment"}
                except json.JSONDecodeError:
                    # 200 status but non-JSON response is still success
                    print(f"✅ Audio sent via file_attachment (non-JSON response)")
                    return {"success": True, "message": "Message sent", "method": "file_attachment"}
            else:
                # If file_attachment fails, try sending as text URL
                print(f"⚠️ file_attachment failed with status {response.status_code}, trying text URL...")
                print(f"📤 Attempt 2: Trying text message with .opus URL...")
                print(f"📤 Payload: {payload_text}")
                
                response2 = await self.client.post(url, headers=self.headers, json=payload_text)
                response_text2 = response2.text
                print(f"📥 Response status: {response2.status_code}")
                print(f"📥 Response text: {response_text2[:200]}")
                
                if response2.status_code == 200:
                    try:
                        result = response2.json()
                        print(f"✅ Audio sent as text URL (.opus). Response: {result}")
                        return {"success": True, "data": result, "method": "text_url"}
                    except json.JSONDecodeError:
                        print(f"✅ Audio sent as text URL (.opus) (non-JSON response)")
                        return {"success": True, "message": "Message sent", "method": "text_url"}
                else:
                    return {"success": False, "error": f"Both methods failed. Statuses: {response.status_code}, {response2.status_code}"}
                    
        except Exception as e:
            print(f"❌ ERROR sending Qiscus audio: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    async def send_document_message(self, to_number: str, document_url: str, filename: str = None) -> Dict[str, Any]:
        """
        Send a document message via Qiscus
        
        Args:
            to_number: Room ID in Qiscus
            document_url: URL of the document to send
            filename: Optional filename for the document
        """
        url = f"{self.base_url}/{self.app_code}/bot"
        
        payload = {
            "sender_email": self.sender_email,
            "message": filename or "Document",
            "type": "file_attachment",
            "room_id": to_number,
            "payload": {
                "url": document_url,
                "caption": filename or "Document"
            }
        }
        
        try:
            response = await self.client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            print(f"Qiscus document sent to room {to_number}. Response: {result}")
            return {"success": True, "data": result}
        except Exception as e:
            print(f"ERROR sending Qiscus document: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_button_message(self, to_number: str, text: str, buttons: list) -> Dict[str, Any]:
        """
        Send a button message via Qiscus
        Note: Buttons are not supported for WhatsApp in Qiscus
        
        Args:
            to_number: Room ID in Qiscus
            text: Button message text
            buttons: List of button objects
        """
        # Since buttons are not supported for WhatsApp in Qiscus, send as text
        button_text = f"{text}\n\n"
        for i, button in enumerate(buttons, 1):
            button_text += f"{i}. {button.get('label', 'Option')}\n"
        
        return await self.send_text_message(to_number, button_text)
    
    async def download_media(self, media_id: str) -> bytes:
        """
        Download media file by ID
        Note: Qiscus handles media differently - URLs are provided directly
        """
        try:
            # In Qiscus, media URLs are provided directly in the webhook
            # This method might not be needed as URLs are direct
            response = await self.client.get(media_id)  # media_id is actually the URL
            response.raise_for_status()
            return response.content
            
        except Exception as e:
            print(f"ERROR downloading Qiscus media: {e}")
            raise
    
    async def set_webhook(self, webhook_url: str, events: list = None) -> Dict[str, Any]:
        """
        Set webhook URL for receiving messages
        Note: Webhook is configured in Qiscus dashboard, not via API
        """
        print(f"Qiscus webhook should be configured in dashboard: {webhook_url}")
        return {"success": True, "message": "Webhook configured in Qiscus dashboard"}
    
    def parse_webhook_message(self, webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse incoming Qiscus webhook message to standard format
        
        Qiscus webhook format:
        {
            "type": "post_comment_mobile",
            "payload": {
                "from": {"id": 1, "email": "user@example.com", "name": "User"},
                "room": {
                    "id": 1, 
                    "topic_id": 1, 
                    "type": "group", 
                    "name": "WhatsApp Room - +96170123456",
                    "options": {
                        "source": "wa",
                        "channel_details": {"channel_id": 1, "name": "WhatsApp Channel"}
                    },
                    "participants": [...]
                },
                "message": {"type": "text", "text": "message", "payload": {}}
            }
        }
        """
        try:
            print(f"DEBUG: Parsing Qiscus webhook: {json.dumps(webhook_data, indent=2)}")
            
            # Check if this is a Qiscus webhook
            if webhook_data.get("type") in ["post_comment_mobile", "post_comment_rest"]:
                payload = webhook_data.get("payload", {})
                
                # Extract user information
                from_user = payload.get("from", {})
                user_id = str(from_user.get("id", ""))
                user_email = from_user.get("email", "")
                user_name = from_user.get("name", user_email)
                
                # Extract room information - THIS IS CRITICAL
                room = payload.get("room", {})
                room_id = str(room.get("id", ""))
                room_name = room.get("name", "")
                room_options = room.get("options", {})
                
                print(f"DEBUG: Extracted room_id: {room_id}, room_name: {room_name}")
                print(f"DEBUG: Room options: {room_options}")
                
                # Extract phone number from room name or participants
                phone_number = self._extract_phone_from_qiscus_room(room, from_user)
                print(f"🔍 DEBUG: Phone extraction result: {phone_number}")
                if not phone_number:
                    print(f"❌ CRITICAL: Phone extraction FAILED!")
                    print(f"❌ Room name: {room_name}")
                    print(f"❌ User email: {user_email}")
                    print(f"❌ Room options: {room_options}")
                
                # Validate room_id exists
                if not room_id or room_id == "":
                    print(f"ERROR: No room_id found in Qiscus webhook!")
                    return None
                
                # Store room mapping for future use
                self.room_mapping[user_id] = room_id
                if phone_number:
                    self.room_mapping[phone_number] = room_id
                print(f"DEBUG: Stored room mapping - user_id: {user_id} -> room_id: {room_id}")
                if phone_number:
                    print(f"DEBUG: Stored phone mapping - phone: {phone_number} -> room_id: {room_id}")
                
                # Extract message information
                message = payload.get("message", {})
                message_type = message.get("type", "text")
                message_text = message.get("text", "")
                message_payload = message.get("payload", {})
                
                print(f"DEBUG: Message type: {message_type}, text: {message_text}")
                
                # Generate unique message_id using unique_temp_id or message id
                # This prevents collision when message_text is empty (e.g., images with no caption)
                unique_id = message.get("unique_temp_id", "")
                if not unique_id or unique_id == "0":
                    # Fallback: use message id
                    unique_id = message.get("id_str", message.get("id", str(hash(message_text))))
                
                # Create standard format - IMPORTANT: Use room_id as user_id for responses
                parsed_message = {
                    "user_id": room_id,  # CRITICAL: Use room_id as user_id for sending responses
                    "user_name": user_name,
                    "message_id": f"qiscus_{unique_id}",  # Use unique_temp_id for true uniqueness
                    "timestamp": str(int(__import__('time').time())),
                    "type": message_type,
                    "content": self._extract_qiscus_message_content(message),
                    "room_id": room_id,  # Store room_id separately for reference
                    "original_user_id": user_id,  # Store original user_id for reference
                    "phone_number": phone_number  # Store extracted phone number
                }
                
                print(f"DEBUG: Created parsed message with room_id: {room_id}, phone: {phone_number}, message_id: {parsed_message['message_id']}")
                return parsed_message
            
            print(f"DEBUG: Not a Qiscus webhook format: {webhook_data.get('type', 'unknown')}")
            return None
            
        except Exception as e:
            print(f"ERROR parsing Qiscus webhook: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _extract_phone_from_qiscus_room(self, room: Dict[str, Any], from_user: Dict[str, Any]) -> Optional[str]:
        """
        Extract phone number from Qiscus room information
        
        Qiscus typically stores phone numbers in:
        1. Room name (e.g., "WhatsApp Room - +96170123456")
        2. User email (e.g., "96170123456@wa.qiscus.com")
        3. Participant information
        """
        try:
            # Method 1: Extract from room name
            room_name = room.get("name", "")
            print(f"DEBUG: Checking room name for phone: {room_name}")
            
            # Look for phone patterns in room name
            import re
            phone_patterns = [
                r'\+(\d{1,4})\s*(\d{8,12})',  # +961 70123456 or +96170123456
                r'(\d{1,4})\s*(\d{8,12})',   # 961 70123456 or 96170123456
                r'\+(\d{10,15})',            # +96170123456
                r'(\d{10,15})'               # 96170123456
            ]
            
            for pattern in phone_patterns:
                match = re.search(pattern, room_name)
                if match:
                    if len(match.groups()) == 2:
                        # Country code + number
                        country_code = match.group(1)
                        number = match.group(2)
                        phone = f"+{country_code}{number}"
                    else:
                        # Full number
                        phone = match.group(1)
                        if not phone.startswith('+'):
                            phone = f"+{phone}"
                    
                    print(f"DEBUG: Found phone in room name: {phone}")
                    return phone
            
            # Method 2: Extract from user email (common in WhatsApp integrations)
            user_email = from_user.get("email", "")
            print(f"DEBUG: Checking user email for phone: {user_email}")
            
            # Check if email is just a phone number (like "96176466674")
            if user_email.isdigit() and len(user_email) >= 8:
                phone = f"+{user_email}"
                print(f"DEBUG: Found phone as user email (direct): {phone}")
                return phone
            
            if "@wa.qiscus.com" in user_email or "@whatsapp" in user_email:
                # Extract phone from email like "96170123456@wa.qiscus.com"
                phone_part = user_email.split("@")[0]
                if phone_part.isdigit() and len(phone_part) >= 8:
                    phone = f"+{phone_part}"
                    print(f"DEBUG: Found phone in user email: {phone}")
                    return phone
            
            # Method 3: Check participants for phone information
            participants = room.get("participants", [])
            for participant in participants:
                participant_email = participant.get("email", "")
                if "@wa.qiscus.com" in participant_email or "@whatsapp" in participant_email:
                    phone_part = participant_email.split("@")[0]
                    if phone_part.isdigit() and len(phone_part) >= 8:
                        phone = f"+{phone_part}"
                        print(f"DEBUG: Found phone in participant email: {phone}")
                        return phone
            
            # Method 4: Check room options for channel details
            room_options = room.get("options", {})
            
            # CRITICAL FIX: room_options might be a JSON string, not a dict
            if isinstance(room_options, str):
                try:
                    import json
                    room_options = json.loads(room_options)
                    print(f"DEBUG: Parsed room options from JSON string: {room_options}")
                except json.JSONDecodeError as e:
                    print(f"DEBUG: Failed to parse room options JSON: {e}")
                    room_options = {}
            
            channel_details = room_options.get("channel_details", {})
            if channel_details:
                print(f"DEBUG: Channel details: {channel_details}")
                
                # Check if phone is directly in channel_details
                if "phone" in channel_details:
                    phone = channel_details["phone"]
                    # Clean up the phone number
                    phone = phone.replace(" ", "").replace("-", "")
                    if not phone.startswith('+'):
                        phone = f"+{phone}"
                    print(f"DEBUG: Found phone directly in channel_details: {phone}")
                    return phone
                
                # Some Qiscus integrations store phone in channel details
                for key, value in channel_details.items():
                    if isinstance(value, str) and any(char.isdigit() for char in value):
                        for pattern in phone_patterns:
                            match = re.search(pattern, value)
                            if match:
                                if len(match.groups()) == 2:
                                    country_code = match.group(1)
                                    number = match.group(2)
                                    phone = f"+{country_code}{number}"
                                else:
                                    phone = match.group(1)
                                    if not phone.startswith('+'):
                                        phone = f"+{phone}"
                                
                                print(f"DEBUG: Found phone in channel details: {phone}")
                                return phone
            
            print(f"DEBUG: No phone number found in room information")
            return None
            
        except Exception as e:
            print(f"ERROR extracting phone from Qiscus room: {e}")
            return None
    
    def _extract_qiscus_message_content(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract message content from Qiscus message format
        """
        msg_type = message.get("type", "text")
        
        if msg_type == "text":
            return {"text": message.get("text", "")}
            
        elif msg_type == "file_attachment":
            payload = message.get("payload", {})
            url = payload.get("url", "")
            caption = payload.get("caption", "")
            message_text = message.get("text", "").lower()
            
            print(f"DEBUG: file_attachment - URL: {url}, caption: {caption}, text: {message_text}")
            
            # Determine file type from URL, caption, or message text
            # Check for images
            if any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']):
                return {
                    "image_id": url,  # Use URL as image_id
                    "caption": caption
                }
            
            # Check for audio/voice - IMPROVED DETECTION
            # WhatsApp voice messages might have .opus, .ogg, .oga extensions
            # or might be indicated by caption/text containing "voice" or "audio"
            is_audio = (
                any(ext in url.lower() for ext in ['.mp3', '.wav', '.ogg', '.m4a', '.opus', '.oga', '.aac', '.flac']) or
                'voice' in caption.lower() or
                'audio' in caption.lower() or
                'voice' in message_text or
                'audio' in message_text or
                'ptt' in url.lower()  # PTT = Push To Talk (voice message)
            )
            
            if is_audio:
                print(f"✅ Detected as AUDIO message")
                return {
                    "audio_id": url  # Use URL as audio_id
                }
            
            # Check for video
            if any(ext in url.lower() for ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']):
                return {
                    "video_id": url,  # Use URL as video_id
                    "caption": caption
                }
            
            # Default to document
            print(f"⚠️ Treating as document (no specific type detected)")
            return {
                "document_id": url,  # Use URL as document_id
                "filename": caption or "document"
            }
                
        elif msg_type == "location":
            payload = message.get("payload", {})
            return {
                "latitude": payload.get("latitude"),
                "longitude": payload.get("longitude"),
                "name": payload.get("name", ""),
                "address": payload.get("address", "")
            }
            
        else:
            # Return raw message for unknown types
            return {"raw": message}
    
    async def get_message_status(self, message_id: str) -> Dict[str, Any]:
        """
        Get status of a sent message
        Note: Qiscus doesn't provide direct message status API
        """
        return {"success": True, "status": "sent", "message": "Status tracking not available in Qiscus"}
    
    async def send_template_message(self, to_number: str, template_name: str, 
                                   language_code: str = "en", parameters: list = None) -> Dict[str, Any]:
        """
        Send a template message
        Note: Qiscus doesn't have template messages, send as regular text
        """
        # Convert template to regular text message
        template_text = f"Template: {template_name}"
        if parameters:
            template_text += f"\nParameters: {', '.join(parameters)}"
        
        return await self.send_text_message(to_number, template_text)
    
    def get_room_id_for_user(self, user_id: str) -> str:
        """
        Get room ID for a user (helper method)
        """
        return self.room_mapping.get(user_id, user_id)