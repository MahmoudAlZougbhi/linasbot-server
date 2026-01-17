#!/usr/bin/env python3
"""
Script to add the 11 missing Q&As to the database
"""

import asyncio
from services.qa_database_service import qa_db_service

# The 11 Q&As that failed to migrate
MISSING_QAS = [
    # English Q&As
    {
        "question_en": "What is the difference between laser and IPL hair removal?",
        "answer_en": "Laser hair removal is more precise and effective for dark hair, while IPL works better for lighter skin with darker hair.",
        "category": "services"
    },
    {
        "question_en": "What's the best tattoo removal method?",
        "answer_en": "We offer professional tattoo removal services using the latest laser technology for safe and effective results.",
        "category": "services"
    },
    {
        "question_en": "What are laser hair removal prices?",
        "answer_en": "Prices vary depending on the treatment area and package. Please contact us for a free consultation to get accurate pricing for your needs.",
        "category": "pricing"
    },
    {
        "question_en": "How do I book an appointment?",
        "answer_en": "You can book via WhatsApp or visit us directly. We welcome advance bookings.",
        "category": "appointments"
    },
    {
        "question_en": "What are your working hours?",
        "answer_en": "We're open from 10 AM to 6 PM daily except Sundays.",
        "category": "hours"
    },
    {
        "question_en": "Is laser hair removal painful?",
        "answer_en": "Modern laser technology is virtually painless. You may feel a slight warming sensation, but most clients find it very comfortable.",
        "category": "services"
    },
    {
        "question_en": "How many sessions do I need for hair removal?",
        "answer_en": "Usually you need 6-8 sessions depending on skin type. You'll see results after the first session.",
        "category": "services"
    },
    {
        "question_en": "How much does laser cost?",
        "answer_en": "Prices vary by area. We offer free consultation to determine exact cost.",
        "category": "pricing"
    },

    # French Q&A
    {
        "question_fr": "Quels sont les prix?",
        "answer_fr": "Les prix varient. Consultation gratuite.",
        "category": "pricing"
    },

    # Franco Q&As
    {
        "question_franco": "Shou el ekhnezaat eli fi el markaz?",
        "answer_franco": "3anna ezalet el sha3er bel laser w taksir el bashareh w 3elej kahraba2i.",
        "category": "services"
    },
    {
        "question_franco": "Shou el as3ar?",
        "answer_franco": "El as3ar btekhtalef 7asab el mante2a. Fina na3mel consultation mjaneneh.",
        "category": "pricing"
    }
]

async def add_missing_qas():
    """Add the 11 missing Q&As to database"""

    print("=" * 80)
    print("📝 ADDING 11 MISSING Q&As TO DATABASE")
    print("=" * 80)

    success_count = 0
    error_count = 0

    for i, qa in enumerate(MISSING_QAS, 1):
        # Determine which language field to use
        if "question_en" in qa:
            lang = "EN"
            question = qa["question_en"]
        elif "question_fr" in qa:
            lang = "FR"
            question = qa["question_fr"]
        elif "question_franco" in qa:
            lang = "FRANCO"
            question = qa["question_franco"]
        else:
            lang = "UNKNOWN"
            question = "Unknown"

        print(f"\n📝 Q&A {i}/11: [{lang}] {qa['category']}")
        print(f"   Q: {question[:60]}...")

        try:
            # Create Q&A pair in database
            result = await qa_db_service.create_qa_pair(
                question_ar="",  # Empty Arabic
                answer_ar="",
                question_en=qa.get("question_en", ""),
                answer_en=qa.get("answer_en", ""),
                question_fr=qa.get("question_fr", ""),
                answer_fr=qa.get("answer_fr", ""),
                question_franco=qa.get("question_franco", ""),
                answer_franco=qa.get("answer_franco", ""),
                category=qa["category"]
            )

            if result.get("success"):
                qa_id = result.get("data", {}).get("qa_id")
                print(f"   ✅ Created successfully (ID: {qa_id})")
                success_count += 1
            else:
                print(f"   ❌ Failed: {result.get('message', 'Unknown error')}")
                error_count += 1

        except Exception as e:
            print(f"   ❌ Error: {e}")
            error_count += 1

    # Final statistics
    print("\n" + "=" * 80)
    print("📊 RESULTS")
    print("=" * 80)
    print(f"✅ Successfully added: {success_count}")
    print(f"❌ Failed: {error_count}")
    print(f"📝 Total attempted: {len(MISSING_QAS)}")
    print("=" * 80)

    if success_count > 0:
        print(f"\n🎉 Success! {success_count} Q&As added to database.")
        print("💡 Restart your backend to use these Q&As immediately.")

    if error_count > 0:
        print(f"\n⚠️  {error_count} Q&As failed to add.")
        print("   This likely means your API token doesn't have CREATE permissions.")
        print("   Contact your backend developer to fix the /qa/create endpoint.")

if __name__ == "__main__":
    print("\n🚀 Starting to add missing Q&As...")
    print("⚠️  Make sure your backend database API is running!\n")

    asyncio.run(add_missing_qas())
