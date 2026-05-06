import logging
from google import genai
from google.genai import types
from app.config import settings
from app.analyzer.prompt import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.analyzer.schema import GapAnalysisReport

logger = logging.getLogger(__name__)

# 1. Инициализируем НОВЫЙ клиент
# Он автоматически подхватывает асинхронность через .aio
client = genai.Client(api_key=settings.gemini_api_key)

async def analyze_gap(
    resume_text: str,
    vacancy_text: str,
) -> tuple[GapAnalysisReport, int]:
    """
    Анализирует резюме vs вакансия через Gemini 2.5 Flash-Lite (New SDK).
    """
    user_prompt = USER_PROMPT_TEMPLATE.format(
        resume_text=resume_text[:8000],
        vacancy_text=vacancy_text[:6000],
    )

    # 2. Используем асинхронный вызов через client.aio
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.1,
            response_mime_type="application/json",
            # В новом SDK передача Pydantic-класса работает стабильно
            response_schema=GapAnalysisReport,
        ),
    )

    # 3. Новый SDK возвращает результат, который Pydantic легко съест
    raw_json = response.text
    tokens = response.usage_metadata.total_token_count

    logger.info("Gemini analysis done. tokens=%d", tokens)

    # Валидируем данные (response_schema гарантирует структуру)
    report = GapAnalysisReport.model_validate_json(raw_json)
    return report, tokens
def _strip_markdown(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"): lines = lines[1:]
        if lines and lines[-1].startswith("```"): lines = lines[:-1]
        return "\n".join(lines).strip()
    return text