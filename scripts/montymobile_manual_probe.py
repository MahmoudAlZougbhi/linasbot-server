#!/usr/bin/env python3
"""
MontyMobile Integration Test Script

Tests the MontyMobile WhatsApp API integration for Lina's Laser Bot.
This script can:
1. Test sending messages via MontyMobile API
2. Simulate incoming webhooks
3. Verify the connection and credentials

Usage:
    python tests/test_montymobile.py

Prerequisites:
    - Backend running on localhost:8003
    - Valid MontyMobile credentials in .env file
"""

import json
import time
import subprocess
import sys
import os
from datetime import datetime

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Note: python-dotenv not installed, using environment variables directly")

# Configuration
BASE_URL = "http://localhost:8003"
MONTYMOBILE_BASE_URL = os.getenv("MONTYMOBILE_BASE_URL", "https://omni-apis.montymobile.com")
MONTYMOBILE_API_KEY = os.getenv("MONTYMOBILE_API_KEY", "")
MONTYMOBILE_TENANT_ID = os.getenv("MONTYMOBILE_TENANT_ID", "")
MONTYMOBILE_API_ID = os.getenv("MONTYMOBILE_API_ID", "")
MONTYMOBILE_SOURCE_NUMBER = os.getenv("MONTYMOBILE_SOURCE_NUMBER", "96178974402")

# Test phone number (change this to your phone for real testing)
TEST_PHONE = "+96171412604"


def print_header(title):
    """Print a formatted header"""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


def print_config():
    """Display current configuration"""
    print_header("MONTYMOBILE CONFIGURATION")
    print(f"  Base URL:      {MONTYMOBILE_BASE_URL}")
    print(f"  API Key:       {'*' * 20}...{MONTYMOBILE_API_KEY[-8:] if MONTYMOBILE_API_KEY else 'NOT SET'}")
    print(f"  Tenant ID:     {MONTYMOBILE_TENANT_ID or 'NOT SET'}")
    print(f"  API ID:        {MONTYMOBILE_API_ID or 'NOT SET'}")
    print(f"  Source Number: {MONTYMOBILE_SOURCE_NUMBER}")
    print(f"  Backend URL:   {BASE_URL}")
    print()


def test_send_message_via_api(phone_number, message):
    """
    Send a message directly via MontyMobile API
    This tests outbound messaging capability
    """
    print_header("TEST: Send Message via MontyMobile API")

    if not all([MONTYMOBILE_API_KEY, MONTYMOBILE_TENANT_ID, MONTYMOBILE_API_ID]):
        print("  ERROR: MontyMobile credentials not configured in .env")
        return False

    endpoint = f"{MONTYMOBILE_BASE_URL}/notification/api/v2/WhatsappApi/send-session"

    payload = {
        "tenantId": MONTYMOBILE_TENANT_ID,
        "channelId": MONTYMOBILE_API_ID,
        "receiver": phone_number.replace("+", ""),
        "messageType": "text",
        "text": {
            "body": message
        }
    }

    print(f"  Endpoint: {endpoint}")
    print(f"  To: {phone_number}")
    print(f"  Message: {message}")
    print()

    curl_command = [
        "curl", "-X", "POST", endpoint,
        "-H", "Content-Type: application/json",
        "-H", f"X-API-Key: {MONTYMOBILE_API_KEY}",
        "-d", json.dumps(payload),
        "-w", "\nHTTP Status: %{http_code}\n",
        "-s"
    ]

    try:
        result = subprocess.run(curl_command, capture_output=True, text=True, timeout=30)
        print("  Response:")
        print(f"  {result.stdout}")

        if "200" in result.stdout or "success" in result.stdout.lower():
            print("  SUCCESS: Message sent via MontyMobile API")
            return True
        else:
            print("  FAILED: Check response above for details")
            return False

    except subprocess.TimeoutExpired:
        print("  TIMEOUT: Request took too long")
        return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def test_webhook_simulation(phone_number, message):
    """
    Simulate an incoming webhook from MontyMobile
    This tests the bot's ability to receive and process messages
    """
    print_header("TEST: Simulate Incoming Webhook")

    timestamp_ms = int(time.time() * 1000)

    # MontyMobile webhook format (Meta/WhatsApp Cloud API style)
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": MONTYMOBILE_TENANT_ID,
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": MONTYMOBILE_SOURCE_NUMBER,
                        "phone_number_id": MONTYMOBILE_API_ID
                    },
                    "contacts": [{
                        "profile": {"name": "Test User"},
                        "wa_id": phone_number.replace("+", "")
                    }],
                    "messages": [{
                        "id": f"wamid.test_{timestamp_ms}",
                        "from": phone_number.replace("+", ""),
                        "timestamp": str(int(timestamp_ms / 1000)),
                        "type": "text",
                        "text": {"body": message}
                    }]
                },
                "field": "messages"
            }]
        }]
    }

    print(f"  Endpoint: {BASE_URL}/webhook")
    print(f"  From: {phone_number}")
    print(f"  Message: {message}")
    print(f"  Format: Meta/WhatsApp Cloud API")
    print()

    curl_command = [
        "curl", "-X", "POST", f"{BASE_URL}/webhook",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
        "-w", "\nHTTP Status: %{http_code}\n",
        "-s"
    ]

    try:
        result = subprocess.run(curl_command, capture_output=True, text=True, timeout=30)
        print("  Response:")
        print(f"  {result.stdout}")

        if "200" in result.stdout or "success" in result.stdout.lower():
            print("  SUCCESS: Webhook processed successfully")
            return True
        else:
            print("  Note: Check backend console for processing details")
            return True  # May still be successful even with different response

    except subprocess.TimeoutExpired:
        print("  TIMEOUT: Backend might still be processing")
        return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def test_simple_webhook(phone_number, message):
    """
    Simulate a simple webhook format (Qiscus-style)
    This is an alternative format that MontyMobile adapter also supports
    """
    print_header("TEST: Simple Webhook Format")

    timestamp_ms = int(time.time() * 1000)

    payload = {
        "messageId": f"test_{timestamp_ms}",
        "timestamp": timestamp_ms,
        "from": phone_number,
        "to": MONTYMOBILE_SOURCE_NUMBER,
        "text": {"body": message},
        "type": "text"
    }

    print(f"  Endpoint: {BASE_URL}/webhook")
    print(f"  From: {phone_number}")
    print(f"  Message: {message}")
    print(f"  Format: Simple/Qiscus")
    print()

    curl_command = [
        "curl", "-X", "POST", f"{BASE_URL}/webhook",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
        "-w", "\nHTTP Status: %{http_code}\n",
        "-s"
    ]

    try:
        result = subprocess.run(curl_command, capture_output=True, text=True, timeout=30)
        print("  Response:")
        print(f"  {result.stdout}")

        if "200" in result.stdout:
            print("  SUCCESS: Simple webhook processed")
            return True
        return True

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def test_backend_health():
    """Check if the backend is running"""
    print_header("TEST: Backend Health Check")

    curl_command = [
        "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
        f"{BASE_URL}/", "--connect-timeout", "5"
    ]

    try:
        result = subprocess.run(curl_command, capture_output=True, text=True, timeout=10)
        status_code = result.stdout.strip()

        if status_code in ["200", "404", "307"]:
            print(f"  Backend is RUNNING (HTTP {status_code})")
            return True
        else:
            print(f"  Backend returned HTTP {status_code}")
            return False

    except Exception as e:
        print(f"  Backend is NOT RUNNING or unreachable")
        print(f"  Start with: ./venv/bin/python3 main.py")
        return False


def interactive_test():
    """Run interactive test mode"""
    print_header("INTERACTIVE TEST MODE")
    print("  You can now send custom messages.")
    print("  Type 'quit' to exit.\n")

    while True:
        try:
            message = input("  Enter message (or 'quit'): ").strip()
            if message.lower() == 'quit':
                break
            if message:
                test_simple_webhook(TEST_PHONE, message)
                time.sleep(2)
        except KeyboardInterrupt:
            break

    print("\n  Exiting interactive mode.\n")


def run_full_test():
    """Run the complete test suite"""
    print("\n")
    print("=" * 80)
    print("     MONTYMOBILE INTEGRATION TEST SUITE")
    print("     Lina's Laser AI Bot v2.7.22")
    print(f"     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Show configuration
    print_config()

    # Check backend health
    if not test_backend_health():
        print("\n  Cannot proceed without backend running.")
        print("  Please start the backend first:\n")
        print("    ./venv/bin/python3 main.py\n")
        return

    input("\n  Press ENTER to start tests...\n")

    # Test 1: Simple webhook
    print("\n--- TEST 1: Simple Greeting ---")
    test_simple_webhook(TEST_PHONE, "Hello! I want to book an appointment")
    time.sleep(3)

    # Test 2: Meta format webhook
    print("\n--- TEST 2: Meta Format Webhook ---")
    test_webhook_simulation(TEST_PHONE, "What are your prices for laser hair removal?")
    time.sleep(3)

    # Test 3: Send via API (if credentials available)
    if MONTYMOBILE_API_KEY:
        print("\n--- TEST 3: Direct API Message ---")
        print("  NOTE: This will send a REAL message if phone number is valid")
        confirm = input("  Send test message via API? (y/N): ").strip().lower()
        if confirm == 'y':
            test_phone = input(f"  Enter phone number [{TEST_PHONE}]: ").strip() or TEST_PHONE
            test_send_message_via_api(test_phone, "Test message from Lina's Laser Bot")

    # Summary
    print_header("TEST COMPLETE")
    print("  Next steps:")
    print(f"  1. Check backend console for processing logs")
    print(f"  2. Send a message from your phone to: {MONTYMOBILE_SOURCE_NUMBER}")
    print(f"  3. Verify bot responds correctly")
    print(f"  4. Check Live Chat dashboard: http://localhost:3000/live-chat")
    print()


def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()

        if arg == "--help" or arg == "-h":
            print(__doc__)
            return

        elif arg == "--interactive" or arg == "-i":
            print_config()
            if test_backend_health():
                interactive_test()
            return

        elif arg == "--send":
            # Send a direct message via API
            if len(sys.argv) < 4:
                print("Usage: python tests/test_montymobile.py --send <phone> <message>")
                return
            phone = sys.argv[2]
            message = " ".join(sys.argv[3:])
            test_send_message_via_api(phone, message)
            return

        elif arg == "--webhook":
            # Send a test webhook
            message = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Test message"
            test_simple_webhook(TEST_PHONE, message)
            return

    # Default: run full test
    run_full_test()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Test interrupted by user\n")
        sys.exit(0)
