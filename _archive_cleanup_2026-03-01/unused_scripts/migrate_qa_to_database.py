#!/usr/bin/env python3
"""
Migration Script: Local Q&A File → Database API
Migrates Q&A pairs from data/qa_pairs.jsonl to backend database
"""

import asyncio
import json
from services.qa_database_service import qa_db_service

async def migrate_qa_pairs():
    """Migrate Q&A pairs from local file to database"""

    print("=" * 80)
    print("🔄 MIGRATING Q&A PAIRS: Local File → Database")
    print("=" * 80)

    # Read local file
    local_file = "data/qa_pairs.jsonl"

    try:
        with open(local_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        print(f"\n📁 Found {len(lines)} Q&A pairs in local file")

        # Track statistics
        success_count = 0
        skip_count = 0
        error_count = 0

        # Process each Q&A pair
        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue

            try:
                qa = json.loads(line)
                question = qa.get("question", "")
                answer = qa.get("answer", "")
                language = qa.get("language", "ar")
                category = qa.get("category", "general")

                if not question or not answer:
                    print(f"⚠️  Q&A {i}: Skipping - missing question or answer")
                    skip_count += 1
                    continue

                print(f"\n📝 Q&A {i}/{len(lines)}: {language.upper()}")
                print(f"   Q: {question[:60]}...")
                print(f"   A: {answer[:60]}...")

                # Create in database based on language
                if language == "ar":
                    result = await qa_db_service.create_qa_pair(
                        question_ar=question,
                        answer_ar=answer,
                        category=category
                    )
                elif language == "en":
                    result = await qa_db_service.create_qa_pair(
                        question_ar="",  # Empty for non-Arabic
                        answer_ar="",
                        question_en=question,
                        answer_en=answer,
                        category=category
                    )
                elif language == "fr":
                    result = await qa_db_service.create_qa_pair(
                        question_ar="",
                        answer_ar="",
                        question_fr=question,
                        answer_fr=answer,
                        category=category
                    )
                elif language == "franco":
                    result = await qa_db_service.create_qa_pair(
                        question_ar="",
                        answer_ar="",
                        question_franco=question,
                        answer_franco=answer,
                        category=category
                    )
                else:
                    print(f"⚠️  Unknown language: {language}")
                    skip_count += 1
                    continue

                if result.get("success"):
                    print(f"   ✅ Created in database (ID: {result.get('data', {}).get('qa_id')})")
                    success_count += 1
                else:
                    print(f"   ❌ Failed: {result.get('message')}")
                    error_count += 1

            except json.JSONDecodeError as e:
                print(f"❌ Q&A {i}: JSON parse error - {e}")
                error_count += 1
            except Exception as e:
                print(f"❌ Q&A {i}: Error - {e}")
                error_count += 1

        # Final statistics
        print("\n" + "=" * 80)
        print("📊 MIGRATION COMPLETE")
        print("=" * 80)
        print(f"✅ Successfully migrated: {success_count}")
        print(f"⚠️  Skipped: {skip_count}")
        print(f"❌ Errors: {error_count}")
        print(f"📝 Total processed: {len(lines)}")
        print("=" * 80)

        if success_count > 0:
            print(f"\n🎉 Migration successful! {success_count} Q&As now in database.")
            print(f"💡 Tip: You can now delete or backup {local_file}")

    except FileNotFoundError:
        print(f"❌ Error: File not found - {local_file}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("\n🚀 Starting Q&A migration...")
    print("⚠️  Make sure your backend database API is running!\n")

    asyncio.run(migrate_qa_pairs())
