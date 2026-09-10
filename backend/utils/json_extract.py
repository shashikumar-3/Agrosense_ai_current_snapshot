from __future__ import annotations

import json
import re

from utils.errors import PredictionPipelineError


def parse_json_response(text: str, *, source: str = "AI") -> dict:
    """Extract a JSON object from an LLM text response (handles ```json fences and stray prose)."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        raise PredictionPipelineError(f"{source} returned non-JSON output", 502, details=text[:1200]) from None
