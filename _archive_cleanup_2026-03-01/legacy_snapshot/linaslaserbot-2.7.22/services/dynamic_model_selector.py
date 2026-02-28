"""
Dynamic Model Selector Service
Analyzes question complexity and selects the most cost-effective AI model
"""

import re
from typing import Tuple, Dict, Any
from enum import Enum

class ModelTier(Enum):
    """AI Model tiers from cheapest to most expensive"""
    MINI = "gpt-4o-mini"           # $0.15 / 1M input, $0.60 / 1M output
    TURBO = "gpt-3.5-turbo"         # $0.50 / 1M input, $1.50 / 1M output  
    GPT4 = "gpt-4o"                 # $2.50 / 1M input, $10.00 / 1M output
    GPT4_ADVANCED = "gpt-4-turbo"  # $10.00 / 1M input, $30.00 / 1M output

class QuestionComplexity(Enum):
    """Question complexity levels"""
    SIMPLE = 1      # Greetings, basic info
    MODERATE = 2    # Service inquiries, prices
    COMPLEX = 3     # Medical advice, detailed analysis
    EXPERT = 4      # Multi-step reasoning, calculations

class DynamicModelSelector:
    """Selects the most appropriate AI model based on question complexity"""
    
    def __init__(self):
        # Simple patterns that can be handled by cheaper models
        self.simple_patterns = {
            'ar': [
                r'مرحبا|أهلا|السلام عليكم|صباح|مساء',  # Greetings
                r'شكرا|تمام|حسنا|نعم|لا|موافق',        # Simple responses
                r'كيف حالك|كيفك|شو اخبارك',            # How are you
                r'ما اسمك|مين انت',                    # Who are you
                r'وداعا|باي|الى اللقاء',               # Goodbye
            ],
            'en': [
                r'hi|hello|hey|good morning|good evening',  # Greetings
                r'thanks|thank you|ok|okay|yes|no',         # Simple responses
                r'how are you|what\'s up',                  # How are you
                r'who are you|what\'s your name',           # Who are you
                r'bye|goodbye|see you',                     # Goodbye
            ],
            'fr': [
                r'bonjour|salut|bonsoir',                   # Greetings
                r'merci|oui|non|d\'accord',                 # Simple responses
                r'comment allez-vous|ça va',                # How are you
                r'qui êtes-vous',                           # Who are you
                r'au revoir|à bientôt',                     # Goodbye
            ]
        }
        
        # Moderate complexity patterns
        self.moderate_patterns = {
            'ar': [
                r'كم سعر|كم تكلفة|الأسعار|السعر',      # Prices
                r'متى|موعد|المواعيد|ساعات العمل',      # Appointments/hours
                r'وين|أين|العنوان|الموقع',            # Location
                r'إزالة الشعر|ليزر الشعر',              # Basic services
                r'كيف احجز|الحجز|موعد',                 # How to book
            ],
            'en': [
                r'how much|price|cost|fees',            # Prices
                r'when|appointment|hours|schedule',     # Appointments/hours
                r'where|location|address',              # Location
                r'hair removal|laser hair',             # Basic services
                r'how to book|booking|reservation',     # How to book
            ],
            'fr': [
                r'combien|prix|coût|tarif',            # Prices
                r'quand|rendez-vous|horaires',         # Appointments/hours
                r'où|adresse|localisation',            # Location
                r'épilation|laser',                    # Basic services
                r'comment réserver|réservation',       # How to book
            ]
        }
        
        # Complex patterns requiring better models
        self.complex_patterns = {
            'ar': [
                r'حرق|ألم|التهاب|حساسية|مشكلة طبية',   # Medical issues
                r'وشم|تاتو|إزالة الوشم',                # Tattoo removal
                r'نصيحة|ماذا تنصح|أفضل علاج',          # Advice needed
                r'مقارنة|الفرق بين|أيهما أفضل',       # Comparisons
                r'تفاصيل|شرح|كيف يعمل',                # Detailed explanations
            ],
            'en': [
                r'burn|pain|inflammation|allergy|medical',  # Medical issues
                r'tattoo|tattoo removal',                   # Tattoo removal
                r'advice|recommend|best treatment',         # Advice needed
                r'compare|difference|which is better',      # Comparisons
                r'details|explain|how does.*work',          # Detailed explanations
            ],
            'fr': [
                r'brûlure|douleur|inflammation|allergie',   # Medical issues
                r'tatouage|détatouage',                     # Tattoo removal
                r'conseil|recommandez|meilleur traitement', # Advice needed
                r'comparer|différence|lequel est mieux',    # Comparisons
                r'détails|expliquer|comment.*fonctionne',   # Detailed explanations
            ]
        }
        
        # Keywords that always require the best model
        self.expert_keywords = [
            'حالة طارئة', 'emergency', 'urgence',
            'خطير', 'serious', 'grave',
            'عاجل', 'urgent', 'urgente',
            'مضاعفات', 'complications', 'complications',
            'حامل', 'pregnant', 'enceinte',
            'سرطان', 'cancer', 'cancer',
        ]
        
        # Model selection rules
        self.model_rules = {
            QuestionComplexity.SIMPLE: ModelTier.MINI,
            QuestionComplexity.MODERATE: ModelTier.MINI,  # Still use mini for cost
            QuestionComplexity.COMPLEX: ModelTier.GPT4,
            QuestionComplexity.EXPERT: ModelTier.GPT4,
        }
        
        # Cost tracking (per 1K tokens)
        self.model_costs = {
            ModelTier.MINI: {'input': 0.00015, 'output': 0.0006},
            ModelTier.TURBO: {'input': 0.0005, 'output': 0.0015},
            ModelTier.GPT4: {'input': 0.0025, 'output': 0.01},
            ModelTier.GPT4_ADVANCED: {'input': 0.01, 'output': 0.03},
        }

    def detect_language(self, text: str) -> str:
        """Detect the language of the text"""
        text_lower = text.lower()
        
        # Arabic detection
        arabic_chars = sum(1 for char in text if '\u0600' <= char <= '\u06FF')
        if arabic_chars > len(text) * 0.3:
            return 'ar'
        
        # French detection
        french_words = ['bonjour', 'merci', 'comment', 'vous', 'est', 'une']
        if any(word in text_lower for word in french_words):
            return 'fr'
        
        # Default to English
        return 'en'

    def analyze_complexity(self, question: str, context: list = None) -> QuestionComplexity:
        """
        Analyze the complexity of a question
        
        Args:
            question: The user's question
            context: Previous conversation context (optional)
            
        Returns:
            QuestionComplexity level
        """
        question_lower = question.lower()
        lang = self.detect_language(question)
        
        # Check for expert-level keywords first (highest priority)
        for keyword in self.expert_keywords:
            if keyword in question_lower:
                return QuestionComplexity.EXPERT
        
        # Check if it's a follow-up question requiring context
        if context and len(context) > 2:
            # If there's significant context, it might be complex
            if any(word in question_lower for word in ['لماذا', 'why', 'pourquoi', 'كيف', 'how', 'comment']):
                return QuestionComplexity.COMPLEX
        
        # Check for complex patterns
        if lang in self.complex_patterns:
            for pattern in self.complex_patterns[lang]:
                if re.search(pattern, question_lower):
                    return QuestionComplexity.COMPLEX
        
        # Check for moderate patterns
        if lang in self.moderate_patterns:
            for pattern in self.moderate_patterns[lang]:
                if re.search(pattern, question_lower):
                    return QuestionComplexity.MODERATE
        
        # Check for simple patterns
        if lang in self.simple_patterns:
            for pattern in self.simple_patterns[lang]:
                if re.search(pattern, question_lower):
                    return QuestionComplexity.SIMPLE
        
        # Check question length as a factor
        word_count = len(question.split())
        if word_count <= 3:
            return QuestionComplexity.SIMPLE
        elif word_count <= 10:
            return QuestionComplexity.MODERATE
        elif word_count <= 25:
            return QuestionComplexity.COMPLEX
        else:
            return QuestionComplexity.EXPERT
    
    def select_model(self, 
                     question: str, 
                     context: list = None,
                     force_best: bool = False,
                     user_tier: str = "standard") -> Tuple[str, Dict[str, Any]]:
        """
        Select the most appropriate model for the question
        
        Args:
            question: The user's question
            context: Previous conversation context
            force_best: Force use of best model (e.g., for VIP customers)
            user_tier: User subscription tier (standard/premium/vip)
            
        Returns:
            Tuple of (model_name, metadata_dict)
        """
        # VIP users always get the best model
        if force_best or user_tier == "vip":
            return ModelTier.GPT4.value, {
                'complexity': QuestionComplexity.EXPERT.name,
                'reason': 'VIP user - best model selected',
                'estimated_cost': self._estimate_cost(question, ModelTier.GPT4)
            }
        
        # Analyze question complexity
        complexity = self.analyze_complexity(question, context)
        
        # Select model based on complexity
        selected_model = self.model_rules[complexity]
        
        # Premium users get upgraded one tier
        if user_tier == "premium" and selected_model == ModelTier.MINI:
            selected_model = ModelTier.GPT4
        
        # Calculate estimated cost
        estimated_cost = self._estimate_cost(question, selected_model)
        
        # Return model and metadata
        metadata = {
            'complexity': complexity.name,
            'complexity_level': complexity.value,
            'model_tier': selected_model.name,
            'estimated_cost': estimated_cost,
            'reason': self._get_selection_reason(complexity, question)
        }
        
        return selected_model.value, metadata
    
    def _estimate_cost(self, text: str, model: ModelTier) -> float:
        """Estimate the cost for processing this text"""
        # Rough token estimation (1 token ≈ 4 characters)
        estimated_tokens = len(text) / 4
        input_cost = (estimated_tokens / 1000) * self.model_costs[model]['input']
        # Assume output is 2x input length
        output_cost = (estimated_tokens * 2 / 1000) * self.model_costs[model]['output']
        return round(input_cost + output_cost, 6)
    
    def _get_selection_reason(self, complexity: QuestionComplexity, question: str) -> str:
        """Get a human-readable reason for model selection"""
        reasons = {
            QuestionComplexity.SIMPLE: "Simple greeting or basic question",
            QuestionComplexity.MODERATE: "Standard service inquiry",
            QuestionComplexity.COMPLEX: "Detailed explanation or medical concern",
            QuestionComplexity.EXPERT: "Critical issue requiring best analysis"
        }
        return reasons.get(complexity, "General inquiry")
    
    def get_cost_savings(self, question: str, actual_model: str, forced_model: str = "gpt-4o") -> float:
        """Calculate cost savings by using dynamic selection"""
        actual_cost = self._estimate_cost(question, ModelTier(actual_model))
        forced_cost = self._estimate_cost(question, ModelTier(forced_model))
        return round(forced_cost - actual_cost, 6)


# Singleton instance
model_selector = DynamicModelSelector()


def select_optimal_model(question: str, 
                         context: list = None,
                         user_tier: str = "standard") -> Tuple[str, Dict[str, Any]]:
    """
    Main function to select optimal model
    
    Args:
        question: User's question
        context: Conversation history
        user_tier: User subscription level
        
    Returns:
        Tuple of (model_name, metadata)
    """
    return model_selector.select_model(question, context, user_tier=user_tier)


# Example usage and testing
if __name__ == "__main__":
    # Test cases
    test_questions = [
        ("مرحبا", "ar"),  # Simple greeting
        ("كم سعر إزالة الشعر بالليزر؟", "ar"),  # Moderate - pricing
        ("عندي حرق من الليزر وألم شديد، ماذا أفعل؟", "ar"),  # Complex - medical
        ("Hello", "en"),  # Simple
        ("What are your prices for laser hair removal?", "en"),  # Moderate
        ("I have severe burns and need urgent medical advice", "en"),  # Expert
    ]
    
    for question, expected_lang in test_questions:
        model, metadata = select_optimal_model(question)
        print(f"\nQuestion: {question}")
        print(f"Selected Model: {model}")
        print(f"Complexity: {metadata['complexity']}")
        print(f"Estimated Cost: ${metadata['estimated_cost']}")
        print(f"Reason: {metadata['reason']}")