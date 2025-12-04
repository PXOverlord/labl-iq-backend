"""Providers for generating assistant responses."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from .context import format_context_summary
from .models import AssistantMessage

try:  # pragma: no cover - optional dependency guard
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore


@dataclass
class AssistantCompletion:
    """Represents a generated response from the assistant."""

    content: str
    suggestions: Optional[List[str]] = None


class AssistantProvider:
    """Base provider interface."""

    async def complete_chat(
        self,
        messages: Iterable[AssistantMessage],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> AssistantCompletion:
        raise NotImplementedError


class LocalAssistantProvider(AssistantProvider):
    """Rule-based assistant used when no external LLM is configured."""

    def __init__(self, base_prompt: str):
        self.base_prompt = base_prompt

    async def complete_chat(
        self,
        messages: Iterable[AssistantMessage],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> AssistantCompletion:
        history = list(messages)
        latest = history[-1].content if history else ""
        summary = format_context_summary(context)
        lower = latest.lower()

        suggestions: List[str] = []
        if any(keyword in lower for keyword in ["rate", "analysis", "optimiz", "savings"]):
            body = (
                "Here is how we can tackle your rate analysis:\n\n"
                "1. Upload a recent shipment file so we can review carrier spend\n"
                "2. Map your weight, zone, and cost columns to the LABL IQ template\n"
                "3. Apply your markup, fuel surcharge, and delivery fees from rate settings\n"
                "4. Review the savings summary and rate opportunities\n\n"
                "Let me know if you want quick tips on uploads or a fresh report."
            )
            suggestions = ["Upload data", "Review analytics", "Generate savings report"]
        elif any(keyword in lower for keyword in ["upload", "file", "import", "csv", "excel"]):
            body = (
                "To move your data through LABL IQ:\n\n"
                "• Go to Upload, drag in your CSV or Excel file\n"
                "• Confirm the detected columns or adjust the mapping\n"
                "• Save a column profile if you will reuse this format\n"
                "• Run processing to calculate Amazon rate comparisons\n\n"
                "Need help with a specific column or error message?"
            )
            suggestions = ["Column mapping tips", "Create column profile", "Troubleshoot upload"]
        elif any(keyword in lower for keyword in ["setting", "config", "preference", "profile"]):
            body = (
                "Settings are split across a few panels:\n\n"
                "• Rate Settings → markup, surcharges, origin ZIP\n"
                "• Column Profiles → reusable mappings for each data source\n"
                "• Preferences → themes, notifications, defaults\n"
                "• Admin → workspace-level controls\n\n"
                "Tell me which area you'd like to tune and I can walk you through it."
            )
            suggestions = ["Rate settings", "Column profiles", "User preferences"]
        elif any(keyword in lower for keyword in ["report", "export", "download"]):
            body = (
                "You can export savings summaries as CSV, Excel, or PDF from the Results page. "
                "If you need a presentation-ready brief, I can draft highlights from the latest analysis."
            )
            suggestions = ["Download CSV", "Create PDF summary", "Build client brief"]
        else:
            intro = (
                "I'm your LABL IQ assistant. I help with upload workflows, rate settings, analytics, and reporting."
            )
            context_line = f" {summary}" if summary else ""
            body = f"{intro}{context_line} What would you like to do next?"
            suggestions = ["Analyze my rates", "Help with uploads", "Show my last results"]

        if summary and "What would you like" in body:
            body += "\n\nKey context: " + summary

        return AssistantCompletion(content=body.strip(), suggestions=suggestions)


class OpenAIChatProvider(AssistantProvider):
    """OpenAI-backed provider for richer conversational responses."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_prompt: str,
        api_base: Optional[str] = None,
        history_limit: int = 10,
    ) -> None:
        if AsyncOpenAI is None:  # pragma: no cover - guard if dependency missing
            raise RuntimeError("openai package is not available")
        client_kwargs: Dict[str, Any] = {"api_key": api_key}
        if api_base:
            client_kwargs["base_url"] = api_base
        self.client = AsyncOpenAI(**client_kwargs)
        self.model = model
        self.base_prompt = base_prompt
        self.history_limit = history_limit

    async def complete_chat(
        self,
        messages: Iterable[AssistantMessage],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> AssistantCompletion:
        history = list(messages)[-self.history_limit :]
        context_summary = format_context_summary(context)
        system_prompt = self._build_system_prompt(context_summary)
        payload = [{"role": "system", "content": system_prompt}]
        payload.extend({"role": msg.role, "content": msg.content} for msg in history)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=payload,
            temperature=0.5,
            max_tokens=600,
        )
        message = response.choices[0].message.content or ""
        return self._parse_response(message)

    def _build_system_prompt(self, context_summary: str) -> str:
        prompt = (
            f"{self.base_prompt}\n\n"
            "Always respond with JSON using the shape {\"content\": string, \"suggestions\": string[]}."
        )
        if context_summary:
            prompt += f"\nContext: {context_summary}"
        return prompt

    def _parse_response(self, message: str) -> AssistantCompletion:
        message = message.strip()
        try:
            payload = json.loads(message)
            content = str(payload.get("content", "")).strip()
            suggestions = payload.get("suggestions")
            if isinstance(suggestions, list):
                suggestions = [str(item) for item in suggestions if isinstance(item, str)]
            else:
                suggestions = None
            return AssistantCompletion(content=content or message, suggestions=suggestions)
        except json.JSONDecodeError:
            # Fall back if the model ignored the JSON contract
            suggestions = _extract_bullet_suggestions(message)
            return AssistantCompletion(content=message, suggestions=suggestions)


def _extract_bullet_suggestions(message: str) -> Optional[List[str]]:
    lines = [line.strip(" •-\t") for line in message.splitlines()]
    candidates = [line for line in lines if line]
    if not candidates:
        return None
    top = candidates[:3]
    return [item for item in top if len(item) < 80]
