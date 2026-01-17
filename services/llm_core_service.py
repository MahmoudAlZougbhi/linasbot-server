# services/llm_core_service.py
from openai import AsyncOpenAI
import config

# تهيئة عميل OpenAI
client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)