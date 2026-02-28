# services/gender_recognition_service.py
from services.llm_core_service import client
import json

async def get_gender_from_gpt(user_input: str) -> str:
    """
    Uses GPT to determine user's gender (male/female/unknown) based on text.
    Only detects gender when user EXPLICITLY states their own gender.
    """
    system_prompt = (
        "You are an intelligent assistant that detects if a user has EXPLICITLY stated their own gender. "
        "The response **MUST be a single word only**: 'male', 'female', or 'unknown'.\n\n"
        "**CRITICAL RULES:**\n"
        "1. ONLY detect gender when the user EXPLICITLY states their own gender (e.g., 'ana shab', 'I am a girl')\n"
        "2. Greetings like 'kifak', 'kifik', 'hi', 'hello', 'marhaba' are ALWAYS 'unknown' - they do NOT indicate gender\n"
        "3. Verb conjugations in greetings do NOT indicate the SPEAKER's gender\n"
        "4. When in doubt, respond 'unknown' - it's better to ask than assume\n\n"
        "**EXPLICIT gender statements (detect these):**\n"
        "- 'أنا شب' / 'ana shab' / 'ana chab' -> male\n"
        "- 'أنا صبية' / 'ana sabieh' / 'ana sabiye' -> female\n"
        "- 'انا بنت' / 'ana bnt' -> female\n"
        "- 'انا رجل' / 'ana rajol' -> male\n"
        "- 'انا زلمة' / 'ana zalami' -> male\n"
        "- 'i am a guy' / 'i am a girl' / 'i am male' / 'i am female' -> detect accordingly\n"
        "- 'je suis un homme' / 'je suis une femme' -> detect accordingly\n"
        "- 'شب' (standalone, as answer to gender question) -> male\n"
        "- 'صبية' / 'بنت' (standalone, as answer to gender question) -> female\n"
        "- 'بدي اعمل ليزر رجالي' -> male (explicitly asking for male services)\n"
        "- 'بدي خدمات نسائية' -> female (explicitly asking for female services)\n\n"
        "**NOT gender indicators (always return 'unknown'):**\n"
        "- 'kifak' / 'kifik' / 'كيفك' -> unknown (greeting, NOT speaker's gender)\n"
        "- 'hi kifak' / 'hello' / 'marhaba' / 'مرحبا' -> unknown\n"
        "- 'shu akhbarak' / 'شو اخبارك' -> unknown (greeting)\n"
        "- 'بدي احجز موعد' -> unknown (no gender stated)\n"
        "- 'كم السعر' / 'what is the price' -> unknown\n"
        "- Any question about services without explicit gender mention -> unknown\n"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.15, # Adjusted temperature for more confident gender detection
            max_tokens=10
        )
        if not response.choices:
            return "unknown"
        gender_prediction = response.choices[0].message.content.strip().lower()
        if gender_prediction in ["male", "female"]:
            return gender_prediction
        return "unknown"
    except Exception as e:
        print(f"❌ ERROR in get_gender_from_gpt: {e}")
        return "unknown"