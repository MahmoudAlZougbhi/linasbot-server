#!/usr/bin/env python3
"""
Script to fix archived conversations by changing their status to 'active'
"""
import sys
sys.path.insert(0, '/Users/jadkoby/Desktop/linaslaserbot-2.7.22')

from utils.utils import get_firestore_db
import config

def fix_archived_conversations():
    """Change all archived conversations back to active"""

    db = get_firestore_db()
    if not db:
        print("❌ ERROR: Firestore not initialized!")
        return

    print("\n" + "="*80)
    print("🔧 FIXING ARCHIVED CONVERSATIONS")
    print("="*80 + "\n")

    app_id = "linas-ai-bot-backend"
    users_collection = db.collection("artifacts").document(app_id).collection("users")

    users_docs = list(users_collection.stream())
    total_fixed = 0

    for user_doc in users_docs:
        user_id = user_doc.id

        conversations_collection = users_collection.document(user_id).collection(
            config.FIRESTORE_CONVERSATIONS_COLLECTION
        )
        conversations_docs = list(conversations_collection.stream())

        for conv_doc in conversations_docs:
            conv_data = conv_doc.to_dict()
            status = conv_data.get("status", "active")

            if status in ["archived", "resolved"]:
                print(f"🔄 Fixing conversation {conv_doc.id} for user {user_id}")
                print(f"   Current status: {status}")

                # Update to active
                conv_doc.reference.update({
                    "status": "active",
                    "fixed_at": "2026-01-15",
                    "fixed_reason": "Manually reactivated for testing"
                })

                print(f"   ✅ Changed to: active")
                total_fixed += 1

    print(f"\n{'='*80}")
    print(f"✅ Fixed {total_fixed} conversations")
    print(f"{'='*80}\n")

    if total_fixed > 0:
        print("Now refresh your Live Chat dashboard - conversations should appear!")
    else:
        print("No archived/resolved conversations found. Everything is already active.")

if __name__ == "__main__":
    try:
        fix_archived_conversations()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
