"""
WhatsApp Adapter Factory
Creates and manages WhatsApp adapters (Meta, 360Dialog, ThirdProvider, etc.)
In local/development mode or when ENABLE_SENDING=false, wraps the real adapter
with SafeSendAdapter so outbound messaging is dry-run or sandbox-only.
"""
import os
from typing import Optional
from .base_adapter import WhatsAppAdapter
from .meta_adapter import MetaAdapter
from .dialog360_adapter import Dialog360Adapter
from .qiscus_adapter import QiscusAdapter
from .montymobile_adapter import MontyMobileAdapter
from .safe_send_adapter import SafeSendAdapter

try:
    import config
except ImportError:
    config = None


def _wrap_if_safe_send(adapter: WhatsAppAdapter) -> WhatsAppAdapter:
    """Wrap adapter with SafeSendAdapter when local env or sending disabled."""
    if config is None:
        return adapter
    if getattr(config, "is_local_env", lambda: False)() or not getattr(config, "ENABLE_SENDING", True):
        print("📋 Outbound WhatsApp: dry-run or sandbox-only (APP_MODE=local / ENABLE_SENDING=false)")
        return SafeSendAdapter(adapter)
    return adapter


class WhatsAppFactory:
    """Factory for creating WhatsApp adapters"""
    
    _current_adapter: Optional[WhatsAppAdapter] = None
    _current_provider: str = "montymobile"  # NEW DEFAULT: MontyMobile (new Qiscus endpoint)
    
    @classmethod
    def get_adapter(cls, provider: str = None) -> WhatsAppAdapter:
        """Get WhatsApp adapter instance"""
        if provider:
            cls._current_provider = provider
        
        # If adapter exists and is the same provider, return it
        if cls._current_adapter and hasattr(cls._current_adapter, 'provider_name'):
            if cls._current_adapter.provider_name == cls._current_provider:
                return cls._current_adapter
        
        # Create new adapter
        if cls._current_provider == "meta":
            cls._current_adapter = cls._create_meta_adapter()
        elif cls._current_provider == "360dialog":
            cls._current_adapter = cls._create_360dialog_adapter()
        elif cls._current_provider == "qiscus":
            cls._current_adapter = cls._create_qiscus_adapter()
        elif cls._current_provider == "montymobile":
            cls._current_adapter = cls._create_montymobile_adapter()
        else:
            raise ValueError(f"Unknown WhatsApp provider: {cls._current_provider}")
        
        # Add provider name for tracking
        cls._current_adapter.provider_name = cls._current_provider
        cls._current_adapter = _wrap_if_safe_send(cls._current_adapter)
        return cls._current_adapter
    
    @classmethod
    def _create_meta_adapter(cls) -> MetaAdapter:
        """Create Meta WhatsApp adapter"""
        api_token = os.getenv("WHATSAPP_API_TOKEN")
        phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        
        if not api_token or not phone_number_id:
            raise ValueError("Meta WhatsApp credentials not found in environment variables")
        
        return MetaAdapter(api_token, phone_number_id)
    
    @classmethod
    def _create_360dialog_adapter(cls) -> Dialog360Adapter:
        """Create 360Dialog adapter"""
        api_token = os.getenv("DIALOG360_API_KEY", "rqwWBA_sandbox")  # Default to sandbox key from docs
        is_sandbox = os.getenv("DIALOG360_SANDBOX", "true").lower() == "true"
        
        return Dialog360Adapter(api_token, is_sandbox)
    
    @classmethod
    def _create_qiscus_adapter(cls) -> QiscusAdapter:
        """
        Create Qiscus adapter
        """
        # Get credentials from environment variables
        api_token = os.getenv("QISCUS_SDK_SECRET")
        app_code = os.getenv("QISCUS_APP_CODE")
        sender_email = os.getenv("QISCUS_SENDER_EMAIL")
        
        # Optional: Get additional configuration
        base_url = os.getenv("QISCUS_BASE_URL", "https://omnichannel.qiscus.com")
        
        if not api_token or not app_code or not sender_email:
            raise ValueError("Qiscus credentials not found in environment variables. Required: QISCUS_SDK_SECRET, QISCUS_APP_CODE, QISCUS_SENDER_EMAIL")
        
        # Create adapter with configuration
        kwargs = {}
        if base_url:
            kwargs['base_url'] = base_url
        
        return QiscusAdapter(api_token, app_code, sender_email, **kwargs)
    
    @classmethod
    def _create_montymobile_adapter(cls) -> MontyMobileAdapter:
        """
        Create MontyMobile adapter (New Qiscus endpoint)
        """
        # Get credentials from environment variables
        api_token = os.getenv("MONTYMOBILE_API_KEY")
        tenant_id = os.getenv("MONTYMOBILE_TENANT_ID")
        api_id = os.getenv("MONTYMOBILE_API_ID")
        source_number = os.getenv("MONTYMOBILE_SOURCE_NUMBER")
        
        # Optional: Get additional configuration
        base_url = os.getenv("MONTYMOBILE_BASE_URL", "https://omni-apis.montymobile.com")
        
        if not api_token or not tenant_id or not api_id or not source_number:
            raise ValueError(
                "MontyMobile credentials not found in environment variables. "
                "Required: MONTYMOBILE_API_KEY, MONTYMOBILE_TENANT_ID, MONTYMOBILE_API_ID, MONTYMOBILE_SOURCE_NUMBER"
            )
        
        # Create adapter with configuration
        kwargs = {}
        if base_url:
            kwargs['base_url'] = base_url
        
        return MontyMobileAdapter(api_token, tenant_id, api_id, source_number, **kwargs)
    
    @classmethod
    def switch_provider(cls, provider: str) -> WhatsAppAdapter:
        """Switch to a different WhatsApp provider"""
        print(f"Switching WhatsApp provider from {cls._current_provider} to {provider}")
        
        # Close current adapter if exists
        if cls._current_adapter:
            # Note: We'll handle cleanup in the background
            pass
        
        cls._current_provider = provider
        cls._current_adapter = None  # Force recreation
        return cls.get_adapter()
    
    @classmethod
    def get_current_provider(cls) -> str:
        """Get current WhatsApp provider name"""
        return cls._current_provider
    
    @classmethod
    async def close_current_adapter(cls):
        """Close current adapter connection"""
        if cls._current_adapter:
            await cls._current_adapter.close()
            cls._current_adapter = None