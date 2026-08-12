"""
LinasLaser Agent API integrations.

Implementation is split by domain under 500 lines; this module re-exports the public API.
"""

from __future__ import annotations

from services.api_integrations_booking import (  # noqa: F401
    _body_part_session_row,
    _clean_body_part_ids_for_api,
    _clean_body_parts_with_sessions_for_api,
    _safe_float_amount,
    add_appointment_discount,
    create_appointment,
    extract_appointment_total_from_api_payload,
    sync_appointment_agreed_price,
    update_appointment_date,
)
from services.api_integrations_catalog import (  # noqa: F401
    get_body_parts,
    get_branches,
    get_clinic_hours,
    get_machines,
    get_service_data,
    get_services,
)
from services.api_integrations_customers import (  # noqa: F401
    check_customer_gender,
    create_customer,
    generate_daily_report_command,
    update_customer_gender,
)
from services.api_integrations_edit import (  # noqa: F401
    edit_appointment,
    update_paused_appointment,
)
from services.api_integrations_http import (  # noqa: F401
    REPORT_LOG_FILE,
    _make_api_request,
    _normalize_update_status_endpoint,
    _post_update_status_logged,
    _root_api_url,
    _update_status_post_url_candidates,
    api_client,
    log_report_event,
)
from services.api_integrations_reminders import (  # noqa: F401
    check_appointment_payment,
    check_next_appointment,
    get_appointment_details,
    get_missed_appointments,
    get_paused_appointments_between_dates,
    get_pricing_details,
    get_sessions_count_by_phone,
    move_client_branch,
    send_appointment_reminders,
)
from services.api_integrations_status import (  # noqa: F401
    _phone_clean_for_appointment_api,
    add_customer_note,
    get_all_customers,
    get_clients_without_today,
    get_customer_appointments,
    get_customer_by_phone,
    get_customer_sessions,
    pause_appointment,
    resume_appointment,
    update_appointments_status,
)
