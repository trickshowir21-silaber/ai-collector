from __future__ import annotations
import asyncio
import json
from typing import Any
import httpx
from loguru import logger
from app.config import settings

SYSTEM_PROMPT = """You are an expert AI content curator for a Persian-language Telegram channel.

Analyze the given content and return a JSON object with EXACTLY these fields:
{
  "summary_fa": "A 2-3 sentence summary written in colloquial Persian (خودمانی). Use Persian equivalents for tech terms where they exist naturally.",
  "summary_en": "A 2-3 sentence summary in English, concise and engaging",
  "category": "One of: tutorial, news, tool, prompt, paper, other",
  "score": 8.5,
  "hashtags": ["AI", "ChatGPT"]
}

Rules:
- summary_fa: colloquial Persian, NOT formal
- summary_en: concise English
- score: 0-10, only 8+ for excellent content
- hashtags: 3-5 without #
- Return ONLY valid JSON"""

_last_gemini_call = 0.0
_last_openai_call = 0.0
_last_deepseek_call = 0.0
GEMINI_INTERVAL = 5.5
OPENAI_INTERVAL = 2.0
DEEPSEEK_INTERVAL = 3.0


class AIService:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._logged = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _rate_limit(self, provider: str) -> None:
        global _last_gemini_call, _last_openai_call, _last_deepseek_call
        now = asyncio.get_event_loop().time()
        if provider == "gemini":
            elapsed = now - _last_gemini_call
            if elapsed < GEMINI_INTERVAL:
                await asyncio.sleep(GEMINI_INTERVAL - elapsed)
            _last_gemini_call = asyncio.get_event_loop().time()
        elif provider == "openai":
            elapsed = now - _last_openai_call
            if elapsed < OPENAI_INTERVAL:
                await asyncio.sleep(OPENAI_INTERVAL - elapsed)
            _last_openai_call = asyncio.get_event_loop().time()
        elif provider == "deepseek":
            elapsed = now - _last_deepseek_call
            if elapsed < DEEPSEEK_INTERVAL:
                await asyncio.sleep(DEEPSEEK_INTERVAL - elapsed)
            _last_deepseek_call = asyncio.get_event_loop().time()

    async def _call_gemini(self, content: str, system: str = SYSTEM_PROMPT, json_mode: bool = True):
        if not settings.gemini_api_key:
            return None
        await self._rate_limit("gemini")
        client = await self._get_client()
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.0-flash:generateContent?key={settings.gemini_api_key}"
            )
            prompt_text = f"{system}\n\n{content}"
            if json_mode:
                prompt_text += "\n\nIMPORTANT: Return ONLY valid JSON. No markdown, no code blocks."
            body = {
                "contents": [{"parts": [{"text": prompt_text}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
            }
            resp = await client.post(url, json=body)
            if resp.status_code == 429:
                logger.warning("Gemini 429! Waiting 65s then retry...")
                await asyncio.sleep(65)
                resp = await client.post(url, json=body)
            if resp.status_code != 200:
                logger.error(f"Gemini HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            if json_mode:
                return json.loads(text)
            return text.strip()
        except json.JSONDecodeError:
            logger.error("Gemini: JSON parse error")
            return None
        except httpx.TimeoutException:
            logger.error("Gemini: TIMEOUT")
            return None
        except Exception as e:
            logger.error(f"Gemini: {type(e).__name__}: {e}")
            return None

    async def _call_openai(self, content: str, system: str = SYSTEM_PROMPT, json_mode: bool = True):
        if not settings.openai_api_key:
            return None
        await self._rate_limit("openai")
        client = await self._get_client()
        try:
            body = {
                "model": settings.openai_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.3,
            }
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json=body,
            )
            if resp.status_code != 200:
                logger.error(f"OpenAI HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            if json_mode:
                return json.loads(text)
            return text.strip()
        except Exception as e:
            logger.error(f"OpenAI: {type(e).__name__}: {e}")
            return None

    async def _call_deepseek(self, content: str, system: str = SYSTEM_PROMPT, json_mode: bool = True):
        if not settings.deepseek_api_key:
            return None
        await self._rate_limit("deepseek")
        client = await self._get_client()
        try:
            body = {
                "model": settings.deepseek_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.3,
            }
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            resp = await client.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if resp.status_code != 200:
                logger.error(f"DeepSeek HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            if json_mode:
                return json.loads(text)
            return text.strip()
        except Exception as e:
            logger.error(f"DeepSeek: {type(e).__name__}: {e}")
            return None

    async def _call_any(self, content, system=SYSTEM_PROMPT, json_mode=True):
        if not self._logged:
            providers = []
            if settings.gemini_api_key:
                providers.append("Gemini")
            if settings.openai_api_key:
                providers.append("OpenAI")
            if settings.deepseek_api_key:
                providers.append("DeepSeek")
            logger.info(f"AI providers: {providers}")
            if not providers:
                logger.error("NO AI KEY! Set GEMINI_API_KEY or OPENAI_API_KEY or DEEPSEEK_API_KEY")
            self._logged = True

        for func in [self._call_gemini, self._call_openai, self._call_deepseek]:
            try:
                result = await func(content, system=system, json_mode=json_mode)
                if result:
                    name = func.__name__.replace("_call_", "")
                    logger.info(f"AI OK via {name}")
                    return result
            except Exception as e:
                logger.error(f"{func.__name__}: {type(e).__name__}: {e}")

        logger.error("ALL AI providers failed!")
        return None

    async def analyze_content(self, title: str, text: str, url: str | None = None) -> dict[str, Any]:
        payload = f"Title: {title}\n\nContent:\n{text[:4000]}"
        if url:
            payload += f"\n\nURL: {url}"
        result = await self._call_any(payload)
        if result and isinstance(result, dict):
            return self._normalize(result)
        return {
            "summary_fa": f"مطلب جدید: {title}",
            "summary_en": f"New content: {title}",
            "category": "other",
            "score": 5.0,
            "hashtags": ["AI"],
        }

    async def translate_to_farsi(self, text: str) -> str:
        prompt = f"Translate this to colloquial Persian:\n\n{text[:3500]}"
        result = await self._call_any(
            prompt, system="You are a professional Persian translator. Return only the translation.", json_mode=False,
        )
        if result and isinstance(result, str) and len(result) > 10:
            return result
        return "[ترجمه ناموفق]"

    async def translate_to_english(self, text: str) -> str:
        prompt = f"Translate this to English:\n\n{text[:3500]}"
        result = await self._call_any(
            prompt, system="You are a professional English translator. Return only the translation.", json_mode=False,
        )
        if result and isinstance(result, str) and len(result) > 10:
            return result
        return "[Translation failed]"

    @staticmethod
    def _normalize(result: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary_fa": str(result.get("summary_fa", "خلاصه‌ای نیست")),
            "summary_en": str(result.get("summary_en", result.get("summary", ""))),
            "category": str(result.get("category", "other")).lower(),
            "score": max(0.0, min(10.0, float(result.get("score", 5.0)))),
            "hashtags": list(result.get("hashtags", ["AI"]))[:5],
        }


ai_service = AIService()
