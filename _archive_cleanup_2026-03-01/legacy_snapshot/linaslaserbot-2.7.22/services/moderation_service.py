"""
Content Moderation Service for OpenAI Compliance
This module implements content moderation to prevent policy violations
"""

import os
from openai import AsyncOpenAI
import config
from typing import Tuple, Dict, List
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict

# Initialize OpenAI client
client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

# Rate limiting configuration
RATE_LIMITS = {
    'messages_per_minute': 20,
    'messages_per_hour': 100,
    'messages_per_day': 500,
    'images_per_hour': 5,
    'voice_per_hour': 10
}

# User rate tracking
user_rate_tracker = defaultdict(lambda: {
    'messages': [],
    'images': [],
    'voice': [],
    'last_reset': datetime.now()
})

def is_laser_service_context(text: str) -> bool:
    """
    Check if the message is clearly about laser services (body parts for treatment).
    This helps prevent false positives from moderation API.
    """
    import re
    text_lower = text.lower()

    # Body parts commonly treated with laser (in multiple languages)
    body_parts = [
        # English
        'arms', 'legs', 'face', 'back', 'chest', 'bikini', 'underarms', 'full body',
        'upper lip', 'chin', 'neck', 'shoulders', 'stomach', 'hands', 'feet', 'fingers',
        # Arabic
        'ايدين', 'رجلين', 'وجه', 'ظهر', 'صدر', 'بكيني', 'ابط', 'جسم كامل',
        'شفة', 'ذقن', 'رقبة', 'اكتاف', 'بطن', 'ايادي', 'قدمين',
        # Franco-Arabic
        'eedayn', 'rejlayn', 'wej', 'daher', 'sader', 'ebt',
    ]

    # Service-related keywords
    service_keywords = [
        'laser', 'hair removal', 'treatment', 'session', 'appointment', 'book', 'price',
        'ليزر', 'ازالة', 'شعر', 'جلسة', 'موعد', 'حجز', 'سعر',
        'do', 'want', 'need', 'بدي', 'بدها', 'عايز', 'عايزة',
    ]

    has_body_part = any(part in text_lower for part in body_parts)
    has_service_keyword = any(kw in text_lower for kw in service_keywords)

    # If message contains body part + service context, it's likely about laser services
    if has_body_part and has_service_keyword:
        return True

    # Also check for common patterns like "I want to do [body part]"
    do_patterns = [
        r'\b(?:do|want|need|book|get)\s+(?:my\s+)?(?:arms|legs|face|back|chest|bikini|underarms|full body)\b',
        r'\b(?:بدي|عايز|عايزة)\s+(?:اعمل|اعملي)?\s*(?:ايدين|رجلين|وجه|ظهر|صدر|بكيني|ابط)\b',
    ]
    for pattern in do_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True

    return False


async def moderate_content(text: str, user_id: str = None) -> Tuple[bool, Dict]:
    """
    Check content for policy violations using OpenAI's Moderation API

    Args:
        text: The text content to moderate
        user_id: Optional user ID for tracking

    Returns:
        Tuple of (is_safe, moderation_results)
    """
    try:
        # Call OpenAI's moderation endpoint
        response = await client.moderations.create(
            input=text
        )

        if not response.results:
            return True, {'flagged': False, 'message': 'No moderation result'}
        result = response.results[0]

        # Check if content is flagged
        if result.flagged:
            flagged_categories = [cat for cat, flagged in result.categories.model_dump().items() if flagged]
            category_scores = result.category_scores.model_dump()

            # CHECK FOR FALSE POSITIVES: Laser service context
            # If flagged for self-harm but message is clearly about laser services, allow it
            is_self_harm_flag = any('self_harm' in cat or 'self-harm' in cat for cat in flagged_categories)
            is_service_context = is_laser_service_context(text)

            if is_self_harm_flag and is_service_context:
                print(f"✅ MODERATION: False positive detected for user {user_id} - laser service context")
                print(f"   Message: '{text[:100]}...' flagged as {flagged_categories} but is service-related")
                return True, {
                    'flagged': False,
                    'false_positive': True,
                    'original_categories': flagged_categories,
                    'category_scores': category_scores,
                    'message': 'Content allowed - laser service context detected'
                }

            # Also check if scores are relatively low (< 0.5) for self-harm - likely false positive
            self_harm_score = max(
                category_scores.get('self_harm', 0),
                category_scores.get('self-harm', 0),
                category_scores.get('self_harm_intent', 0),
                category_scores.get('self-harm/intent', 0)
            )
            if is_self_harm_flag and self_harm_score < 0.5:
                print(f"✅ MODERATION: Low confidence self-harm flag ({self_harm_score:.2f}) for user {user_id} - allowing")
                return True, {
                    'flagged': False,
                    'low_confidence': True,
                    'original_categories': flagged_categories,
                    'category_scores': category_scores,
                    'message': 'Content allowed - low confidence flag'
                }

            print(f"⚠️ MODERATION WARNING: Content flagged for user {user_id}")
            print(f"Categories: {flagged_categories}")

            # Log the violation
            log_violation(user_id, text, result.categories.model_dump())

            return False, {
                'flagged': True,
                'categories': result.categories.model_dump(),
                'category_scores': category_scores,
                'message': 'Content violates OpenAI usage policies'
            }

        return True, {
            'flagged': False,
            'categories': result.categories.model_dump(),
            'category_scores': result.category_scores.model_dump()
        }
        
    except Exception as e:
        print(f"❌ ERROR in content moderation: {e}")
        # Check if it's a rate limit error (429)
        error_str = str(e)
        if '429' in error_str or 'Too Many Requests' in error_str:
            print(f"⚠️ OpenAI moderation API rate limit hit - allowing content through")
            # Allow content through when moderation API is rate limited
            return True, {
                'flagged': False,
                'error': str(e),
                'message': 'Moderation API rate limited - content allowed'
            }
        
        # For other errors, be conservative and flag as potentially unsafe
        return False, {
            'flagged': True,
            'error': str(e),
            'message': 'Could not verify content safety'
        }

async def check_rate_limits(user_id: str, message_type: str = 'message') -> Tuple[bool, str]:
    """
    Check if user has exceeded rate limits
    
    Args:
        user_id: User identifier
        message_type: Type of message ('message', 'image', 'voice')
        
    Returns:
        Tuple of (is_within_limits, error_message)
    """
    now = datetime.now()
    tracker = user_rate_tracker[user_id]
    
    # Clean old entries (older than 24 hours)
    cutoff_time = now - timedelta(days=1)
    for msg_type in ['messages', 'images', 'voice']:
        tracker[msg_type] = [t for t in tracker[msg_type] if t > cutoff_time]
    
    # Add current request
    if message_type == 'message':
        tracker['messages'].append(now)
        
        # Check limits
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)
        
        messages_last_minute = sum(1 for t in tracker['messages'] if t > minute_ago)
        messages_last_hour = sum(1 for t in tracker['messages'] if t > hour_ago)
        messages_last_day = len(tracker['messages'])
        
        if messages_last_minute > RATE_LIMITS['messages_per_minute']:
            return False, f"Rate limit exceeded: Too many messages per minute (limit: {RATE_LIMITS['messages_per_minute']})"
        
        if messages_last_hour > RATE_LIMITS['messages_per_hour']:
            return False, f"Rate limit exceeded: Too many messages per hour (limit: {RATE_LIMITS['messages_per_hour']})"
        
        if messages_last_day > RATE_LIMITS['messages_per_day']:
            return False, f"Rate limit exceeded: Too many messages per day (limit: {RATE_LIMITS['messages_per_day']})"
    
    elif message_type == 'image':
        tracker['images'].append(now)
        hour_ago = now - timedelta(hours=1)
        images_last_hour = sum(1 for t in tracker['images'] if t > hour_ago)
        
        if images_last_hour > RATE_LIMITS['images_per_hour']:
            return False, f"Rate limit exceeded: Too many images per hour (limit: {RATE_LIMITS['images_per_hour']})"
    
    elif message_type == 'voice':
        tracker['voice'].append(now)
        hour_ago = now - timedelta(hours=1)
        voice_last_hour = sum(1 for t in tracker['voice'] if t > hour_ago)
        
        if voice_last_hour > RATE_LIMITS['voice_per_hour']:
            return False, f"Rate limit exceeded: Too many voice messages per hour (limit: {RATE_LIMITS['voice_per_hour']})"
    
    return True, ""

def log_violation(user_id: str, content: str, categories: Dict):
    """
    Log content policy violations for review
    """
    try:
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'content': content[:500],  # Truncate for safety
            'flagged_categories': [cat for cat, flagged in categories.items() if flagged]
        }
        
        # Write to violations log
        log_file = os.path.join(os.getcwd(), 'logs', 'content_violations.jsonl')
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        import json
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        
        print(f"📝 Violation logged for user {user_id}")
        
    except Exception as e:
        print(f"❌ ERROR logging violation: {e}")

def get_safe_response_for_violation(language: str = 'ar') -> str:
    """
    Get a safe response message when content is flagged
    """
    safe_responses = {
        'ar': "عذراً، لا أستطيع معالجة هذا الطلب. يرجى التواصل مع فريق الدعم إذا كنت بحاجة للمساعدة.",
        'en': "Sorry, I cannot process this request. Please contact our support team if you need assistance.",
        'fr': "Désolé, je ne peux pas traiter cette demande. Veuillez contacter notre équipe d'assistance si vous avez besoin d'aide.",
        'franco': "Sorry, ma fini e2dar sa3dak bi hal talab. Please contact el support team."
    }
    
    return safe_responses.get(language, safe_responses['ar'])

def get_rate_limit_response(language: str = 'ar', limit_message: str = "") -> str:
    """
    Get a response message for rate limit violations
    """
    rate_limit_responses = {
        'ar': f"عذراً، لقد تجاوزت الحد المسموح به من الرسائل. يرجى المحاولة مرة أخرى لاحقاً. {limit_message}",
        'en': f"Sorry, you have exceeded the message limit. Please try again later. {limit_message}",
        'fr': f"Désolé, vous avez dépassé la limite de messages. Veuillez réessayer plus tard. {limit_message}",
        'franco': f"Sorry, wsolت lal limit. Try again ba3den. {limit_message}"
    }
    
    return rate_limit_responses.get(language, rate_limit_responses['ar'])

async def moderate_image_prompt(prompt: str, user_id: str = None) -> Tuple[bool, Dict]:
    """
    Moderate prompts used for image analysis
    """
    return await moderate_content(prompt, user_id)

async def get_moderation_stats() -> Dict:
    """
    Get moderation statistics for monitoring
    """
    try:
        log_file = os.path.join(os.getcwd(), 'logs', 'content_violations.jsonl')
        
        if not os.path.exists(log_file):
            return {
                'total_violations': 0,
                'violations_today': 0,
                'top_categories': []
            }
        
        import json
        violations = []
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    violations.append(json.loads(line))
                except:
                    continue
        
        today = datetime.now().date()
        violations_today = [v for v in violations if datetime.fromisoformat(v['timestamp']).date() == today]
        
        # Count category frequencies
        category_counts = defaultdict(int)
        for v in violations:
            for cat in v.get('flagged_categories', []):
                category_counts[cat] += 1
        
        top_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'total_violations': len(violations),
            'violations_today': len(violations_today),
            'top_categories': top_categories,
            'recent_violations': violations[-10:]  # Last 10 violations
        }
        
    except Exception as e:
        print(f"❌ ERROR getting moderation stats: {e}")
        return {
            'total_violations': 0,
            'violations_today': 0,
            'top_categories': [],
            'error': str(e)
        }

# Test function
async def test_moderation():
    """Test the moderation system"""
    test_cases = [
        "مرحبا، كيف يمكنني حجز موعد؟",  # Safe content
        "Hello, I need help with laser treatment",  # Safe content
    ]
    
    for text in test_cases:
        is_safe, result = await moderate_content(text, "test_user")
        print(f"Text: {text[:50]}...")
        print(f"Safe: {is_safe}")
        print(f"Result: {result}\n")

if __name__ == "__main__":
    # Run test
    asyncio.run(test_moderation())