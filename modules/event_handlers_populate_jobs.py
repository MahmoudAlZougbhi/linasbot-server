"""Smart messaging populate jobs for event handlers (LOC split)."""

from __future__ import annotations

from services.appointment_scheduler import (
    populate_missed_month_messages,
    populate_missed_yesterday_messages,
    populate_one_month_followups,
    populate_scheduled_messages_from_appointments,
)


async def populate_messages_job() -> None:
    """Fetch real appointments from backend and populate scheduled messages"""
    try:
        print("🔄 POPULATING SCHEDULED MESSAGES FROM REAL APPOINTMENTS")
        print("=" * 80)
        result = await populate_scheduled_messages_from_appointments()
        if result.get("success"):
            print(f"✅ {result.get('message')}")
            print("   📊 Statistics:")
            print(f"   - Appointments found: {result.get('total_appointments', 0)}")
            print(f"   - Processed: {result.get('processed_appointments', 0)}")
            print(f"   - Failed: {result.get('failed_appointments', 0)}")
            print(f"   - Messages scheduled: {result.get('total_messages', 0)}")
            print(f"   - Total in dict: {result.get('scheduled_messages_count', 0)}")
        else:
            print(f"⚠️ Failed to populate messages: {result.get('message')}")
        print("=" * 80)
    except Exception as e:
        print(f"❌ Error populating scheduled messages: {e}")
        import traceback

        traceback.print_exc()

# Job 0A3: Populate 1-MONTH FOLLOW-UP messages (from last month's appointments)
async def populate_one_month_job() -> None:
    """Fetch last month's appointments and populate 1-month follow-up messages"""
    try:
        print("📅 POPULATING 1-MONTH FOLLOW-UP MESSAGES")
        print("=" * 80)
        result = await populate_one_month_followups()
        if result.get("success"):
            print(f"✅ {result.get('message')}")
            print(f"   📊 Month: {result.get('month', 'N/A')}")
            print(f"   - Appointments found: {result.get('total_appointments', 0)}")
            print(f"   - Follow-ups scheduled: {result.get('total_messages', 0)}")
        else:
            print(f"⚠️ Failed to populate 1-month messages: {result.get('message')}")
        print("=" * 80)
    except Exception as e:
        print(f"❌ Error populating 1-month messages: {e}")
        import traceback

        traceback.print_exc()

# Job 0A4: Populate MISSED-MONTH messages (from this month's missed appointments)
async def populate_missed_month_job() -> None:
    """Fetch this month's missed appointments and populate missed-month messages"""
    try:
        print("📅 POPULATING MISSED-MONTH MESSAGES")
        print("=" * 80)
        result = await populate_missed_month_messages()
        if result.get("success"):
            print(f"✅ {result.get('message')}")
            print(f"   📊 Month: {result.get('month', 'N/A')}")
            print(f"   - Missed appointments found: {result.get('total_missed', 0)}")
            print(f"   - Messages scheduled: {result.get('total_messages', 0)}")
        else:
            print(f"⚠️ Failed to populate missed-month messages: {result.get('message')}")
        print("=" * 80)
    except Exception as e:
        print(f"❌ Error populating missed-month messages: {e}")
        import traceback

        traceback.print_exc()

# Job 0A5: Populate MISSED-YESTERDAY messages (from yesterday's paused appointments)
async def populate_missed_yesterday_job() -> None:
    """Fetch yesterday's paused appointments and populate missed-yesterday messages"""
    try:
        print("📅 POPULATING MISSED-YESTERDAY MESSAGES")
        print("=" * 80)
        result = await populate_missed_yesterday_messages()
        if result.get("success"):
            print(f"✅ {result.get('message')}")
            print(f"   📅 Date: {result.get('date', 'N/A')}")
            print(f"   - Paused appointments found: {result.get('total_missed', 0)}")
            print(f"   - Messages scheduled: {result.get('total_messages', 0)}")
        else:
            print(f"⚠️ Failed to populate missed-yesterday messages: {result.get('message')}")
        print("=" * 80)
    except Exception as e:
        print(f"❌ Error populating missed-yesterday messages: {e}")
        import traceback

        traceback.print_exc()
