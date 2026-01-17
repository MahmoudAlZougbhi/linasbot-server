#!/usr/bin/env python3
"""
Simple test script for testing live chat - sends messages to the CORRECT webhook endpoint
"""
import json
import time
import subprocess
import sys

BASE_URL = "http://localhost:8003"
TEST_PHONE = "+96178999888"  # Test phone number

def send_test_message(message_text, phone=TEST_PHONE):
    """Send a test message using curl (no dependencies needed)"""

    timestamp_ms = int(time.time() * 1000)

    # MontyMobile/Qiscus webhook format
    payload = {
        "messageId": f"test_{timestamp_ms}",
        "timestamp": timestamp_ms,
        "from": phone,
        "to": "96178974402",
        "text": {
            "body": message_text
        },
        "type": "text"
    }

    print(f"\n{'='*80}")
    print(f"📤 Sending message: {message_text}")
    print(f"📱 From: {phone}")
    print(f"⏰ Timestamp: {timestamp_ms}")
    print(f"{'='*80}\n")

    # Use curl to send the request (no Python dependencies needed)
    curl_command = [
        "curl",
        "-X", "POST",
        f"{BASE_URL}/webhook",  # CORRECT ENDPOINT (not /webhook/whatsapp)
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
        "-w", "\\nHTTP Status: %{http_code}\\n",
        "-s"  # Silent mode (no progress bar)
    ]

    try:
        result = subprocess.run(curl_command, capture_output=True, text=True, timeout=30)

        print("📥 Response:")
        print(result.stdout)

        if result.stderr:
            print("⚠️ Errors:")
            print(result.stderr)

        if "200" in result.stdout or '"status":"success"' in result.stdout:
            print("✅ Message sent successfully!")
            return True
        else:
            print("❌ Message failed to send")
            return False

    except subprocess.TimeoutExpired:
        print("⏱️ Request timed out (backend might still be processing)")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Run test messages"""

    print("\n" + "="*80)
    print("🤖 LINA'S LASER BOT - LIVE CHAT TESTER")
    print("="*80)
    print(f"📍 Backend: {BASE_URL}")
    print(f"📱 Test Phone: {TEST_PHONE}")
    print("\n⚠️  Make sure the backend is running on port 8003!")
    print("   Start with: ./venv/bin/python3 main.py")
    print("="*80)

    # Wait for user confirmation
    input("\n Press ENTER to start sending test messages...")

    # Test 1: Simple greeting
    print("\n\n📝 Test 1: Simple greeting")
    send_test_message("Hello, I want information about laser hair removal")
    time.sleep(3)

    # Test 2: Follow-up question
    print("\n\n📝 Test 2: Follow-up question")
    send_test_message("What are your prices?")
    time.sleep(3)

    # Test 3: Request human agent
    print("\n\n📝 Test 3: Request human agent")
    send_test_message("I want to talk to a real person")
    time.sleep(2)

    print("\n\n" + "="*80)
    print("✅ TEST COMPLETE!")
    print("="*80)
    print(f"\n💡 Now check your Live Chat dashboard at:")
    print(f"   http://localhost:3000/live-chat")
    print(f"\n💡 Or check Chat History at:")
    print(f"   http://localhost:3000/chat-history")
    print("\n💡 If conversations don't appear:")
    print("   1. Check backend console for errors")
    print("   2. Run: ./venv/bin/python3 debug_firestore_chats.py")
    print("   3. Make sure backend is actually running on port 8003")
    print("="*80 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
        sys.exit(0)
