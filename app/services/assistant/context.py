"""Utilities for shaping assistant prompts with application context."""
from __future__ import annotations

from typing import Any, Dict, List


def format_context_summary(context: Dict[str, Any] | None) -> str:
    """Build a short natural language summary from context metadata."""
    if not context:
        return ""

    parts: List[str] = []

    page = context.get("page") or context.get("currentPage")
    if page:
        parts.append(f"The user is currently on the {page} page.")

    analysis = context.get("analysis") or {}
    if analysis:
        title = analysis.get("title") or analysis.get("id")
        savings = analysis.get("summary", {}).get("percentSavings")
        shipments = analysis.get("summary", {}).get("totalShipments")
        if title:
            parts.append(f"They are reviewing analysis '{title}'.")
        if savings is not None:
            parts.append(f"The analysis reports {savings}% savings.")
        if shipments is not None:
            parts.append(f"It covers {shipments} shipments.")

    uploads = context.get("upload") or {}
    if uploads:
        filename = uploads.get("filename")
        status = uploads.get("status")
        if filename:
            parts.append(f"Recent upload: {filename}.")
        if status:
            parts.append(f"Upload status: {status}.")

    rate_settings = context.get("rateSettings") or {}
    if rate_settings:
        mark = rate_settings.get("markupPercent")
        fuel = rate_settings.get("fuelSurchargePercent")
        origin = rate_settings.get("originZip")
        details: List[str] = []
        if mark is not None:
            details.append(f"markup {mark}%")
        if fuel is not None:
            details.append(f"fuel surcharge {fuel}%")
        if origin:
            details.append(f"origin ZIP {origin}")
        if details:
            parts.append("Configured rate settings: " + ", ".join(details) + ".")

    if not parts:
        return ""
    return " ".join(parts)
