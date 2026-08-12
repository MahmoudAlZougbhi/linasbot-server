"""OpenAI tool schema: CRM lookup, hours, customer records."""

from __future__ import annotations

from typing import Any

OPENAI_LOOKUP_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_branches",
            "description": "Retrieves a list of all branches associated with the clinic.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_services",
            "description": "Retrieves a list of all services offered by the clinic.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_machines",
            "description": "Lists machines in the clinic. Call when booking laser hair removal (service 1 or 12) to pick the device the customer agreed to (Neo, Quadro, Candela). Trio is no longer available. For non-hair services, do not ask for or send machine_id.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_service_data",
            "description": (
                "GET /service/data (Appointment API): returns pricing and body_parts options for a service_id, "
                "optional machine_id. Recommended before create to show price/options to the user (per BOC doc flow)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_id": {"type": "integer", "description": "Service to quote (same as booking)."},
                    "machine_id": {"type": "integer", "description": " filter when machine is known."},
                },
                "required": ["service_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_body_parts",
            "description": (
                "Returns the official CRM list of bookable body areas (id + name) for a service, optionally filtered by machine. "
                "REQUIRED before submit_booking_intent whenever the user names one or more areas (Arabic/English/franco) "
                "or you need numeric body_part_ids. Always pass the same service_id you are booking "
                "(1 = laser hair removal men, 12 = women, 13 = tattoo, etc.). "
                "When a machine is required/selected for this booking, pass machine_id too so the API can return the exact body-part list for that service+machine. "
                "Match each user-mentioned area to rows in this response and pass every matching id in submit_booking_intent.body_part_ids "
                "(multiple areas = multiple ids). Do not guess ids from memory or pricing text; use this tool. "
                "If this tool returns success=false, read hint_for_model if present: do NOT ask the user for 'CRM/system' area names when "
                "they already described the body location; use submit_booking_intent.body_part with their wording instead when possible."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_id": {
                        "type": "integer",
                        "description": (
                            "Same service as the booking conversation, e.g. 1 or 12 for laser hair removal "
                            "(use 1 for male / شاب، 12 for female / صبية). Required for correct area ids."
                        ),
                    },
                    "machine_id": {
                        "type": "integer",
                        "description": " but recommended when machine is known/required for the booking; filters body parts by service+machine.",
                    },
                },
                "required": ["service_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_clinic_hours",
            "description": "Returns the clinic's working hours for each day of the week.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_appointment_reminders",
            "description": "Triggers the sending of appointment reminders to clients.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "format": "date",
                        "description": "Specific date for reminders (YYYY-MM-DD, optional).",
                    },
                    "phone": {
                        "type": "string",
                        "description": "Client's phone number (required if user_code not provided).",
                    },
                    "user_code": {
                        "type": "string",
                        "description": "Client's unique user code (required if phone is not provided).",
                    },
                },
                "required": [],  # API docs state "required if other not provided"
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_next_appointment",
            "description": (
                "Returns the client's next appointment and (when available) customer_appointments: all rows from the system. "
                "For user-facing replies: **one line per row**, each starting with the numeric **appointment_id** from JSON (same as id). "
                "Include date, time, service, branch, machine/device, body areas/parts, and price/total **only if** those fields exist in the JSON—never invent prices. "
                "When several rows exist and the user must choose (reschedule, resume from pause, etc.), ask them to send the **appointment_id** they want "
                "(or the line number 1/2/3 matching your list). Use tool JSON to map their answer to the correct id for update_appointment_date. "
                "If status is paused/postponed, update that existing row—do not create a new appointment."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Client's phone number."},
                    "user_code": {"type": "string", "description": "Client's unique user code (optional)."},
                },
                "required": ["phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sessions_count_by_phone",
            "description": "Returns the number of sessions a client has attended, based on their phone number or user code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Client's phone number (required if user_code is not provided).",
                    },
                    "user_code": {
                        "type": "string",
                        "description": "Client's unique user code (required if phone is not provided).",
                    },
                    "service_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Filter sessions by specific service IDs (e.g., service_ids[]=1&service_ids[]=2).",
                    },
                },
                "required": [],  # API says phone or user_code required
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_client_branch",
            "description": "Moves a client's future appointments to a different branch. new_date is optional: include only when the Agent API / ops require rescheduling moved rows to a specific day.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Client's phone number."},
                    "from_branch_id": {"type": "integer", "description": "ID of the current branch."},
                    "to_branch_id": {"type": "integer", "description": "ID of the new branch."},
                    "new_date": {
                        "type": "string",
                        "format": "date",
                        "description": ". YYYY-MM-DD when a new date must be sent with the move; omit for branch-only move if allowed by API.",
                    },
                    "user_code": {"type": "string", "description": "Client's unique user code (optional)."},
                    "response_confirm": {
                        "type": "string",
                        "description": "Confirmation of the move, default 'yes'.",
                    },
                },
                "required": ["phone", "from_branch_id", "to_branch_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_appointment_payment",
            "description": "Checks the payment status of a client's appointments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Client's phone number."},
                    "user_code": {"type": "string", "description": "Client's unique user code (optional)."},
                },
                "required": ["phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_missed_appointments",
            "description": "Returns a list of missed appointments for the clinic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "format": "date",
                        "description": "Filter missed appointments by a specific date (YYYY-MM-DD, optional).",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_by_phone",  # NEW API Function
            "description": "Retrieves customer details by phone number.",
            "parameters": {
                "type": "object",
                "properties": {"phone": {"type": "string", "description": "Customer's phone number."}},
                "required": ["phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_customer_gender",
            "description": "Returns the gender of a customer based on the provided identifier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Customer's phone number (required if user_code is not provided).",
                    },
                    "user_code": {
                        "type": "string",
                        "description": "Customer's unique user code (required if phone is not provided).",
                    },
                },
                "required": [],  # API says phone or user_code is required
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_relevant_knowledge",
            "description": "Retrieve relevant knowledge/price/style files for the user's question. Call this when you need more context to answer accurately (e.g. body areas, service details, pricing philosophy). The bot will send the user message to a selector AI, get selected files, and return their content. Use that content to formulate your reply.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_message": {
                        "type": "string",
                        "description": "The user's message or question to match against available files.",
                    }
                },
                "required": ["user_message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_appointment_details",
            "description": "Retrieves detailed information about a specific appointment by appointment ID (customer, date, time, service, machine, branch, status, price, payment_status).",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "integer", "description": "The ID of the appointment to retrieve."}
                },
                "required": ["appointment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sync_appointment_agreed_price",
            "description": (
                "When you and the customer have **explicitly agreed** on a **final total price** for a specific appointment already in CRM "
                "(new booking just created, existing row, or after any change)—call this so the backend can align the system price. "
                "The server reads the current CRM total (or uses `system_total_known` if you pass it from the last booking response), "
                "and if the CRM price is **higher** than the agreed amount, it POSTs `appointments/discount/add` with the difference. "
                "**Important:** after **edit_appointment** / **update_paused_appointment** changes **body parts** or **machine**, CRM may show a **new** list total—call this again with the **same** agreed_price and **same** appointment_id to re-apply alignment. "
                "Do not invent numbers: only use after the user clearly confirmed the price. "
                "If agreed price is higher than CRM, the tool will not increase CRM price—explain honestly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {
                        "type": "integer",
                        "description": "CRM appointment id (from booking/create response, check_next_appointment, or get_appointment_details).",
                    },
                    "agreed_price": {
                        "type": "number",
                        "description": "Final total price you and the customer agreed on (same currency as CRM).",
                    },
                    "system_total_known": {
                        "type": "number",
                        "description": (
                            ". Pass the CRM total from the **last** create/booking tool response if you have it, "
                            "to avoid an extra lookup. Omit to fetch current price from get_appointment_details."
                        ),
                    },
                },
                "required": ["appointment_id", "agreed_price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_clients_without_today",
            "description": "Returns active clients who do not have appointments on the given date. Useful for outreach or availability checks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "format": "date",
                        "description": "Date to check (YYYY-MM-DD). Defaults to today if not provided.",
                    },
                    "branch_id": {"type": "integer", "description": "Filter by branch ID (optional)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_sessions",
            "description": "Returns sessions (appointments) for a customer by customer_id, including service, body area, session number, status, and notes. Use customer_id from get_customer_by_phone response.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "integer",
                        "description": "Customer ID (from get_customer_by_phone data.id).",
                    }
                },
                "required": ["customer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_customer_note",
            "description": "Adds a note to the customer's record (e.g. follow-up request, preference, complaint).",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Customer's phone number."},
                    "note": {"type": "string", "description": "Note content (max 1000 characters)."},
                },
                "required": ["phone", "note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_customers",
            "description": "Returns a list of all customers. Can filter by creation date (date, from, to).",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "format": "date",
                        "description": "Customers created on this date (YYYY-MM-DD).",
                    },
                    "from_date": {
                        "type": "string",
                        "format": "date",
                        "description": "Customers created on or after this date (YYYY-MM-DD).",
                    },
                    "to_date": {
                        "type": "string",
                        "format": "date",
                        "description": "Customers created on or before this date (YYYY-MM-DD).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_customer",
            "description": "Creates a new customer record within the clinic's database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Full name of the customer."},
                    "phone": {"type": "string", "description": "Customer's phone number."},
                    "email": {"type": "string", "format": "email", "description": "Customer's email (optional)."},
                    "gender": {
                        "type": "string",
                        "enum": ["Male", "Female"],
                        "description": "Customer's gender (must be 'Male' or 'Female').",
                    },  # Updated enum
                    "branch_id": {
                        "type": "integer",
                        "description": "Preferred branch ID for the customer.",
                    },  # Made required
                    "date_of_birth": {
                        "type": "string",
                        "format": "date",
                        "description": "Customer's date of birth (YYYY-MM-DD, optional).",
                    },
                },
                "required": ["name", "phone", "gender", "branch_id"],  # Updated required fields
            },
        },
    },
]
