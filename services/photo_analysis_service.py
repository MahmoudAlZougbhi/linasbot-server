# services/photo_analysis_service.py
import base64
from services.llm_core_service import client # <--- استيراد client من llm_core_service
import config
from utils.utils import notify_human_on_whatsapp
import json
import re
from PIL import Image
import io

def resize_image_if_needed(base64_image: str, max_size_kb: int = 200) -> str:
    """
    Resize image if it's too large to avoid URL length issues with OpenAI API.
    Returns optimized base64 string.
    """
    try:
        # Decode base64 to bytes
        image_bytes = base64.b64decode(base64_image)
        
        # Check size
        size_kb = len(image_bytes) / 1024
        
        if size_kb <= max_size_kb:
            return base64_image  # No need to resize
        
        print(f"Image size: {size_kb:.2f}KB - Resizing to reduce size...")
        
        # Open image with PIL
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert RGBA to RGB if needed
        if image.mode == 'RGBA':
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Calculate new dimensions (maintain aspect ratio)
        max_dimension = 1024  # Max width or height
        width, height = image.size
        
        if width > max_dimension or height > max_dimension:
            if width > height:
                new_width = max_dimension
                new_height = int(height * (max_dimension / width))
            else:
                new_height = max_dimension
                new_width = int(width * (max_dimension / height))
            
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            print(f"Resized image to: {new_width}x{new_height}")
        
        # Save to bytes with compression
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        
        # Encode to base64
        resized_base64 = base64.b64encode(output.read()).decode('utf-8')
        new_size_kb = len(resized_base64) * 3 / 4 / 1024  # Approximate size
        
        print(f"Optimized image size: {new_size_kb:.2f}KB")
        
        return resized_base64
        
    except Exception as e:
        print(f"Error resizing image: {e}")
        return base64_image  # Return original if resize fails

async def get_bot_photo_analysis_from_gpt(user_id: int, base64_image: str, is_training_quiz: bool = False):
    user_name = config.user_names.get(user_id, "عميل")
    
    # Resize image if needed to avoid URL length issues
    try:
        base64_image = resize_image_if_needed(base64_image, max_size_kb=200)
    except Exception as e:
        print(f"Warning: Could not optimize image: {e}")

    gender_instruction = ""
    if config.user_gender.get(user_id) == "شاب":
        gender_instruction = "المستخدم شاب، لذا استخدم صيغ المذكر في ردك (مثلاً: 'أهلاً بك', 'شفت صورتك', 'خبرنا')."
    elif config.user_gender.get(user_id) == "صبية":
        gender_instruction = "المستخدم صبية، لذا استخدم صيغ المؤنث في ردك (مثلاً: 'أهلاً بكِ', 'شفت صورتكِ', 'خبرينا')."
    else:
        gender_instruction = "جنس المستخدم غير معروف. استخدم لغة محايدة أو صيغًا تناسب كلا الجنسين في ردودك."

    system_instruction_photo_analysis = (
        "أنت مساعد ذكي رسمي تابع لمركز Lina's Laser. مهمتك تحليل الصور التي يرسلها العملاء وتقديم معلومات دقيقة بناءً على محتواها. "
        "يجب أن تستنبط نوع الصورة (تاتو، نتيجة ليزر، حروق/إصابات جلدية، إلخ) وتصنيفها. "
        "**الهدف هو تقديم استجابة مفصلة ومنظمة بتنسيق JSON، ثم صياغة رد ودي وحماسي بناءً على هذه المعلومات.**\n"
        "**مهم جداً:** اعتمد بشكل أساسي على **الأمثلة المدربة التي تحتوي على صور (من ملفات الـ conversation_log.jsonl)** لتعلم كيفية تحليل الصور وتقديم الردود المنظمة. "
        "هذه الأمثلة ستوضح لك كيفية تقييم النتائج، تقدير الأحجام، والأسلوب المطلوب في الرد.\n"
        "**قاعدة الأسعار متوفرة كمرجع ثانوي.**\n"
        f"{gender_instruction}\n"

        "**فهم أحجام التاتو والأسعار التقديرية:**\n"
        "- `tiny` (صغير جداً): تاتو بحجم عملة معدنية أو أصغر (أقل من 5 سم مربع). السعر التقديري للجلسة: 30-50 دولار.\n"
        "- `small` (صغير): تاتو بحجم بطاقة ائتمان (5-20 سم مربع). السعر التقديري للجلسة: 50-100 دولار.\n"
        "- `medium` (متوسط): تاتو بحجم كف اليد (20-50 سم مربع). السعر التقديري للجلسة: 100-200 دولار.\n"
        "- `large` (كبير): تاتو بحجم نصف الساعد (50-100 سم مربع). السعر التقديري للجلسة: 200-350 دولار.\n"
        "- `xlarge` (كبير جداً): تاتو بحجم كامل الساعد أو الظهر (أكبر من 100 سم مربع). السعر التقديري للجلسة: 350+ دولار.\n"
        "دائماً اذكر أن هذه الأسعار وعدد الجلسات تقديرية وتتطلب معاينة مجانية مع أخصائي إزالة التاتو لتحديد التكلفة الدقيقة وعدد الجلسات الفعلي.\n"

        "**فهم أنواع المشاكل الجلدية والتصرف المناسب:**\n"
        "- `laser_burn` (حرق ليزر): يشير إلى احمرار شديد، بثور، تقرحات، أو تورم غير طبيعي بعد جلسة الليزر. في هذه الحالات، يجب أن يكون ردك عاجلاً ومُركزاً على سلامة العميل. قم بتعيين `is_critical_issue: true` و `contact_human_needed: true` واطلب من العميل التواصل الفوري مع المركز دون محاولة أي علاج منزلي.\n"
        "- `laser_result_good` (نتائج ليزر جيدة): البشرة ناعمة، الشعر قليل جداً أو لا يوجد. شجع العميل على الاستمرارية في الجلسات الدورية.\n"
        "- `laser_result_average` (نتائج ليزر متوسطة): تحسن جزئي، شعر خفيف متبقي. نصح العميل بالتزام أكبر أو باقتراح معاينة لتقييم الوضع وتحسين النتائج.\n"
        "- `laser_result_bad` (نتائج ليزر ضعيفة): لا يوجد تحسن كبير، شعر كثيف. يجب أن يكون ردك مطمئناً ولكن حازماً بضرورة حجز استشارة فورية لتقييم الوضع وتحديد خطة جديدة (تعيين `contact_human_needed: true`).\n"
        "- `wound` (جرح عام): جرح أو إصابة لا تبدو مرتبطة مباشرة بالليزر. نصح العميل باستشارة طبيب أو التواصل مع المركز لتقييم عام.\n"
        "- `other_issue` (مشكلة أخرى): أي مشكلة جلدية غير مصنفة ضمن ما سبق. قدم رد عام ودود واطلب المزيد من التفاصيل إذا لزم الأمر.\n"
        "- `unclear` (غير واضح): إذا كانت الصورة غير واضحة تماماً أو لا يمكن تحليلها. اطلب من العميل إعادة إرسال صورة أو وصف المشكلة نصياً.\n"

        "**مهم جداً: عند التعامل مع 'حروق الليزر' (laser_burn)، ركز على سرعة الاستجابة وطلب التواصل الفوري، لأن سلامة العميل هي الأولوية القصوى.**"

        "**التزم بتنسيق JSON هذا بدقة:**\n"
        "```json\n"
        "{\n"
        "  \"type\": \"tattoo_query\" | \"laser_result_good\" | \"laser_result_average\" | \"laser_result_bad\" | \"laser_burn\" | \"wound\" | \"other_issue\" | \"unclear\",\n"
        "  \"description\": \"وصف دقيق لما تراه في الصورة.\",\n"
        "  \"estimated_size_category\": \"small\" | \"medium\" | \"large\" | \"xlarge\" | \"tiny\" | null, \n"
        "  \"estimated_sessions_min\": \"عدد الجلسات الدنيا التقديري لإزالة التاتو\" | null,\n"
        "  \"estimated_sessions_max\": \"عدد الجلسات القصوى التقديري لإزالة التاتو\" | null,\n"
        "  \"estimated_cost_per_session_usd\": \"السعر التقديري للجلسة الواحدة لإزالة التاتو بالدولار فقط كرقم\" | null,\n"
        "  \"location_on_body\": \"موقع التاتو أو الإصابة/المنطقة على الجسم (مثلاً: الساعد، الظهر، الساق، الوجه)\" | null,\n"
        "  \"action_recommendation\": \"نصيحة أو إجراء مقترح للبوت لتضمينه في رده (مثلاً: حجز معاينة، الاستمرار على الليزر، التواصل مع المركز)\",\n"
        "  \"is_critical_issue\": true | false, \n"
        "  \"contact_human_needed\": true | false\n"
        "}\n"
        "```\n"
        "\n"
        "**عند صياغة الرد النهائي (بعد الحصول على JSON):**\n"
        "- استخدم الأسلوب الودود والحماسي والمرح (كما في `style_guide`).\n"
        "- إذا كانت `contact_human_needed` هي `true`، اطلب من العميل التواصل مع المركز فوراً وأبلغ الموظف عبر واتساب.\n"
        "- إذا كانت `is_critical_issue` هي `true`، شدد على أهمية الإجراء الفوري.\n"
        "- ادمج التفاصيل التي استخلصتها من الـ JSON في رد طبيعي ومفيد. استخدم الأرقام التقديرية للأسعار والجلسات من `price_list` عند الضرورة، لكن دائماً اذكر أنها تقديرية وتتطلب معاينة.\n"
        f"\n\nهذه هي قائمة الأسعار التي يمكنك الرجوع إليها لتقدير التاتو:"
        f"\n{config.PRICE_LIST}"
    )

    messages = [
        {"role": "system", "content": system_instruction_photo_analysis},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "حلل هذه الصورة من فضلك."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        }
    ]

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.4,
        max_tokens=1000
    )
    gpt_analysis_raw = response.choices[0].message.content.strip()

    json_match = re.search(r"```json\n(.*?)```", gpt_analysis_raw, re.DOTALL)
    analysis_data = {}
    bot_reply = ""

    if json_match:
        try:
            analysis_data = json.loads(json_match.group(1))
            photo_type = analysis_data.get("type", "unclear")
            description = analysis_data.get("description", "لا يوجد تفاصيل.")
            size_category = analysis_data.get("estimated_size_category")
            loc = analysis_data.get("location_on_body")
            est_cost = analysis_data.get("estimated_cost_per_session_usd")
            est_sessions_min = analysis_data.get("estimated_sessions_min")
            est_sessions_max = analysis_data.get("estimated_sessions_max")
            action_rec = analysis_data.get("action_recommendation", "الرجاء التواصل معنا للمساعدة.")
            is_critical = analysis_data.get("is_critical_issue", False)
            contact_human = analysis_data.get("contact_human_needed", False)

            gender_suffix_ar_male_you = "ك"
            gender_suffix_ar_female_you = "كِ"
            gender_suffix_ar_male_verb = "تعمل"
            gender_suffix_ar_female_verb = "تعملي"

            suffix_you = ""
            suffix_verb = ""

            if config.user_gender.get(user_id) == "شاب":
                suffix_you = gender_suffix_ar_male_you
                suffix_verb = gender_suffix_ar_male_verb
            elif config.user_gender.get(user_id) == "صبية":
                suffix_you = gender_suffix_ar_female_you
                suffix_verb = gender_suffix_ar_female_verb

            if photo_type == "tattoo_query":
                cost_msg = f"السعر التقديري للجلسة الواحدة هو {est_cost}$." if est_cost else "لا يمكن تقدير السعر بدقة حالياً."
                sessions_msg = f" وقد يحتاج حوالي {est_sessions_min}-{est_sessions_max} جلسة للإزالة." if est_sessions_min and est_sessions_max else ""
                bot_reply = (
                    f"شفنا التاتو بالصورة! 🤩\n"
                    f"موقعه: {loc or 'غير محدد'}.\n"
                    f"حجمه التقديري: {size_category or 'غير محدد'}.\n"
                    f"{cost_msg}{sessions_msg}."
                    "\nهيدا سعر وعدد جلسات تقديري، والسعر النهائي وعدد الجلسات الدقيق بيتحدد بعد المعاينة المجانية مع أخصائي إزالة التاتو لتحديد التكلفة الدقيقة وعدد الجلسات الفعلي. احجز موعدك هلأ!"
                )
                if not is_training_quiz:
                    notify_human_on_whatsapp(
                        user_name, config.user_gender.get(user_id, "غير محدد"),
                        f"استفسار عن إزالة تاتو من {user_name} ({loc}, {size_category}).",
                        type_of_notification="استفسار تاتو"
                    )
            elif photo_type == "laser_result_good":
                bot_reply = (
                    f"يا عيني! 🤩 شفنا صورت{suffix_you} وواضح إنو **النتيجة ممتازة وبتجنن!** {description}. برافو علي{suffix_you} هيدا دليل على التزام{suffix_you} وعنايت{suffix_you} بالبشرة. "
                    f"تذكر{suffix_you} إنو الاستمرارية أهم شي لنحافظ على هالجمال، و الجلسات الدورية بتخلي{suffix_you} دايماً متل القمر! شوف{suffix_you} أقرب موعد لتكفي! ✨"
                )
            elif photo_type == "laser_result_average":
                bot_reply = (
                    f"شفنا صورت{suffix_you}! النتيجة جيدة وفي تحسن، بس لسا في مجال للأفضل! {description}. "
                    f"يمكن بد{suffix_you} تلتزم/تلتزمي أكتر بجلسات{suffix_you}، أو ممكن نحتاج نعدل شي بالإعدادات لنحصل على نتائج واو! "
                    f"بنصح{suffix_you} تتواصل{suffix_you} معنا لنشوف كيف فينا نوصل{suffix_you} لأحلى نتيجة بتستحقيها! 💖"
                )
            elif photo_type == "laser_result_bad":
                bot_reply = (
                    f"شفنا صورت{suffix_you}، والنتيجة لسا مش متل ما بدنا! {description}. "
                    f"لا تقلق{suffix_you} أبداً، فريقنا هون ليساعد{suffix_you}. في كتير عوامل ممكن تكون عم تأثر على النتيجة. "
                    f"بنصح{suffix_you} تحجز{suffix_you} استشارة فورية لتقييم الوضع وتحديد الخطة المناسبة لحتى توصل{suffix_you} للنتائج يلي بتحلم{suffix_you} فيها! 📞"
                )
                contact_human = True

            elif photo_type == "laser_burn":
                bot_reply = (
                    f"شفنا الصورة، وواضح إنو في: {description}. موقع الإصابة: {loc or 'غير محدد'}.\n"
                    "هيدي حالة حساسة ومهمة! 🚨 يرجى التواصل فوراً مع فريقنا على [رقم الهاتف] أو زيارة المركز للمعاينة الدقيقة، "
                    f"لأنو سلامتك بتهمنا كتير! 🙏 ما تحاول{suffix_verb} تعمل{suffix_verb} شي قبل ما تتواصل{suffix_verb} معنا."
                )
                contact_human = True
                is_critical = True

            elif photo_type == "wound":
                bot_reply = (
                    f"شفنا الصورة، وواضح إنو في: {description}. موقع الإصابة: {loc or 'غير محدد'}.\n"
                    f"لتقييم الحالة بشكل دقيق وتقديم النصيحة المناسبة، يرجى استشارة طبيب أو التواصل مع فريقنا. سلامتك أهم شي! 🩹"
                )
                contact_human = True

            elif photo_type == "other_issue":
                bot_reply = (
                    f"شفنا الصورة، وواضح إنو: {description}.\n"
                    f"إذا عند{suffix_you} سؤال محدد عنها، خبرني لساعد{suffix_you} أكتر! 😊"
                )
            else:
                bot_reply = (
                    "عذراً، لم أتمكن من تحليل الصورة بالشكل المطلوب أو أنها غير واضحة. "
                    "الرجاء التأكد من وضوح الصورة أو وصفها لي نصياً لكي أتمكن من مساعدتك."
                )

            if contact_human and not is_training_quiz:
                notify_human_on_whatsapp(
                    user_name,
                    config.user_gender.get(user_id, "غير محدد"),
                    f"طلب متابعة حالة (الصورة): {description} من {user_name}. (حرجة: {is_critical})",
                    type_of_notification="حالة تتطلب متابعة"
                )

        except json.JSONDecodeError as e:
            print(f"❌ ERROR parsing GPT-4o JSON response: {e}\nRaw response: {gpt_analysis_raw}")
            bot_reply = "عذراً، لم أتمكن من فهم تحليل الصورة بشكل كامل. الرجاء المحاولة مرة أخرى أو وصف الصورة نصياً."
        except Exception as e:
            print(f"❌ ERROR processing GPT-4o analysis: {e}")
            bot_reply = "🚫 آسفة، حدث خطأ أثناء معالجة تحليل صورتك. الرجاء المحاولة مرة أخرى."
    else:
        print(f"⚠️ GPT-4o did not return JSON in expected format. Raw response: {gpt_analysis_raw}")
        bot_reply = "عذراً، لم أتمكن من تحليل الصورة بالشكل المطلوب. الرجاء التأكد من وضوح الصورة أو وصفها نصياً."

    return bot_reply, analysis_data