"""
Event handlers module: Startup and shutdown events
Handles initialization of WhatsApp provider and scheduling services.
"""

from __future__ import annotations

from modules.core import app
from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory

# Preserve extracted job modules as part of the event-handlers package surface.
from modules import event_handlers_monitor_jobs as event_handlers_monitor_jobs  # noqa: F401
from modules import event_handlers_populate_jobs as event_handlers_populate_jobs  # noqa: F401
from modules import event_handlers_scheduler as event_handlers_scheduler  # noqa: F401


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize MontyMobile as the default WhatsApp provider on startup"""
    try:
        from services.whatsapp_cloud.legacy_isolation import assert_no_monty_cloud_dual_bind

        assert_no_monty_cloud_dual_bind()
    except RuntimeError as exc:
        # Fail closed when dual-bind detected.
        print(f"❌ WHATSAPP LEGACY/CLOUD CONFLICT: {exc}")
        raise
    except Exception as exc:
        print(f"⚠️ WhatsApp legacy isolation check skipped: {type(exc).__name__}")

    try:
        print("=" * 60)
        print("🚀 INITIALIZING WHATSAPP PROVIDER")
        print("=" * 60)

        # Use MontyMobile as the default provider (new endpoint)
        adapter = WhatsAppFactory.get_adapter("montymobile")
        print(f"✅ MontyMobile adapter initialized: {type(adapter).__name__}")
        print(f"✅ Current provider: {WhatsAppFactory.get_current_provider()}")
        print("=" * 60)
    except Exception as e:
        print(f"❌ ERROR initializing Qiscus adapter: {e}")
        print("⚠️ Bot will continue but WhatsApp functionality may not work")
        import traceback

        traceback.print_exc()

    # Initialize Smart Messaging Scheduler
    try:
        print("=" * 60)
        print("📅 INITIALIZING SMART MESSAGING SCHEDULER")
        print("=" * 60)

        from modules.event_handlers_scheduler import start_smart_messaging_scheduler

        await start_smart_messaging_scheduler(app.state)

        from services.meta_instagram_login_lifecycle import start_instagram_login_lifecycle

        await start_instagram_login_lifecycle(app.state)
        print("✅ Instagram Login lifecycle scheduler started")

    except Exception as e:
        print(f"❌ ERROR initializing Smart Messaging Scheduler: {e}")
        print("⚠️ Smart messaging will not work")
        import traceback

        traceback.print_exc()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup on shutdown"""
    try:
        from services.meta_instagram_login_lifecycle import stop_instagram_login_lifecycle

        await stop_instagram_login_lifecycle(app.state)
    except Exception as e:
        print(f"❌ Error shutting down Instagram Login lifecycle: {e}")
    try:
        if hasattr(app.state, "scheduler"):
            print("🛑 Shutting down Smart Messaging Scheduler...")
            app.state.scheduler.shutdown()
            print("✅ Scheduler shut down successfully")
    except Exception as e:
        print(f"❌ Error shutting down scheduler: {e}")
