import io
import asyncio
import time

# Try to import pydub, handle gracefully if it fails
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError as e:
    print(f"Warning: pydub not available in voice_handlers - {e}")
    PYDUB_AVAILABLE = False
    AudioSegment = None

import config
from utils.utils import notify_human_on_whatsapp, save_conversation_message_to_firestore, update_voice_message_with_transcription  # NEW: Import voice update function
from services.llm_core_service import client as openai_client # Assuming this is correct
from services.analytics_events import analytics  # 📊 ANALYTICS
# We'll call text_handlers.handle_message directly, but need to pass all required args
from handlers.text_handlers import handle_message as handle_text_message_from_voice
from handlers.training_handlers import handle_training_input


async def handle_voice_message(user_id: str, user_name: str, audio_data_bytes: io.BytesIO, user_data: dict, send_message_func, send_action_func, audio_url: str = None):
    """
    Handles voice messages for WhatsApp users.
    Transcribes audio using Whisper and then passes to the text message handler.
    
    Args:
        audio_url: Optional URL of the audio file (for saving to Firestore)
    """
    config.user_names[user_id] = user_name # Ensure name is updated

    if config.user_in_training_mode.get(user_id, False):
        print(f"[handle_voice_message] INFO: User {user_id} in training mode. Handing over to handle_training_input.")
        # Pass necessary data directly to handle_training_input for voice processing in training mode
        await handle_training_input(
            user_id=user_id,
            user_name=user_name,
            audio_data_bytes=audio_data_bytes, # Pass audio bytes directly
            user_data=user_data,
            send_message_func=send_message_func,
            send_action_func=send_action_func
        )
        return

    if not PYDUB_AVAILABLE:
        await send_message_func(user_id, "عذراً، معالجة الرسائل الصوتية غير متاحة @@الياً. الرجاء إرسال رسالتك نصياً.")
        return

    # ✅ NEW: Save user's voice message to Firestore with metadata
    current_conversation_id = user_data.get('current_conversation_id')
    source_message_id = user_data.pop("_source_message_id", None)
    voice_metadata = {
        "type": "voice",
        "audio_url": audio_url  # Save the audio URL for dashboard playback
    }
    if source_message_id:
        voice_metadata["source_message_id"] = source_message_id
    await save_conversation_message_to_firestore(
        user_id,
        "user",
        "[رسالة صوتية]",  # Placeholder - will be updated with transcription
        current_conversation_id,
        user_name,
        user_data.get('phone_number'),
        metadata=voice_metadata
    )
    user_data['current_conversation_id'] = config.user_data_whatsapp[user_id]['current_conversation_id'] # Ensure it's updated locally

    # ✅ Check if human takeover is active FIRST - before processing with AI
    from utils.utils import get_firestore_db
    db = get_firestore_db()

    if db and current_conversation_id:
        try:
            app_id_for_firestore = "linas-ai-bot-backend"
            conv_doc_ref = db.collection("artifacts").document(app_id_for_firestore).collection("users").document(user_id).collection(config.FIRESTORE_CONVERSATIONS_COLLECTION).document(current_conversation_id)
            doc_snap = conv_doc_ref.get()

            if doc_snap.exists:
                conv_data = doc_snap.to_dict()
                human_takeover_active = conv_data.get('human_takeover_active', False)

                if human_takeover_active:
                    print(f"[handle_voice_message] INFO: User {user_id} conversation {current_conversation_id} is in human takeover mode. Voice will be stored but NOT processed by AI.")

                    # Get operator info for notification message
                    # Try to get operator_name first, then fallback to operator_id
                    operator_name = conv_data.get('operator_name')
                    if not operator_name:
                        operator_id = conv_data.get('operator_id')
                        # If operator_id looks like an email, extract the name part
                        if operator_id and '@' in str(operator_id):
                            operator_name = str(operator_id).split('@')[0].replace('.', ' ').replace('_', ' ').title()
                        elif operator_id:
                            operator_name = operator_id

                    # Prepare handover notification message based on language
                    user_lang = user_data.get('user_preferred_lang', 'ar')

                    # Different messages depending on whether we have the operator name
                    if operator_name:
                        handover_messages = {
                            "ar": f"📞 تم تحويل المحادثة إلى {operator_name}. سيقوم بالرد عليك قريباً.",
                            "en": f"📞 The conversation has been transferred to {operator_name}. They will respond to you shortly.",
                            "fr": f"📞 La conversation a été transférée à {operator_name}. Il vous répondra sous peu."
                        }
                    else:
                        handover_messages = {
                            "ar": "📞 تم تحويل المحادثة إلى أحد موظفينا. سيقوم فريقنا بالرد عليك قريباً.",
                            "en": "📞 The conversation has been transferred to a human agent. Our team will respond to you shortly.",
                            "fr": "📞 La conversation a été transférée à un agent humain. Notre équipe vous répondra sous peu."
                        }
                    handover_msg = handover_messages.get(user_lang, handover_messages['ar'])

                    # Send handover notification ONCE (only if not already notified)
                    if not user_data.get('handover_notified_voice'):
                        await send_message_func(user_id, handover_msg)
                        await save_conversation_message_to_firestore(
                            user_id,
                            "ai",
                            handover_msg,
                            current_conversation_id,
                            user_name,
                            user_data.get('phone_number')
                        )
                        user_data['handover_notified_voice'] = True
                        config.user_data_whatsapp[user_id]['handover_notified_voice'] = True

                    # Exit early - don't process with AI
                    return

        except Exception as e:
            print(f"❌ ERROR checking human takeover status for voice message: {e}")

    # Normal AI processing continues only if human takeover is NOT active
    await send_message_func(user_id, "عم بسمع صوتك... ثواني و بكون جاهزة للرد! 🎧")
    await send_action_func(user_id) # Simulate typing indicator

    mp3_buffer = None
    start_time = time.time()  # 📊 Track processing time

    try:
        # pydub expects a file-like object, audio_data_bytes is already io.BytesIO
        audio = AudioSegment.from_file(audio_data_bytes, format="ogg") # Assuming WhatsApp sends OGG

        mp3_buffer = io.BytesIO()
        audio.export(mp3_buffer, format="mp3")
        mp3_buffer.seek(0)
        mp3_buffer.name = "voice_message.mp3" # Name is needed for openai_client.audio.transcriptions.create

        transcription_response = await openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=mp3_buffer,
            language="ar" # Assuming primary language is Arabic for transcription
        )

        user_text_input = transcription_response.text
        print(f"👂 تم تحويل الصوت إلى نص: {user_text_input}")
        
        # 📊 ANALYTICS: Log voice message from user
        audio_duration_seconds = len(audio) / 1000.0  # pydub duration is in milliseconds
        whisper_cost = (audio_duration_seconds / 60) * 0.006  # Whisper pricing: $0.006 per minute
        
        analytics.log_message(
            source="user",
            msg_type="voice",
            user_id=user_id,
            language=user_data.get('user_preferred_lang', 'ar'),
            sentiment="neutral",
            tokens=0,  # Whisper doesn't report tokens
            cost_usd=whisper_cost,
            model="whisper-1",
            response_time_ms=(time.time() - start_time) * 1000,
            message_length=len(user_text_input)
        )

        # ✅ FIXED: Update the voice message with transcribed text instead of saving a new text message
        # This ensures the Firebase message has:
        # - type: "voice" (not "text")
        # - audio_url: link to original audio
        # - text: the transcribed content
        # - transcribed: true flag
        print(f"DEBUG: voice_handlers - current_conversation_id: {current_conversation_id}, audio_url: {audio_url}")
        if current_conversation_id and audio_url:
            print(f"✅ Calling update_voice_message_with_transcription...")
            await update_voice_message_with_transcription(
                user_id=user_id,
                conversation_id=current_conversation_id,
                audio_url=audio_url,
                transcribed_text=user_text_input,
                phone_number=user_data.get('phone_number')
            )
        else:
            print(f"⚠️ Skipping update - missing current_conversation_id or audio_url")

        # ✅ FIXED: Pass skip_firestore_save flag to prevent double-saving in text_handlers
        # The voice message is already saved and updated above
        await handle_text_message_from_voice(
            user_id=user_id,
            user_name=user_name,
            user_input_text=user_text_input,
            user_data=user_data,
            send_message_func=send_message_func,
            send_action_func=send_action_func,
            skip_firestore_save=True  # ✅ NEW: Don't save again, we already saved above
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ ERROR processing voice message: {e}")
        error_reply = "🚫 آسفة، ما قدرت أفهم رسالتك الصوتية هالمرة. ممكن تعيدها أو تكتبها؟ 🙏"
        await send_message_func(user_id, error_reply)
        # NEW: Save error reply to Firestore
        await save_conversation_message_to_firestore(user_id, "ai", error_reply, user_data['current_conversation_id'], user_name, user_data.get('phone_number'))
        notify_human_on_whatsapp(
            user_name,
            config.user_gender.get(user_id, "غير محدد"),
            f"فشل معالجة رسالة صوتية من: {user_name}. الخطأ: {e}",
            type_of_notification="خطأ رسالة صوتية"
        )
    finally:
        if mp3_buffer:
            mp3_buffer.close()
        print("💡 Voice message processing cleanup complete.")
