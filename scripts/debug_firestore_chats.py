#!/usr/bin/env python3
"""
Debug script to check Firestore conversations and why they're not appearing in Live Chat
"""
import datetime
import sys

# Add project root to path
sys.path.insert(0, '/Users/jadkoby/Desktop/linaslaserbot-2.7.22')

from utils.utils import get_firestore_db
import config

def check_conversations():
    """Check all conversations in Firestore and diagnose why they're not showing"""

    db = get_firestore_db()
    if not db:
        print("❌ ERROR: Firestore not initialized!")
        print("Check if data/firebase_data.json exists and is valid")
        return

    print("\n" + "="*80)
    print("🔍 FIRESTORE CONVERSATIONS DEBUG REPORT")
    print("="*80 + "\n")

    app_id = "linas-ai-bot-backend"
    users_collection = db.collection("artifacts").document(app_id).collection("users")

    users_docs = list(users_collection.stream())
    print(f"📊 Total users in Firestore: {len(users_docs)}\n")

    if len(users_docs) == 0:
        print("⚠️ NO USERS FOUND IN FIRESTORE!")
        print("This means:")
        print("  1. No messages have been saved yet, OR")
        print("  2. Phone number extraction is failing (messages not saved)")
        print("\nRun your curl test and check backend logs for errors.")
        return

    current_time = datetime.datetime.now()
    total_conversations = 0

    # Statistics
    stats = {
        "active": 0,
        "resolved": 0,
        "archived": 0,
        "within_6h": 0,
        "older_than_6h": 0,
        "no_messages": 0,
        "waiting_human": 0,
        "with_operator": 0,
        "bot_only": 0
    }

    for user_doc in users_docs:
        user_id = user_doc.id
        user_data = user_doc.to_dict()

        print(f"\n{'─'*80}")
        print(f"👤 USER: {user_id}")
        print(f"   Name: {user_data.get('name', 'Unknown')}")
        print(f"   Phone: {user_data.get('phone_full', 'Unknown')}")
        print(f"   Last Activity: {user_data.get('last_activity', 'Unknown')}")

        conversations_collection = users_collection.document(user_id).collection(
            config.FIRESTORE_CONVERSATIONS_COLLECTION
        )
        conversations_docs = list(conversations_collection.stream())

        print(f"   Total Conversations: {len(conversations_docs)}")
        total_conversations += len(conversations_docs)

        for conv_doc in conversations_docs:
            conv_data = conv_doc.to_dict()
            messages = conv_data.get("messages", [])

            print(f"\n   📝 Conversation ID: {conv_doc.id}")

            # Check messages
            if not messages:
                print(f"      ❌ NO MESSAGES (will be skipped)")
                stats["no_messages"] += 1
                continue

            print(f"      Messages: {len(messages)}")

            # Check status
            status = conv_data.get("status", "active")
            print(f"      Status: {status}", end="")
            if status == "active":
                print(" ✅")
                stats["active"] += 1
            elif status == "resolved":
                print(" ⚠️  (WILL NOT SHOW - marked resolved)")
                stats["resolved"] += 1
            elif status == "archived":
                print(" ⚠️  (WILL NOT SHOW - archived)")
                stats["archived"] += 1

            # Check last message time
            last_message = messages[-1]
            last_msg_time_raw = last_message.get("timestamp")

            # Parse timestamp
            if isinstance(last_msg_time_raw, str):
                try:
                    last_msg_time = datetime.datetime.fromisoformat(last_msg_time_raw.replace('Z', '+00:00'))
                except:
                    last_msg_time = current_time
            else:
                last_msg_time = current_time

            time_diff = (current_time - last_msg_time).total_seconds()
            hours_ago = time_diff / 3600

            print(f"      Last Activity: {hours_ago:.1f} hours ago", end="")
            if hours_ago <= 6:
                print(f" ✅ (within 6-hour window)")
                stats["within_6h"] += 1
            else:
                print(f" ⚠️  (WILL NOT SHOW - older than 6 hours)")
                stats["older_than_6h"] += 1

            # Check human takeover status
            human_takeover = conv_data.get("human_takeover_active", False)
            operator_id = conv_data.get("operator_id")

            if human_takeover:
                if operator_id:
                    print(f"      Human Takeover: YES, Operator: {operator_id} ✅")
                    stats["with_operator"] += 1
                else:
                    print(f"      Human Takeover: YES, NO OPERATOR ⚠️  (in waiting queue only)")
                    stats["waiting_human"] += 1
            else:
                print(f"      Human Takeover: NO (bot handling)")
                stats["bot_only"] += 1

            # Check if this conversation SHOULD appear
            should_appear = (
                len(messages) > 0 and
                status not in ["resolved", "archived"] and
                hours_ago <= 6 and
                not (human_takeover and operator_id is None)  # Not waiting for human
            )

            print(f"      VERDICT: ", end="")
            if should_appear:
                print("✅ SHOULD APPEAR IN LIVE CHAT")
            else:
                print("❌ WILL NOT APPEAR")
                if len(messages) == 0:
                    print(f"         Reason: No messages")
                if status in ["resolved", "archived"]:
                    print(f"         Reason: Status is '{status}'")
                if hours_ago > 6:
                    print(f"         Reason: Older than 6 hours ({hours_ago:.1f} hours)")
                if human_takeover and operator_id is None:
                    print(f"         Reason: Waiting in queue (will appear in waiting queue section)")

            # Show last few messages
            print(f"\n      Last 3 messages:")
            for msg in messages[-3:]:
                role = msg.get("role", "unknown")
                text = msg.get("text", "")[:60]
                timestamp = msg.get("timestamp", "unknown")
                print(f"        [{role}] {text}... ({timestamp})")

    # Print summary
    print(f"\n\n{'='*80}")
    print(f"📊 SUMMARY")
    print(f"{'='*80}")
    print(f"Total Users: {len(users_docs)}")
    print(f"Total Conversations: {total_conversations}")
    print(f"\nStatus Breakdown:")
    print(f"  Active: {stats['active']}")
    print(f"  Resolved: {stats['resolved']} ⚠️")
    print(f"  Archived: {stats['archived']} ⚠️")
    print(f"\nTime Window:")
    print(f"  Within 6 hours: {stats['within_6h']} ✅")
    print(f"  Older than 6 hours: {stats['older_than_6h']} ⚠️")
    print(f"\nHandling:")
    print(f"  Bot handling: {stats['bot_only']}")
    print(f"  With operator: {stats['with_operator']}")
    print(f"  Waiting for human: {stats['waiting_human']} (in waiting queue)")
    print(f"\nOther:")
    print(f"  No messages: {stats['no_messages']} ⚠️")

    print(f"\n\n{'='*80}")
    print(f"💡 RECOMMENDATIONS")
    print(f"{'='*80}")

    if stats['resolved'] > 0:
        print(f"\n1. You have {stats['resolved']} RESOLVED conversations")
        print(f"   These won't show in Live Chat (only in Chat History)")
        print(f"   To make them appear, change status to 'active'")

    if stats['archived'] > 0:
        print(f"\n2. You have {stats['archived']} ARCHIVED conversations")
        print(f"   These won't show anywhere")
        print(f"   To make them appear, change status to 'active'")

    if stats['older_than_6h'] > 0:
        print(f"\n3. You have {stats['older_than_6h']} conversations OLDER than 6 hours")
        print(f"   These are auto-filtered from Live Chat")
        print(f"   Send a NEW message to create a fresh conversation")
        print(f"   OR increase ACTIVE_TIME_WINDOW in services/live_chat_service.py")

    if stats['waiting_human'] > 0:
        print(f"\n4. You have {stats['waiting_human']} conversations WAITING FOR HUMAN")
        print(f"   These appear in the 'Waiting Queue' section, NOT active chats")
        print(f"   Assign an operator to move them to active chats")

    if total_conversations == 0:
        print(f"\n⚠️  NO CONVERSATIONS FOUND!")
        print(f"   Possible causes:")
        print(f"   1. Backend webhook isn't receiving messages")
        print(f"   2. Phone number extraction is failing")
        print(f"   3. save_conversation_message_to_firestore() is returning early")
        print(f"\n   Start the backend and check logs when sending test curl")

    print("\n" + "="*80)

if __name__ == "__main__":
    try:
        check_conversations()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        print("\nMake sure:")
        print("  1. data/firebase_data.json exists")
        print("  2. Firebase credentials are valid")
        print("  3. Firestore is properly initialized")
