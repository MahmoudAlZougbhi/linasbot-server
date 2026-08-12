"""create_appointment: resolve customer name/phone."""

from __future__ import annotations

# ruff: noqa: B020
from services.chat_response_runtime_common import (
    HAIR_REMOVAL_MACHINE_IDS,
    LASER_HAIR_REMOVAL_SERVICE_IDS,
    LOOP_CONTINUE,
    Any,
    _extract_direct_submit_booking_args_from_user_message,
    _fix_misassigned_tattoo_service_for_hair_booking,
    _merge_explicit_user_booking_args,
    _record_tool_round_trip,
    _safe_int,
    config,
    json,
    re,
)


async def handle_create_appointment_name(ns: Any) -> Any:
    if ns.function_name == "create_appointment":
        ns.explicit_booking_args = _extract_direct_submit_booking_args_from_user_message(
            ns.user_input,
            phone=ns.customer_phone_clean
            or config.user_data_whatsapp.get(ns.user_id, {}).get("phone_number")
            or ns.user_id,
            current_gender=ns.current_gender,
            fallback_name=config.user_names.get(ns.user_id, ns.user_name),
        )
        _merge_explicit_user_booking_args(ns.function_args, ns.explicit_booking_args)
        ns.explicit_machine_id = (
            _safe_int(ns.explicit_booking_args.get("machine_id"))
            if isinstance(ns.explicit_booking_args, dict)
            else None
        )
        ns.explicit_service_id = (
            _safe_int(ns.explicit_booking_args.get("service_id"))
            if isinstance(ns.explicit_booking_args, dict)
            else None
        )
        if (
            ns.explicit_service_id in LASER_HAIR_REMOVAL_SERVICE_IDS
            and ns.explicit_machine_id is not None
            and ns.explicit_machine_id not in HAIR_REMOVAL_MACHINE_IDS
        ):
            ns.tool_output = {
                "success": False,
                "error_type": "validation_error",
                "conflicting_fields": {
                    "machine_id": {
                        "detail": "Requested machine is unavailable. Trio is no longer available.",
                        "machine_id": ns.explicit_machine_id,
                        "allowed_machine_ids": sorted(HAIR_REMOVAL_MACHINE_IDS),
                    }
                },
                "human_readable_reason": "Trio is no longer available. Ask the user to choose Neo, Quadro, or Candela.",
            }
            ns.tool_content = json.dumps(ns.tool_output, ensure_ascii=False, default=str)
            ns.tool_round_trips.append(
                _record_tool_round_trip(ns.function_name, ns.function_args, ns.tool_content, ns.tool_output)
            )
            ns.messages.append(
                {
                    "tool_call_id": ns.tool_call.id,
                    "role": "tool",
                    "name": ns.function_name,
                    "content": ns.tool_content,
                }
            )
            return LOOP_CONTINUE
        _fix_misassigned_tattoo_service_for_hair_booking(
            ns.function_args,
            ns.current_gender,
            ns.user_input,
            ns.current_context_messages,
        )
        # Extract customer name and phone from the conversation if not provided in tool args
        # CRITICAL FIX: For Qiscus, user_id is room_id, NOT phone number
        # Get actual phone number from user_data_whatsapp
        ns.phone_number = config.user_data_whatsapp.get(ns.user_id, {}).get("phone_number")

        # Fallback: If no phone_number stored, check if user_id looks like a phone number
        if not ns.phone_number:
            # Check if user_id looks like a phone number (starts with + and has digits)
            if ns.user_id.startswith("+") or (
                ns.user_id.replace("+", "").replace("-", "").replace(" ", "").isdigit() and len(ns.user_id) >= 8
            ):
                ns.phone_number = ns.user_id
                print(
                    f"DEBUG: Using user_id as phone_number (Meta/Dialog360 format): ***{str(ns.phone_number)[-4:] if ns.phone_number else ''}"
                )
            else:
                print(
                    f"ERROR: No phone_number found for user {ns.user_id} and user_id doesn't look like a phone number"
                )
        else:
            print(
                f"DEBUG: Using stored phone_number from user_data: ***{str(ns.phone_number)[-4:] if ns.phone_number else ''}"
            )

        # CRITICAL FIX: Priority 1 - Use collected name (protected from webhook)
        ns.user_data_dict = config.user_data_whatsapp.get(ns.user_id, {})
        ns.customer_name = ns.user_data_dict.get("collected_name")

        if ns.customer_name:
            print(f"DEBUG: Using protected collected name: {ns.customer_name}")

        # Priority 2: Check config.user_names (might be overwritten by webhook)
        if not ns.customer_name:
            ns.customer_name = config.user_names.get(ns.user_id)
            # Skip if Arabic (causes API 500 errors)
            if ns.customer_name and re.search(r"[\u0600-\u06FF]", ns.customer_name):
                print(f"WARNING: Skipping Arabic name from config: {ns.customer_name}")
                ns.customer_name = None
            elif ns.customer_name:
                print(f"DEBUG: Using name from config.user_names: {ns.customer_name}")

        # Priority 3: Search conversation history for Latin name
        # Check BOTH user messages AND bot messages (GPT might have confirmed the name)
        if not ns.customer_name:
            for ns.msg_entry in reversed(ns.current_context_messages + [{"role": "user", "content": ns.user_input}]):
                ns.msg_content = ns.msg_entry["content"].strip()
                ns.msg_role = ns.msg_entry["role"]

                # Pattern 1: User explicitly states their name
                if ns.msg_role == "user":
                    ns.name_match = re.search(
                        r"(?:my name is|i am|i'm|call me|انا اسمي|اسمي|اسمي هو|je\s*m['\s]?appelle|je suis|moi c'est)\s+([A-Za-zÀ-ÿا-ي\s]{2,50})",
                        ns.msg_content,
                        re.IGNORECASE | re.UNICODE,
                    )
                    if ns.name_match:
                        ns.potential_name = ns.name_match.group(1).strip()

                        # Validate: name should not contain booking-related words
                        ns.booking_keywords = [
                            "book",
                            "appointment",
                            "schedule",
                            "reserve",
                            "موعد",
                            "حجز",
                            "want",
                            "need",
                            "like",
                            "please",
                            "tomorrow",
                            "today",
                            "بدي",
                            "بحب",
                            "just",
                            "an",
                            "the",
                            "a",
                            "have",
                            "get",
                        ]

                        ns.contains_booking_word = any(
                            ns.keyword in ns.potential_name.lower() for ns.keyword in ns.booking_keywords
                        )

                        if not ns.contains_booking_word:
                            ns.customer_name = ns.potential_name
                            print(f"DEBUG: Extracted name from user message with prefix: {ns.customer_name}")
                            break

                # Pattern 2: Bot confirmed the name (e.g., "Your name is John Smith")
                elif ns.msg_role == "assistant":
                    ns.name_match = re.search(
                        r"(?:your name is|you are|you\'re called|اسمك|اسمك هو|ton nom est)\s+([A-Za-zÀ-ÿا-ي\s]{2,50})",
                        ns.msg_content,
                        re.IGNORECASE | re.UNICODE,
                    )
                    if ns.name_match:
                        ns.potential_name = ns.name_match.group(1).strip()

                        # Clean up any trailing punctuation or words
                        ns.potential_name = re.sub(
                            r"\s+(and|et|و|،|,|\.).*$", "", ns.potential_name, flags=re.IGNORECASE
                        )

                        # Validate length
                        if 2 <= len(ns.potential_name) <= 50:
                            ns.customer_name = ns.potential_name
                            print(f"DEBUG: Extracted name from bot confirmation: {ns.customer_name}")
                            break

                # Pattern 3: User provides JUST their name (2-4 words, proper capitalization)
                # This is risky but necessary when user responds to "What is your name?"
                elif ns.msg_role == "user" and not ns.customer_name:
                    # Check if this looks like a standalone name response
                    ns.words = ns.msg_content.split()
                    if 1 <= len(ns.words) <= 4:
                        # Must start with capital letter or be Arabic
                        if re.match(r"^[A-ZÀ-Ÿا-ي]", ns.msg_content, re.UNICODE) and re.match(
                            r"^[A-Za-zÀ-ÿا-ي\s\-\']+$", ns.msg_content, re.UNICODE
                        ):
                            # Exclude common words and booking terms
                            ns.excluded_words = [
                                "yes",
                                "no",
                                "ok",
                                "okay",
                                "sure",
                                "please",
                                "thanks",
                                "hello",
                                "hi",
                                "book",
                                "appointment",
                                "schedule",
                                "tomorrow",
                                "today",
                                "now",
                                "نعم",
                                "لا",
                                "تمام",
                                "ماشي",
                                "شكرا",
                                "مرحبا",
                                "موعد",
                                "حجز",
                                "oui",
                                "non",
                                "merci",
                                "bonjour",
                                "salut",
                            ]

                            if ns.msg_content.lower() not in ns.excluded_words:
                                # Check if previous bot message was asking for name
                                # Look back in conversation for name request
                                ns.asking_for_name = False
                                for ns.prev_msg in reversed(ns.current_context_messages):
                                    if ns.prev_msg["role"] == "assistant":
                                        ns.prev_content = ns.prev_msg["content"].lower()
                                        if any(
                                            ns.phrase in ns.prev_content
                                            for ns.phrase in [
                                                "your name",
                                                "full name",
                                                "what is your name",
                                                "may i have your name",
                                                "اسمك",
                                                "ما اسمك",
                                                "شو اسمك",
                                                "votre nom",
                                                "ton nom",
                                                "quel est votre nom",
                                            ]
                                        ):
                                            ns.asking_for_name = True
                                            break
                                    # Only check last 2 bot messages
                                    if ns.prev_msg["role"] == "assistant":
                                        break

                                if ns.asking_for_name:
                                    ns.customer_name = ns.msg_content.strip()
                                    print(
                                        f"DEBUG: Extracted standalone name (response to name question): {ns.customer_name}"
                                    )
                                    break

                if ns.customer_name:
                    break
        # === NEW PATCH: Persist detected customer name ===
        if ns.customer_name:
            # Save name in runtime config
            config.user_data_whatsapp[ns.user_id]["user_name"] = ns.customer_name
            config.user_names[ns.user_id] = ns.customer_name

            # Persist to Firestore asynchronously
            try:
                from utils.utils import save_user_name_to_firestore

                await save_user_name_to_firestore(ns.user_id, ns.customer_name)
            except Exception as e:
                print(f"⚠️ Could not persist user name for {ns.user_id}: {e}")

        # Update function_args with inferred phone/name if not present
