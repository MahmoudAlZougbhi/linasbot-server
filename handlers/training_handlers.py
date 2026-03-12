# handlers/training_handlers.py
import io
import base64
import json
import asyncio
from collections import deque
import httpx # NEW: for downloading media in training mode

import config
from utils.utils import save_for_training_conversation_log, notify_human_on_whatsapp, translate_qa_pair_with_gpt
from services.photo_analysis_service import get_bot_photo_analysis_from_gpt
from services.training_response_service import process_training_request_with_gpt
from services.llm_core_service import client as openai_client
# Try to import pydub, handle gracefully if it fails
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError as e:
    print(f"Warning: pydub not available in training_handlers - {e}")
    PYDUB_AVAILABLE = False
    AudioSegment = None

# User-specific training state (moved from global 'training_stage')
# Using config.training_stage = defaultdict(int) defined in config.py
# Using config.last_generated_qa_for_save = defaultdict(list) defined in config.py


async def start_training_mode(user_id: str, user_data: dict, send_message_func, send_action_func):
    """
    Activates the smart training mode for the trainer on WhatsApp.
    """
    if user_id == config.TRAINER_WHATSAPP_NUMBER: # Use WhatsApp number for trainer ID check
        config.user_in_training_mode[user_id] = True
        config.training_stage[user_id] = 1 # Enters free interaction mode
        config.last_generated_qa_for_save[user_id].clear() # Clear any previous data

        # Ensure training conversation context is initialized/cleared
        if 'training_conversation_context' not in user_data:
            user_data['training_conversation_context'] = deque(maxlen=config.MAX_CONTEXT_MESSAGES_TRAINING)
        user_data['training_conversation_context'].clear() # Clear previous training context

        trainer_preferred_lang = user_data.get('user_preferred_lang', 'ar')

        initial_message_map = {
            "ar": "تم تفعيل وضع التدريب الذكي. 🤖\nالآن، أرسل لي **تعليماتك مباشرة لـ GPT** (نص أو صوت أو صورة).\nيمكنك أن تطلب:\n1.  **'سؤال وجواب عن كذا'**: لأتولّد لك أزواج Q&A باللغات الأربع (عربي، إنجليزي، فرنسي، فرنكو) للحفظ.\n2.  **'لخص' / 'شو اتفقنا'**: لألخّص لك المحادثة كـ Q&A للحفظ.\n3.  **'عدّل هذا' / 'كون ودود أكثر' / 'حط إيموجي'**: لأعدّل على آخر رد لـ GPT. (إذا كان نصياً عادياً).\n4.  **صورة**: لأحللها وتطلب مني صياغة سؤال/جواب حولها.\nللخروج من هذا الوضع، اكتب /exit\nللحفظ (بعد توليد Q&A أو تلخيصها): أرسل 'احفظ' أو '/save'.",
            "en": "Smart training mode activated. 🤖\nNow, send me your **instructions directly to GPT** (text, voice, or image).\nYou can ask:\n1.  **'Question and answer about X'**: To generate Q&A pairs in 4 languages (AR, EN, FR, Franco) for saving.\n2.  **'Summarize' / 'What did we agree on'**: To summarize the conversation as Q&A for saving.\n3.  **'Edit this' / 'Be more friendly' / 'Add emoji'**: To modify GPT's last response (if it was plain text).\n4.  **Image**: To analyze it and ask me to formulate a Q&A about it.\nTo exit, type /exit\nTo save (after Q&A generation or summarization): send 'save' or '/save'.",
            "fr": "Mode d'entraînement intelligent activé. 🤖\nMaintenant, envoyez-moi vos **instructions directement à GPT** (texte, voix ou image).\nVous pouvez demander :\n1.  **'Question et réponse sur X'**: Pour générer des paires Q&A en 4 langues (AR, EN, FR, Franco) à enregistrer.\n2.  **'Résumer' / 'Qu'avons-nous convenu'**: Pour résumer la conversation en Q&A à enregistrer.\n3.  **'Modifier ceci' / 'Sois plus amical' / 'Ajoute des emojis'**: Pour modifier la dernière réponse de GPT (si c'était du texte brut).\n4.  **Image**: Pour l'analyser et me demander de formuler une Q&A à ce sujet.\nPour quitter, tapez /exit\nPour enregistrer (après génération Q&A ou résumé Q&A) : envoyez 'enregistrer' ou '/save'.",
            "franco": "Hello! 😊\nMa3ak Lina’s Laser – El mosa3ed el zaki bel zaka2 el istina3e.\nKifak? Kif fini sa3edak el yom? 🧠✨\n\nFik t7kili bi ay tari2a bte7ebbaha – 7atta law bel sawt! 🎤\nAna hon mchan sa3edak bi ay chi baddak yeh, bi kel souhoule w ser3a.\nJahiz? Yalla ne7ki! 🤖💬\n\nW bel monasabe, kermel ne2dar nsa3edak w ne2addemlak afdal khedme, mumkin tkabbirna law sama7t iza inta chab aw inti sabieh? 👦👧"
        }
        await send_message_func(user_id, initial_message_map.get(trainer_preferred_lang, initial_message_map['ar']))
    else:
        await send_message_func(user_id, "ليس لديك صلاحية لتفعيل وضع التدريب.")

async def exit_training_mode(user_id: str, user_data: dict, send_message_func, send_action_func):
    """
    Deactivates the smart training mode for the trainer on WhatsApp.
    """
    if user_id == config.TRAINER_WHATSAPP_NUMBER:
        config.user_in_training_mode[user_id] = False
        config.training_stage[user_id] = 0 # Reset state
        config.last_generated_qa_for_save[user_id].clear() # Clear any previous data
        if 'training_conversation_context' in user_data:
            user_data['training_conversation_context'].clear() # Clear training context as well
        await send_message_func(user_id, "تم إلغاء تفعيل وضع التدريب. عاد البوت للعمل الطبيعي.")
    else:
        await send_message_func(user_id, "ليس لديك صلاحية لإلغاء تفعيل وضع التدريب.")

async def save_generated_data_to_log(user_id: str, send_message_func):
    """
    Saves the last generated Q&A data to the conversation log.
    """
    if user_id != config.TRAINER_WHATSAPP_NUMBER:
        await send_message_func(user_id, "هذا الأمر مخصص للمدربين فقط.")
        return

    data_to_save = config.last_generated_qa_for_save.get(user_id)
    if not data_to_save:
        await send_message_func(user_id, "لا توجد بيانات تدريب مولدة حالياً لحفظها. يرجى توليدها أولاً (عبر طلب 'سؤال وجواب عن كذا' أو 'لخص').")
        return

    try:
        if not isinstance(data_to_save, list):
            await send_message_func(user_id, "عذراً، البيانات المولدة ليست بصيغة صحيحة للحفظ (ليست قائمة).")
            print(f"ERROR: Data to save is not a list: {data_to_save}")
            return

        for entry in data_to_save:
            if isinstance(entry, dict) and 'question' in entry and 'answer' in entry and 'language' in entry:
                save_for_training_conversation_log(entry["question"], entry["answer"])
            else:
                await send_message_func(user_id, f"تحذير: عنصر غير صالح في بيانات التدريب المولدة، لن يتم حفظه: {entry}")
                print(f"Invalid generated data entry: {entry}")

        config.load_training_data() # Load training data immediately after saving to update bot's knowledge in real-time

        await send_message_func(user_id, "تم حفظ بيانات التدريب المولدة بنجاح وتحديث قاعدة بيانات البوت! ✅")
        config.last_generated_qa_for_save[user_id].clear()
        config.training_stage[user_id] = 1 # Trainer can send new instructions directly
    except Exception as e:
        await send_message_func(user_id, f"حدث خطأ أثناء حفظ بيانات التدريب: {e}")
        notify_human_on_whatsapp(config.user_names.get(user_id, "غير محدد"), config.user_gender.get(user_id, "غير محدد"),
                                 f"خطأ في حفظ بيانات التدريب المولدة من المدرب {config.user_names.get(user_id)}: {e}",
                                 type_of_notification="خطأ تدريب")

async def handle_training_input(user_id: str, user_name: str = "مدرب", user_input_text: str = None, audio_data_bytes: io.BytesIO = None, image_url: str = None, user_data: dict = None, send_message_func = None, send_action_func = None):
    """
    Handles input from the trainer in training mode, supporting text, voice, and photo.
    """
    if user_id != config.TRAINER_WHATSAPP_NUMBER or not config.user_in_training_mode.get(user_id, False):
        await send_message_func(user_id, "أنت لست في وضع التدريب. يرجى التواصل مع المدير إذا كنت ترغب بالتدريب.")
        return

    # Check for /exit command
    if user_input_text and user_input_text.lower() == "/exit":
        await exit_training_mode(user_id, user_data, send_message_func, send_action_func)
        return

    # Handle /save command
    if user_input_text and any(kw in user_input_text.lower() for kw in config.SAVE_KEYWORDS):
        await save_generated_data_to_log(user_id, send_message_func)
        return

    processed_input_for_gpt = None # This will be the textual instruction sent to GPT
    
    # Ensure user_data['training_conversation_context'] exists
    if 'training_conversation_context' not in user_data:
        user_data['training_conversation_context'] = deque(maxlen=config.MAX_CONTEXT_MESSAGES_TRAINING)

    # Process input based on type
    if audio_data_bytes:
        if not PYDUB_AVAILABLE:
            await send_message_func(user_id, "عذراً، معالجة الرسائل الصوتية غير متاحة حالياً. الرجاء إرسال تعليماتك نصياً.")
            return
            
        await send_message_func(user_id, "جارٍ تحويل رسالتك الصوتية إلى نص تعليمات التدريب... 🎧")
        await send_action_func(user_id)
        try:
            audio = AudioSegment.from_file(audio_data_bytes, format="ogg") # Assuming OGG for WhatsApp voice notes
            mp3_buffer = io.BytesIO()
            audio.export(mp3_buffer, format="mp3")
            mp3_buffer.seek(0)
            mp3_buffer.name = "voice_training_instruction.mp3"

            transcription_response = await openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=mp3_buffer,
                language="ar" # Arabic for transcription
            )
            processed_input_for_gpt = transcription_response.text
            await send_message_func(user_id, f"تم التعرف على النص: \"{processed_input_for_gpt}\"\n")

        except Exception as e:
            print(f"❌ ERROR processing voice message for training instruction: {e}")
            await send_message_func(user_id, "🚫 آسفة، لم أستطع فهم رسالتك الصوتية لتعليمات التدريب. الرجاء المحاولة مرة أخرى أو الكتابة نصياً.")
            return

    elif image_url:
        await send_message_func(user_id, "تلقيت صورة للتدريب. جارٍ تحليلها بواسطة GPT... 📸")
        await send_action_func(user_id)
        if (
            getattr(config, "ENFORCE_TOTAL_PHOTO_ANALYSIS_LIMIT", False)
            and config.user_photo_analysis_count[user_id] >= config.MAX_PHOTO_ANALYSIS_PER_USER
        ):
             await send_message_func(user_id, "وصلت لعدد الصور القصوى المسموحة في وضع التدريب أيضاً. يرجى الخروج من وضع التدريب أو التواصل مع المطور.")
             return
        try:
            async with httpx.AsyncClient() as client:
                photo_response = await client.get(image_url)
                photo_response.raise_for_status()
                photo_data_bytes = io.BytesIO(photo_response.content)
                photo_data_bytes.seek(0)
            base64_image = base64.b64encode(photo_data_bytes.read()).decode("utf-8")

            bot_initial_reply, analysis_data = await get_bot_photo_analysis_from_gpt(user_id, base64_image, is_training_quiz=True)

            processed_input_for_gpt = (
                f"لدي صورة تم تحليلها. الوصف الأولي لـ GPT هو: {analysis_data.get('description', 'غير معروف')}، "
                f"النوع المقترح: {analysis_data.get('type', 'غير محدد')}، الموقع: {analysis_data.get('location_on_body', 'غير محدد')}. "
                f"الرد المقترح كان: '{bot_initial_reply}'.\n"
                "الآن، أرغب في صياغة سؤال وجواب مثاليين لتدريب البوت على هذه الصورة، أو تعديل الرد المقترح."
            )
            config.user_photo_analysis_count[user_id] += 1

        except Exception as e:
            print(f"❌ ERROR processing photo for training: {e}")
            await send_message_func(user_id, f"🚫 آسفة، حدث خطأ أثناء معالجة صورتك للتدريب: {e}")
            return
    
    elif user_input_text:
        processed_input_for_gpt = user_input_text
    
    if not processed_input_for_gpt: # No usable text after processing
        await send_message_func(user_id, "الرجاء إرسال تعليمات نصية، رسالة صوتية، أو صورة.")
        return

    # Now pass the trainer's instruction to GPT
    await send_action_func(user_id) # Show typing indicator
    
    # Determine if a JSON Q&A generation is explicitly requested by trainer keywords
    is_qa_generation_request = any(kw in processed_input_for_gpt.lower() for kw in config.GENERATE_QA_KEYWORDS)
    is_summary_qa_request = any(kw in processed_input_for_gpt.lower() for kw in config.SUMMARIZE_QA_KEYWORDS)

    gpt_response_obj = await process_training_request_with_gpt(
        user_id,
        processed_input_for_gpt,
        list(user_data['training_conversation_context']), # Pass conversation context
        is_qa_generation_request=is_qa_generation_request,
        is_summary_qa_request=is_summary_qa_request
    )

    # Save trainer's message and GPT's response to training conversation context
    user_data['training_conversation_context'].append({"role": "user", "content": processed_input_for_gpt})
    if gpt_response_obj and 'data' in gpt_response_obj:
        if isinstance(gpt_response_obj['data'], list): # If JSON Q&A
            user_data['training_conversation_context'].append({"role": "assistant", "content": json.dumps(gpt_response_obj['data'], ensure_ascii=False)})
        elif isinstance(gpt_response_obj['data'], str): # If plain text
            user_data['training_conversation_context'].append({"role": "assistant", "content": gpt_response_obj['data']})
        else:
            user_data['training_conversation_context'].append({"role": "assistant", "content": "Unrecognized GPT response format."})


    if gpt_response_obj and gpt_response_obj["type"] == "qa_list":
        config.last_generated_qa_for_save[user_id] = gpt_response_obj["data"]
        config.training_stage[user_id] = 2 # Generated, waiting for save command

        response_message = "تم توليد بيانات التدريب التالية:\n\n"
        for entry in gpt_response_obj["data"]:
            response_message += f"**اللغة:** `{entry.get('language', 'N/A').upper()}`\n"
            response_message += f"**السؤال:** {entry.get('question', 'N/A')}\n"
            response_message += f"**الإجابة:** {entry.get('answer', 'N/A')}\n\n"
        response_message += "إذا كنت راضياً، أرسل لي الأمر **'احفظ'** أو **'/save'** لحفظ هذه البيانات."
        await send_message_func(user_id, response_message) # parse_mode='Markdown' might not be supported by WhatsApp text
    elif gpt_response_obj and gpt_response_obj["type"] == "text":
        config.last_generated_qa_for_save[user_id].clear() # Clear previous Q&A if it was a plain text response
        config.training_stage[user_id] = 1 # Remains in free interaction state
        
        await send_message_func(user_id, f"رد GPT:\n\n{gpt_response_obj['data']}")
        await send_message_func(user_id, "يمكنك الآن إما أن تطلب تعديلات أو تسأل GPT سؤالاً جديداً.\nإذا أردت حفظ آخر سؤال وجواب تم التوصل إليهما في حوارنا، أرسل **'لخص'** أو **'شو اتفقنا'** (لطلب صياغة Q&A للحفظ).")
    else:
        await send_message_func(user_id, "عذراً، لم أتمكن من توليد رد صالح من GPT. الرجاء المحاولة مرة أخرى.")
        config.last_generated_qa_for_save[user_id].clear()
        config.training_stage[user_id] = 1 # Remains in waiting for new instructions