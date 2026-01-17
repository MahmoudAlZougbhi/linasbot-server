# services/gender_recognition_service.py
from services.llm_core_service import client
import json

async def get_gender_from_gpt(user_input: str) -> str:
    """
    Uses GPT to determine user's gender (male/female/unknown) based on text.
    """
    system_prompt = (
        "You are an intelligent assistant specializing in determining user gender based on their text. "
        "Your task is to analyze the provided text and determine if the user refers to themselves as 'male' or 'female'. "
        "The response **MUST be a single word only**: 'male' if male, 'female' if female, and 'unknown' if you cannot determine with high confidence. "
        "Do not add any other text or explanation whatsoever. The response must ONLY be 'male', 'female', or 'unknown'."
        "Strict and very important examples for Lebanese colloquial and Franco Arabic:\n"
        "- User: 'أنا شب' -> male\n"
        "- User: 'أنا صبية' -> female\n"
        "- User: 'انا بنت' -> female\n"
        "- User: 'انا رجل' -> male\n"
        "- User: 'انا انثى' -> female\n"
        "- User: 'انا ذكر' -> male\n"
        "- User: 'i am a girl' -> female\n"
        "- User: 'je suis un homme' -> male\n"
        "- User: 'ana sabieh' -> female\n"
        "- User: 'ana chab' -> male\n"
        "- User: 'لا انا شب' -> male\n"
        "- User: 'انا مش بنت انا زلمة' -> male\n"
        "- User: 'انا بنت مش شب' -> female\n"
        "- User: 'انا زلمة' -> male\n"
        "- User: 'انا صبية مش شب' -> female\n"
        "- User: 'مدام' -> female\n"
        "- User: 'أستاذ' -> male\n"
        "- User: 'مسيو' -> male\n"
        "- User: 'مدموزيل' -> female\n"
        "- User: 'ميس' -> female\n"
        "- User: 'من فضلك أنا سيدة' -> female\n"
        "- User: 'أنا ذكر' -> male\n"
        "- User: 'أنا أنثى' -> female\n"
        "- User: 'شب' -> male\n"
        "- User: 'بنت' -> female\n"
        "- User: 'صبية' -> female\n"
        "- User: 'رجل' -> male\n"
        "- User: 'امرأة' -> female\n"
        "- User: 'chab' -> male\n"
        "- User: 'sabieh' -> female\n"
        "- User: 'bnt' -> female\n"
        "- User: 'rajol' -> male\n"
        "- User: 'zalami' -> male\n"
        "- User: 'chbe' -> male\n"
        "- User: 'sabiyeh' -> female\n"
        "- User: 'ana zalami' -> male\n"
        "- User: 'ana bnt' -> female\n"
        "- User: 'hi im a guy' -> male\n"
        "- User: 'i am a lady' -> female\n"
        "- User: 'انا معلم' -> male\n"
        "- User: 'انا ست' -> female\n"
        "- User: 'صبية انا' -> female\n"
        "- User: 'شب انا' -> male\n"
        # Examples for more subtle hints (from a user's initial interaction)
        "- User: 'شو عندكن خدمات ليزر للرجال؟' -> male\n" # Direct cue for male
        "- User: 'كيف بقدر احجز جلسة لإزالة الشعر للرجال؟' -> male\n" # Direct cue for male
        "- User: 'أنا سيدة مهتمة بإزالة الشعر' -> female\n" # Direct cue for female
        "- User: 'معكن الشباب؟' -> male\n" # Indirect cue for male
        "- User: 'بدي احكي مع بنت' -> female\n" # Indirect cue for female
        "- User: 'بدي اعمل ليزر رجالي' -> male\n" # New example for male
        "- User: 'بدي اسأل عن ليزر للمناطق الحساسة للشباب' -> male\n" # New example for male
        "- User: 'انا مهتمة بالخدمات النسائية' -> female\n" # New example for female
        "- User: 'بدي اسأل عن اسعار إزالة الشعر للوجه' -> unknown\n" # Still unknown
        "- User: 'مرحبا' -> unknown\n"
        "- User: 'بدي اسأل سؤال' -> unknown\n"
        "Focus on pronouns and gender-specific words across all languages (formal Arabic, colloquial, English, French, and Franco Arabic). Be very careful and precise in inferring gender from any sentence. **Try to logically infer gender even if not explicitly stated, based on any word or phrase that implies it.** If there is any contradiction, try to infer the clearest gender. If you are not very highly confident (more than 70% instead of the previous 95%), respond with 'unknown'. The goal is to reduce 'unknown' as much as possible when reasonable indicators exist."
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
        gender_prediction = response.choices[0].message.content.strip().lower()
        if gender_prediction in ["male", "female"]:
            return gender_prediction
        return "unknown"
    except Exception as e:
        print(f"❌ ERROR in get_gender_from_gpt: {e}")
        return "unknown"