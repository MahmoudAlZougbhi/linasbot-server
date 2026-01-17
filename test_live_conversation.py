#!/usr/bin/env python3
"""
Test script for simulating a full live conversation with the bot
"""
import requests
import json
import time

BASE_URL = "http://localhost:8003"
TEST_PHONE = "+96178999888"  # Test phone number

def send_message(user_input, phone=TEST_PHONE):
    """Send a message to the bot and get response"""

    # MontyMobile webhook format (what the bot expects)
    payload = {
        "messageId": f"test_{int(time.time() * 1000)}",
        "timestamp": int(time.time() * 1000),
        "from": phone,
        "to": "96178974402",
        "text": {
            "body": user_input
        },
        "type": "text"
    }

    print(f"\n{'='*80}")
    print(f"📤 YOU: {user_input}")
    print(f"{'='*80}")

    try:
        response = requests.post(
            f"{BASE_URL}/webhook/whatsapp",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        print(f"📥 Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Response received")

            # The bot processes the message and sends response via WhatsApp API
            # We can check the response in the API logs or use the test endpoint

            # Get the last message for this user from chat history
            time.sleep(1)  # Wait for processing
            history_response = requests.get(f"{BASE_URL}/api/chat-history/conversation/{phone}")

            if history_response.status_code == 200:
                history = history_response.json()
                if 'messages' in history and history['messages']:
                    last_bot_message = None
                    for msg in reversed(history['messages']):
                        if msg.get('sender') == 'bot':
                            last_bot_message = msg
                            break

                    if last_bot_message:
                        bot_reply = last_bot_message.get('text', '')
                        print(f"\n🤖 BOT: {bot_reply}")
                    else:
                        print(f"\n⚠️ No bot response found in history yet")
                else:
                    print(f"\n⚠️ No conversation history found")
            else:
                print(f"\n❌ Could not fetch conversation history: {history_response.status_code}")
        else:
            print(f"❌ Error: {response.text}")

    except requests.exceptions.Timeout:
        print(f"⏱️ Request timed out (bot is processing)")
    except Exception as e:
        print(f"❌ Error: {e}")

    print(f"{'='*80}\n")


def test_full_conversation():
    """Test a complete conversation flow"""

    print(f"\n🚀 TESTING FULL LIVE CONVERSATION")
    print(f"📱 Test Phone: {TEST_PHONE}")
    print(f"🌐 Backend: {BASE_URL}")
    print(f"\n⏰ Starting conversation...\n")

    # Test 1: Initial message in Franco-Arabic (should ask for gender in Arabic)
    print("\n📝 Test 1: Franco-Arabic greeting")
    send_message("kifak, bade shil ltattoo")
    time.sleep(2)

    # Test 2: Respond with gender
    print("\n📝 Test 2: Provide gender")
    send_message("male")
    time.sleep(2)

    # Test 3: Ask a question about services
    print("\n📝 Test 3: Ask about laser types")
    send_message("shou anwa3 el laser 3andkon?")
    time.sleep(2)

    # Test 4: Ask about pricing
    print("\n📝 Test 4: Ask about pricing")
    send_message("addeh se3er el tattoo removal?")
    time.sleep(2)

    # Test 5: Request to talk to human
    print("\n📝 Test 5: Request human agent")
    send_message("bade 7ke ma3 7ada")
    time.sleep(2)

    print(f"\n✅ CONVERSATION TEST COMPLETE")
    print(f"\n💡 TIP: Check the dashboard at {BASE_URL.replace('8003', '3000')}/live-chat to see the live conversation")
    print(f"💡 TIP: Check the chat history at {BASE_URL.replace('8003', '3000')}/chat-history")


def test_english_conversation():
    """Test English language conversation"""

    print(f"\n🚀 TESTING ENGLISH CONVERSATION")
    print(f"📱 Test Phone: +96178888777 (different number for clean language lock)")
    print(f"\n⏰ Starting conversation...\n")

    # Use different phone for English test (language locking per conversation)
    english_phone = "+96178888777"

    # Test 1: English greeting
    print("\n📝 Test 1: English greeting")
    send_message("Hello, I want to remove my tattoo with laser", english_phone)
    time.sleep(2)

    # Test 2: Provide gender
    print("\n📝 Test 2: Provide gender")
    send_message("female", english_phone)
    time.sleep(2)

    # Test 3: Ask about process
    print("\n📝 Test 3: Ask about the process")
    send_message("How does the tattoo removal process work?", english_phone)
    time.sleep(2)

    print(f"\n✅ ENGLISH CONVERSATION TEST COMPLETE")


def test_french_conversation():
    """Test French language conversation"""

    print(f"\n🚀 TESTING FRENCH CONVERSATION")
    print(f"📱 Test Phone: +96178777666 (different number for clean language lock)")
    print(f"\n⏰ Starting conversation...\n")

    # Use different phone for French test
    french_phone = "+96178777666"

    # Test 1: French greeting
    print("\n📝 Test 1: French greeting")
    send_message("Bonjour, je veux enlever mon tatouage", french_phone)
    time.sleep(2)

    # Test 2: Provide gender
    print("\n📝 Test 2: Provide gender")
    send_message("homme", french_phone)
    time.sleep(2)

    print(f"\n✅ FRENCH CONVERSATION TEST COMPLETE")


if __name__ == "__main__":
    print(f"\n🤖 LINA'S LASER BOT - LIVE CONVERSATION TESTER")
    print(f"=" * 80)

    # Test full Franco-Arabic conversation
    test_full_conversation()

    # Uncomment to test other languages:
    # test_english_conversation()
    # test_french_conversation()

    print(f"\n\n🎯 ALL TESTS COMPLETE!")
    print(f"📊 Check the dashboard at http://localhost:3000 to see conversation details")
