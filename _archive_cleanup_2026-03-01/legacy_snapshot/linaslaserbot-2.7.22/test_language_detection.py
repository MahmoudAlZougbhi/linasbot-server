#!/usr/bin/env python3
"""
Comprehensive test script for the Language Detection System.

Tests the LanguageResolver and LanguageDetectionService to ensure
correct language detection across all supported scenarios.

Run with: python test_language_detection.py
"""

import sys
from typing import List, Tuple
from dataclasses import dataclass

# Import the language resolver
from language_resolver import (
    LanguageResolver,
    system_language_instruction,
    clean,
    alpha_len,
    tokenize,
    mask_times,
    looks_like_full_name,
    arabizi_score,
    is_arabizi,
    french_features,
    english_features,
    ARABIC_RE,
)

# Try to import the service (may fail if dependencies aren't available)
try:
    from services.language_detection_service import language_detection_service
    SERVICE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import language_detection_service: {e}")
    SERVICE_AVAILABLE = False


@dataclass
class TestCase:
    """A single test case for language detection."""
    message: str
    expected_language: str
    description: str
    category: str


class LanguageDetectionTester:
    """Comprehensive tester for the language detection system."""

    def __init__(self):
        self.resolver = LanguageResolver()
        self.passed = 0
        self.failed = 0
        self.results: List[Tuple[TestCase, str, bool]] = []

    def test_case(self, test: TestCase, conversation_id: str = "test_conv") -> bool:
        """Run a single test case and return whether it passed."""
        detected = self.resolver.resolve(
            conversation_id=conversation_id,
            user_text=test.message,
        )
        passed = detected == test.expected_language
        self.results.append((test, detected, passed))
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        return passed

    def print_result(self, test: TestCase, detected: str, passed: bool):
        """Print a single test result."""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test.description}")
        if not passed:
            print(f"       Message: '{test.message[:50]}{'...' if len(test.message) > 50 else ''}'")
            print(f"       Expected: {test.expected_language}, Got: {detected}")

    def run_category(self, category: str, tests: List[TestCase]):
        """Run all tests in a category."""
        print(f"\n{'='*60}")
        print(f"📋 {category}")
        print(f"{'='*60}")

        # Reset resolver state for each category
        self.resolver = LanguageResolver()

        for test in tests:
            passed = self.test_case(test, conversation_id=f"{category}_{id(test)}")
            self.print_result(test, self.results[-1][1], passed)

    def print_summary(self):
        """Print the overall test summary."""
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"📊 TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Total: {total} | Passed: {self.passed} | Failed: {self.failed}")
        print(f"Success Rate: {(self.passed/total)*100:.1f}%")

        if self.failed > 0:
            print(f"\n❌ Failed Tests:")
            for test, detected, passed in self.results:
                if not passed:
                    print(f"  - [{test.category}] {test.description}")
                    print(f"    Message: '{test.message[:60]}...' if len > 60 else '{test.message}'")
                    print(f"    Expected: {test.expected_language}, Got: {detected}")


def get_arabic_tests() -> List[TestCase]:
    """Tests for Arabic script detection."""
    return [
        TestCase("مرحبا", "ar", "Simple Arabic greeting", "Arabic"),
        TestCase("مرحبا، شو الخدمات؟", "ar", "Arabic question about services", "Arabic"),
        TestCase("كيفك؟", "ar", "Arabic 'how are you'", "Arabic"),
        TestCase("أهلاً وسهلاً", "ar", "Arabic welcome", "Arabic"),
        TestCase("بدي موعد", "ar", "Arabic 'I want appointment'", "Arabic"),
        TestCase("شو سعر الليزر؟", "ar", "Arabic price question", "Arabic"),
        TestCase("الليزر للرجال", "ar", "Arabic service for men", "Arabic"),
        TestCase("شكراً كتير", "ar", "Arabic thank you", "Arabic"),
        TestCase("بكرا الساعة 3", "ar", "Arabic tomorrow at 3", "Arabic"),
        TestCase("مساء الخير", "ar", "Arabic good evening", "Arabic"),
        TestCase("أنا شب", "ar", "Arabic 'I am male'", "Arabic"),
        TestCase("أنا صبية", "ar", "Arabic 'I am female'", "Arabic"),
    ]


def get_franco_arabic_tests() -> List[TestCase]:
    """Tests for Franco-Arabic/Arabizi detection."""
    return [
        TestCase("kifak", "franco", "Franco greeting 'kifak'", "Franco-Arabic"),
        TestCase("shu akhbarak", "franco", "Franco 'what's up'", "Franco-Arabic"),
        TestCase("ana bade maw3ad", "franco", "Franco 'I want appointment'", "Franco-Arabic"),
        TestCase("kifak, bade booking", "franco", "Franco mixed with English", "Franco-Arabic"),
        TestCase("se3er el laser", "franco", "Franco with digit (3=ع)", "Franco-Arabic"),
        TestCase("7abibi", "franco", "Franco with digit (7=ح)", "Franco-Arabic"),
        TestCase("ma3 el saleme", "franco", "Franco goodbye", "Franco-Arabic"),
        TestCase("shukran ktir", "franco", "Franco thank you", "Franco-Arabic"),
        TestCase("ana shab", "franco", "Franco 'I am male'", "Franco-Arabic"),
        TestCase("ana sabieh", "franco", "Franco 'I am female'", "Franco-Arabic"),
        TestCase("shou el as3ar", "franco", "Franco 'what are the prices'", "Franco-Arabic"),
        TestCase("bukra el sa3a 5", "franco", "Franco 'tomorrow at 5'", "Franco-Arabic"),
        TestCase("wein el clinic", "franco", "Franco 'where is clinic'", "Franco-Arabic"),
        TestCase("yalla book it", "franco", "Franco + English", "Franco-Arabic"),
        TestCase("la2 mesh hek", "franco", "Franco 'no not like that'", "Franco-Arabic"),
        TestCase("3am fakir fi", "franco", "Franco 'I'm thinking about it'", "Franco-Arabic"),
    ]


def get_english_tests() -> List[TestCase]:
    """Tests for English detection."""
    return [
        TestCase("Hello, what services do you offer?", "en", "English greeting + question", "English"),
        TestCase("I want to book an appointment", "en", "English booking request", "English"),
        TestCase("What is the price for laser?", "en", "English price question", "English"),
        TestCase("I'm male", "en", "English gender statement", "English"),
        TestCase("im female", "en", "English gender (informal)", "English"),
        TestCase("Thank you for your help", "en", "English gratitude", "English"),
        TestCase("Can I schedule for tomorrow?", "en", "English scheduling", "English"),
        TestCase("How much does hair removal cost?", "en", "English cost inquiry", "English"),
        TestCase("I would like information about your services", "en", "English info request", "English"),
        TestCase("What are your working hours?", "en", "English hours question", "English"),
        TestCase("Please confirm my appointment", "en", "English confirmation", "English"),
        TestCase("I need to reschedule", "en", "English reschedule", "English"),
    ]


def get_french_tests() -> List[TestCase]:
    """Tests for French detection."""
    return [
        TestCase("Bonjour, quels services offrez-vous?", "fr", "French greeting + question", "French"),
        TestCase("Je voudrais prendre rendez-vous", "fr", "French booking request", "French"),
        TestCase("Quel est le prix du laser?", "fr", "French price question", "French"),
        TestCase("Merci beaucoup", "fr", "French thank you", "French"),
        TestCase("Je suis un homme", "fr", "French 'I am a man'", "French"),
        TestCase("Je suis une femme", "fr", "French 'I am a woman'", "French"),
        TestCase("C'est combien?", "fr", "French 'how much'", "French"),
        TestCase("J'ai besoin d'informations", "fr", "French info request", "French"),
        TestCase("À quelle heure ouvrez-vous?", "fr", "French hours question", "French"),
        TestCase("S'il vous plaît confirmez", "fr", "French confirmation request", "French"),
        TestCase("Je voudrais annuler mon rendez-vous", "fr", "French cancel request", "French"),
        TestCase("Pouvez-vous m'aider?", "fr", "French help request", "French"),
    ]


def get_time_expression_tests() -> List[TestCase]:
    """Tests to ensure time expressions don't trigger false Franco detection."""
    return [
        TestCase("I want appointment at 7", "en", "English with time '7'", "Time Expressions"),
        TestCase("Book me for 7pm", "en", "English with '7pm'", "Time Expressions"),
        TestCase("Schedule at 3:30", "en", "English with '3:30'", "Time Expressions"),
        TestCase("Tomorrow at 2pm please", "en", "English with '2pm'", "Time Expressions"),
        TestCase("I can come around 5", "en", "English with 'around 5'", "Time Expressions"),
        TestCase("Je veux un rendez-vous à 7h", "fr", "French with '7h'", "Time Expressions"),
        TestCase("Rendez-vous vers 15h30", "fr", "French with '15h30'", "Time Expressions"),
        TestCase("at 7 tomorrow morning", "en", "English time tomorrow", "Time Expressions"),
        TestCase("available from 9 to 5", "en", "English time range", "Time Expressions"),
    ]


def get_full_name_tests() -> List[TestCase]:
    """Tests for full name detection (should preserve previous language)."""
    # Note: These require the expecting_full_name flag or heuristic detection
    return [
        TestCase("Jean-Pierre Dubois", "en", "French-style name (preserves default)", "Full Names"),
        TestCase("Mohammed Al-Rashid", "en", "Arabic-style name in Latin", "Full Names"),
        TestCase("Sarah Johnson", "en", "English name", "Full Names"),
        TestCase("Marie-Claire Lefebvre", "en", "French hyphenated name", "Full Names"),
        TestCase("Ahmad Khalil", "en", "Arabic name in Latin", "Full Names"),
    ]


def get_mixed_language_tests() -> List[TestCase]:
    """Tests for mixed language inputs."""
    return [
        TestCase("Hello merci", "en", "English + French greeting (keep locked)", "Mixed"),
        TestCase("Bonjour thank you", "en", "French + English (keep locked)", "Mixed"),
        TestCase("I want laser please merci", "en", "Mostly English with French word", "Mixed"),
        TestCase("Je veux booking please", "fr", "Mostly French with English", "Mixed"),
    ]


def get_low_signal_tests() -> List[TestCase]:
    """Tests for low-signal inputs (should preserve previous language)."""
    return [
        TestCase("ok", "en", "Single word 'ok'", "Low Signal"),
        TestCase("yes", "en", "Single word 'yes'", "Low Signal"),
        TestCase("no", "en", "Single word 'no'", "Low Signal"),
        TestCase("oui", "en", "Single word 'oui' (keeps default)", "Low Signal"),
        TestCase("non", "en", "Single word 'non' (keeps default)", "Low Signal"),
        TestCase("neo", "en", "Machine name 'neo'", "Low Signal"),
        TestCase("manara", "en", "Location 'manara'", "Low Signal"),
        TestCase("beirut", "en", "Location 'beirut'", "Low Signal"),
    ]


def get_edge_case_tests() -> List[TestCase]:
    """Edge case and regression tests."""
    return [
        TestCase("", "en", "Empty string (keeps default)", "Edge Cases"),
        TestCase("   ", "en", "Whitespace only (keeps default)", "Edge Cases"),
        TestCase("123", "en", "Numbers only (keeps default)", "Edge Cases"),
        TestCase("😊", "en", "Emoji only (keeps default)", "Edge Cases"),
        TestCase("!!!", "en", "Punctuation only (keeps default)", "Edge Cases"),
        TestCase("https://example.com", "en", "URL (keeps default)", "Edge Cases"),
        TestCase("test@email.com", "en", "Email (keeps default)", "Edge Cases"),
    ]


def test_helper_functions():
    """Test helper functions independently."""
    print(f"\n{'='*60}")
    print("🔧 Testing Helper Functions")
    print(f"{'='*60}")

    # Test clean()
    assert clean("Hello  World") == "Hello World", "clean() should normalize spaces"
    assert clean("test@email.com text") == "  text", "clean() should remove emails"
    print("  ✅ clean() works correctly")

    # Test alpha_len()
    assert alpha_len("Hello123") == 5, "alpha_len() should count only letters"
    assert alpha_len("مرحبا") == 5, "alpha_len() should count Arabic letters"
    print("  ✅ alpha_len() works correctly")

    # Test tokenize()
    tokens = tokenize("Hello World 123")
    assert "hello" in tokens, "tokenize() should lowercase"
    assert "123" in tokens, "tokenize() should keep digits"
    print("  ✅ tokenize() works correctly")

    # Test mask_times()
    assert "<TIME>" in mask_times("at 7pm"), "mask_times() should mask '7pm'"
    assert "<TIME>" in mask_times("7:30"), "mask_times() should mask '7:30'"
    assert "<TIME>" in mask_times("15h30"), "mask_times() should mask '15h30'"
    print("  ✅ mask_times() works correctly")

    # Test looks_like_full_name()
    assert looks_like_full_name("John Smith") == True, "Should detect full name"
    assert looks_like_full_name("Jean-Pierre") == True, "Should detect hyphenated name"
    assert looks_like_full_name("hello world how are you") == False, "Should not match long text"
    assert looks_like_full_name("John123") == False, "Should not match name with digits"
    print("  ✅ looks_like_full_name() works correctly")

    # Test arabizi_score()
    assert arabizi_score("kifak") > 0, "Should score kifak as Arabizi"
    assert arabizi_score("7abibi") > 0, "Should score 7abibi as Arabizi"
    assert arabizi_score("hello") == 0, "Should not score hello as Arabizi"
    print("  ✅ arabizi_score() works correctly")

    # Test ARABIC_RE
    assert ARABIC_RE.search("مرحبا") is not None, "Should detect Arabic script"
    assert ARABIC_RE.search("hello") is None, "Should not detect Arabic in English"
    print("  ✅ ARABIC_RE works correctly")

    # Test french_features()
    fr_score, fr_hits, fr_diac = french_features("Bonjour, comment ça va?")
    assert fr_score > 0, "Should score French text"
    assert fr_diac == True, "Should detect French diacritics"
    print("  ✅ french_features() works correctly")

    # Test english_features()
    en_score, en_hits = english_features("Hello, how are you?")
    assert en_score > 0, "Should score English text"
    print("  ✅ english_features() works correctly")

    # Test system_language_instruction()
    assert "Arabic" in system_language_instruction("ar"), "Should mention Arabic"
    assert "English" in system_language_instruction("en"), "Should mention English"
    assert "français" in system_language_instruction("fr"), "Should mention French"
    print("  ✅ system_language_instruction() works correctly")

    print("\n✅ All helper function tests passed!")


def test_conversation_persistence():
    """Test that language persists across messages in a conversation."""
    print(f"\n{'='*60}")
    print("🔄 Testing Conversation Persistence")
    print(f"{'='*60}")

    resolver = LanguageResolver()
    conv_id = "persistence_test"

    # Start with Arabic
    lang1 = resolver.resolve(conv_id, "مرحبا كيفك")
    assert lang1 == "ar", f"Should detect Arabic, got {lang1}"
    print(f"  ✅ Message 1 (Arabic): detected '{lang1}'")

    # Low-signal message should preserve Arabic
    lang2 = resolver.resolve(conv_id, "ok")
    assert lang2 == "ar", f"Low signal should keep Arabic, got {lang2}"
    print(f"  ✅ Message 2 (low signal): preserved '{lang2}'")

    # Switch to English with strong signal
    lang3 = resolver.resolve(conv_id, "Hello, I would like to book an appointment please")
    assert lang3 == "en", f"Should switch to English, got {lang3}"
    print(f"  ✅ Message 3 (English): switched to '{lang3}'")

    # Low-signal should now preserve English
    lang4 = resolver.resolve(conv_id, "yes")
    assert lang4 == "en", f"Low signal should keep English, got {lang4}"
    print(f"  ✅ Message 4 (low signal): preserved '{lang4}'")

    print("\n✅ Conversation persistence tests passed!")


def test_expecting_full_name_flag():
    """Test the expecting_full_name flag functionality."""
    print(f"\n{'='*60}")
    print("👤 Testing Expecting Full Name Flag")
    print(f"{'='*60}")

    resolver = LanguageResolver()
    conv_id = "name_test"

    # Set language to Arabic first
    lang1 = resolver.resolve(conv_id, "مرحبا")
    assert lang1 == "ar", f"Should detect Arabic, got {lang1}"
    print(f"  ✅ Initial language: '{lang1}'")

    # Set the expecting_full_name flag
    resolver.set_expecting_full_name(conv_id, True)
    print("  ✅ Set expecting_full_name flag to True")

    # Now a French-looking name should NOT change the language
    lang2 = resolver.resolve(conv_id, "Jean-Pierre Dubois")
    assert lang2 == "ar", f"Name should not change language, got {lang2}"
    print(f"  ✅ After name input: language preserved as '{lang2}'")

    # Flag should be auto-cleared, next message should be detected normally
    lang3 = resolver.resolve(conv_id, "Bonjour, je voudrais un rendez-vous")
    assert lang3 == "fr", f"Should now detect French, got {lang3}"
    print(f"  ✅ After flag cleared: switched to '{lang3}'")

    print("\n✅ Expecting full name flag tests passed!")


def test_service_integration():
    """Test the LanguageDetectionService wrapper."""
    if not SERVICE_AVAILABLE:
        print(f"\n{'='*60}")
        print("⚠️ Skipping Service Integration Tests (service not available)")
        print(f"{'='*60}")
        return

    print(f"\n{'='*60}")
    print("🔌 Testing Service Integration")
    print(f"{'='*60}")

    user_data = {'current_conversation_id': 'service_test_conv'}

    # Test English detection
    result = language_detection_service.detect_language(
        user_id="test_user_1",
        message="Hello, I want to book an appointment",
        user_data=user_data
    )
    assert result['detected_language'] == 'en', f"Should detect English, got {result}"
    assert result['response_language'] == 'en', f"Response should be English"
    print(f"  ✅ English: {result}")

    # Test Franco-Arabic detection
    result = language_detection_service.detect_language(
        user_id="test_user_2",
        message="kifak, bade maw3ad",
        user_data={'current_conversation_id': 'service_test_conv_2'}
    )
    assert result['detected_language'] == 'franco', f"Should detect Franco, got {result}"
    assert result['response_language'] == 'ar', f"Response should be Arabic for Franco"
    print(f"  ✅ Franco-Arabic: {result}")

    # Test Arabic detection
    result = language_detection_service.detect_language(
        user_id="test_user_3",
        message="مرحبا، بدي موعد",
        user_data={'current_conversation_id': 'service_test_conv_3'}
    )
    assert result['detected_language'] == 'ar', f"Should detect Arabic, got {result}"
    assert result['response_language'] == 'ar', f"Response should be Arabic"
    print(f"  ✅ Arabic: {result}")

    print("\n✅ Service integration tests passed!")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("🧪 LANGUAGE DETECTION COMPREHENSIVE TEST SUITE")
    print("="*60)

    tester = LanguageDetectionTester()

    # Run helper function tests
    test_helper_functions()

    # Run conversation persistence tests
    test_conversation_persistence()

    # Run expecting full name tests
    test_expecting_full_name_flag()

    # Run service integration tests
    test_service_integration()

    # Run all category tests
    tester.run_category("Arabic Script Detection", get_arabic_tests())
    tester.run_category("Franco-Arabic Detection", get_franco_arabic_tests())
    tester.run_category("English Detection", get_english_tests())
    tester.run_category("French Detection", get_french_tests())
    tester.run_category("Time Expression Handling", get_time_expression_tests())
    tester.run_category("Full Name Handling", get_full_name_tests())
    tester.run_category("Mixed Language Inputs", get_mixed_language_tests())
    tester.run_category("Low Signal Inputs", get_low_signal_tests())
    tester.run_category("Edge Cases", get_edge_case_tests())

    # Print summary
    tester.print_summary()

    # Return exit code
    return 0 if tester.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
