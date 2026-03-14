# services/training_response_service.py
import json
import re
# from services.openai_service import client # <--- استبدلها
from services.llm_core_service import client # <--- استيراد client من llm_core_service
import config # نحتاج config هنا للوصول إلى BOT_STYLE_GUIDE, CORE_KNOWLEDGE_BASE, PRICE_LIST
from utils.utils import translate_qa_pair_with_gpt # نحتاج هذه الدالة هنا أيضاً

async def process_training_request_with_gpt(user_id: int, training_instruction_text: str, current_training_context: list = None, is_qa_generation_request: bool = False, is_summary_qa_request: bool = False):
    """
    دالة وسيطة ترسل طلب المدرب إلى GPT لإنشاء أو تعديل بيانات تدريب بمرونة.
    `is_qa_generation_request`: إذا كانت True، سنطلب من GPT إخراج JSON صارم لـ Q&A.
    `is_summary_qa_request`: إذا كانت True، سنطلب من GPT تلخيص السياق الحالي كـ Q&A.
    """
    if current_training_context is None:
        current_training_context = []

    # التعليمات ستختلف بناءً على نوع الطلب
    if is_summary_qa_request:
        system_instruction_for_training_mode_gpt = (
            "أنت مساعد تدريب ذكي. مهمتك هي تحليل سياق المحادثة الأخيرة مع المدرب (الموجود في 'current_training_context') "
            "واستخلاص السؤال الرئيسي والإجابة المتفق عليها أو الأفكار الأساسية منها. "
            "ثم يجب أن تصوغ هذه الأفكار كأزواج سؤال/إجابة (Q&A) باللغات الأربع: العربية (ar)، الإنجليزية (en)، الفرنسية (fr)، والفرنكو عربي (franco). "
            "الرد **يجب أن يكون JSON صارم** (قائمة من كائنات {question, answer, language}). "
            "كن دقيقاً جداً في استخلاص النقطة الرئيسية من الحوار. "
            "**مثال لمخرج JSON متوقع:**\n"
            "```json\n"
            "[\n"
            "  {\"question\": \"ما هي ساعات عمل المركز؟\", \"answer\": \"ساعات عمل مركز لينا ليزر هي من 10 صباحاً لـ 6 مساءً يومياً ما عدا الأحد.\", \"language\": \"ar\"},\n"
            "  {\"question\": \"What are the center's operating hours?\", \"answer\": \"Lina's Laser Center operates from 10 AM to 6 PM daily, except for Sundays.\", \"language\": \"en\"}\n"
            "]\n"
            "```\n"
            "أعد فقط الـ JSON. لا تضف أي نص آخر قبله أو بعده."
        )
        messages = [{"role": "system", "content": system_instruction_for_training_mode_gpt}] + current_training_context
        messages.append({"role": "user", "content": "الرجاء تلخيص المحادثة أعلاه في أزواج سؤال/إجابة باللغات الأربع (عربي، إنجليزي، فرنسي، فرنكو عربي)."})

    else: # الوضع العادي لإنشاء/تعديل بيانات التدريب
        system_instruction_for_training_mode_gpt = (
            "أنت مساعد تدريب ذكي ومرن لمركز Lina's Laser. مهمتك هي التفاعل مع المدرب لفهم طلباته حول إنشاء أو تعديل بيانات تدريب (أسئلة وأجوبة). "
            "المدرب يمكن أن يعطيك طلبات متنوعة جداً. يجب أن تستوعب طلبه بمرونة شديدة، حتى لو كان غير واضح أو عام. "
            "**فهم اللغة:** تفهم العربية (فصحى وعامية)، الإنجليزية، الفرنسية، و**الفرانكو عربي** ببراعة. "
            "**مرونة الأوامر:** تستجيب لأوامر مثل: 'سؤال وجواب عن كذا'، 'عدّل هذا'، 'كون ودود أكثر'، 'حط إيموجي'، 'أعطني صيغ أخرى لهذا السؤال'، 'اجعل الجواب أقصر/أطول'. "
            "**تنسيق المخرج:**\n"
            "1.  **إذا طلب المدرب بوضوح 'سؤال وجواب' أو 'Q&A' أو ما يشابه ذلك (باللغات الأربع ar, en, fr, franco)، يجب أن يكون مخرجك JSON صارم** (قائمة من كائنات {question, answer, language}). هذا هو التنسيق الوحيد الذي يمكن حفظه تلقائياً. تأكد أن كل عنصر في القائمة يحتوي على المفاتيح الثلاثة تماماً. "
            "    **طلبات توليد Q&A عادة ما تتضمن عبارات مثل:** 'سؤال وجواب عن'، 'Q&A for', 'générer Q&R sur', 'صيغة سؤال وجواب', 'اعطيني سؤال وجواب'.\n"
            "    **مثال لطلب المدرب:** 'أريد سؤالاً وإجابة عن ساعات عمل المركز باللغات الأربع.'\n"
            "    **مثال لمخرج JSON متوقع (للتدريب على الفرنكو):**\n"
            "    ```json\n"
            "    [\n"
            "      {\"question\": \"ما هي ساعات عمل المركز؟\", \"answer\": \"ساعات عمل مركز لينا ليزر هي من 10 صباحاً لـ 6 مساءً يومياً ما عدا الأحد.\", \"language\": \"ar\"},\n"
            "      {\"question\": \"What are the center's operating hours?\", \"answer\": \"Lina's Laser Center operates from 10 AM to 6 PM daily, except for Sundays.\", \"language\": \"en\"},\n"
            "      {\"question\": \"Quelles sont les heures d'ouverture du centre ?\", \"answer\": \"Le Centre Laser Lina's est ouvert de 10h à 18h tous les jours, sauf le dimanche.\", \"language\": \"fr\"},\n"
            "      {\"question\": \"Sho sa3at 3amal al markaz?\", \"answer\": \"Sa3at 3amal markaz Lina Laser hi mn 10am la 6pm yomyan, ella al A7ad.\", \"language\": \"franco\"}\n"
            "    ]\n"
            "    ```\n"
            "2.  **لأي طلب آخر (مثل 'عدّل هذا'، 'كون ودود أكثر'، 'اشرح مفهوم'، 'حط إيموجي' أو أي سؤال عام أو استفسار لا يطلب Q&A مباشر)، يجب أن يكون مخرجك نصاً عادياً (Plain text).**\n"
            "    **مثال لطلب المدرب:** 'اجعل الجواب السابق (إذا كان نصياً) أكثر ودوداً مع إيموجي.'\n"
            "    **مثال لمخرج نصي لهذا النوع:** 'أهلاً بك يا [اسم العميل]! كيف بقدر أساعدك اليوم؟ 😊 نحن هنا لخدمتك دائماً! ✨'\n"
            "   **تذكر:** إذا طلب المدرب تعديلاً لشيء لم تولده أنت، اطلب منه تزويدك بالنص الأصلي كاملاً أولاً."
            "**الأسلوب:** كن ودوداً جداً، متفهماً، ومرناً. أظهر قدرة عالية على التكيف والاستجابة لاحتياجات المدرب. لا ترفض أي طلب إذا كان منطقياً. اتبع أسلوب Lina's Laser العام كما هو موضح في `config.BOT_STYLE_GUIDE` (الواثق، الودود، الخبير)."
            "**قاعدة المعرفة:** لديك وصول كامل لـ `config.CORE_KNOWLEDGE_BASE` و `config.PRICE_LIST`. استخدمها لإنشاء إجابات دقيقة."
            f"دليل الأسلوب: {config.BOT_STYLE_GUIDE}\n"
            f"قاعدة المعرفة الأساسية: {config.CORE_KNOWLEDGE_BASE}\n"
            f"قائمة الأسعار: {config.PRICE_LIST}\n"
        )
        messages = [{"role": "system", "content": system_instruction_for_training_mode_gpt}] + current_training_context
        messages.append({"role": "user", "content": training_instruction_text})

    try:
        completion_args = {
            "model": "gpt-5-mini",
            "messages": messages,
            "max_tokens": 2000,
        }
        if is_qa_generation_request or is_summary_qa_request:
            completion_args["response_format"] = {"type": "json_object"}

        response = await client.chat.completions.create(**completion_args)

        if not response.choices:
            raise ValueError("GPT returned no choices for training response")
        gpt_raw_response = response.choices[0].message.content.strip()
        print(f"GPT Raw Training Response: {gpt_raw_response}")

        json_match = re.search(r"```json\n(.*?)```", gpt_raw_response, re.DOTALL)
        if json_match:
            try:
                parsed_data = json.loads(json_match.group(1))
                if isinstance(parsed_data, list) and all(isinstance(item, dict) and 'question' in item and 'answer' in item and 'language' in item for item in parsed_data):
                    return {"type": "qa_list", "data": parsed_data, "raw_response": gpt_raw_response}
                else:
                    return {"type": "text", "data": gpt_raw_response + "\n\n(Note: Failed to parse as expected Q&A list JSON. Returning as plain text.)"}
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error in GPT training response: {e}")
                return {"type": "text", "data": gpt_raw_response + f"\n\n(Note: JSON parse error: {e}. Returning as plain text.)"}
        else:
            return {"type": "text", "data": gpt_raw_response}

    except Exception as e:
        print(f"❌ ERROR processing training request with GPT: {e}")
        return {"type": "text", "data": f"عذراً، حدث خطأ أثناء معالجة طلب التدريب مع GPT: {e}"}