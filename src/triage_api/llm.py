from openai import AsyncOpenAI

from triage_api.config import settings

LLM = AsyncOpenAI(
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
)
