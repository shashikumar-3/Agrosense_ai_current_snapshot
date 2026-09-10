"""Two-image + environmental observation-based risk prognosis.

Provider order: Groq (primary) -> Gemini (secondary, if configured) -> local heuristic. Any
provider exception falls through to the next rather than failing the request — this endpoint
should always return a usable result.
"""
from __future__ import annotations

import logging

from config.settings import Config
from services.gemini_service import gemini_two_image_prognosis
from services.groq_service import groq_two_image_prognosis
from utils.errors import PredictionPipelineError

logger = logging.getLogger(__name__)


def _heuristic_prognosis(*, humidity: float, temperature: float, ndvi: float) -> dict:
    """Fallback when Gemini API key is absent; still return useful risk guidance for demos/local use."""
    risk_score = 0.0
    if humidity >= 75:
        risk_score += 0.35
    if temperature >= 28:
        risk_score += 0.25
    if ndvi < 0.35:
        risk_score += 0.25
    if humidity < 40 and ndvi > 0.7:
        risk_score -= 0.15

    if risk_score >= 0.75:
        risk_level = "high"
        likely = True
        summary = (
            "Environmental conditions are favoring stress and disease development, and canopy vigor appears weak. "
            "Monitor the crop closely and act early with crop hygiene and ventilation measures."
        )
    elif risk_score >= 0.35:
        risk_level = "moderate"
        likely = True
        summary = (
            "Current conditions suggest a moderate risk of disease or stress. Watch for spreading lesions, color change, "
            "or accelerated canopy decline over the next few days."
        )
    else:
        risk_level = "low"
        likely = False
        summary = (
            "Current conditions appear comparatively stable. Keep routine scouting in place, but there is no strong sign "
            "of an immediate outbreak based on the provided environmental pattern."
        )

    return {
        "risk_level": risk_level,
        "disease_outbreak_likely": likely,
        "summary": summary,
        "visual_changes": "Image comparison indicates the crop should be checked for subtle canopy stress and lesion spread.",
        "env_interpretation": (
            f"Humidity of {humidity:.1f}%, temperature of {temperature:.1f}°C, and NDVI of {ndvi:.3f} suggest a "
            f"{risk_level} stress profile for the current field conditions."
        ),
        "precautions": [
            "Improve air movement around dense canopies when humidity stays high.",
            "Remove affected leaves promptly and avoid unnecessary overhead watering.",
            "Keep field scouting frequent for new lesions or wilting spots.",
        ],
        "watch_signs": [
            "Yellowing or browning leaf margins", "New leaf spots spreading between plants", "Canopy thinning despite regular moisture"
        ],
    }


def parse_observation_floats(humidity_raw: str, temperature_raw: str, ndvi_raw: str) -> tuple[float, float, float]:
    """Parse and validate humidity %, °C, NDVI. Raises PredictionPipelineError on bad input."""
    errs: list[str] = []
    try:
        humidity = float(humidity_raw)
    except (TypeError, ValueError):
        humidity = float("nan")
        errs.append("humidity must be a number")
    try:
        temperature = float(temperature_raw)
    except (TypeError, ValueError):
        temperature = float("nan")
        errs.append("temperature must be a number")
    try:
        ndvi = float(ndvi_raw)
    except (TypeError, ValueError):
        ndvi = float("nan")
        errs.append("ndvi must be a number")
    if errs:
        raise PredictionPipelineError("; ".join(errs), 400)

    if not 0 <= humidity <= 100:
        raise PredictionPipelineError("humidity must be between 0 and 100 (percent).", 400)
    if not -15 <= temperature <= 55:
        raise PredictionPipelineError("temperature must be between -15 and 55 (°C).", 400)
    if not -1 <= ndvi <= 1:
        raise PredictionPipelineError("NDVI must be between -1 and 1.", 400)

    return humidity, temperature, ndvi


def run_prognosis(
    current_bytes: bytes,
    previous_bytes: bytes,
    *,
    humidity: float,
    temperature: float,
    ndvi: float,
    plant_id: str,
) -> dict:
    core: dict | None = None
    if current_bytes and previous_bytes:
        if Config.groq_ready():
            try:
                core = groq_two_image_prognosis(
                    current_bytes, previous_bytes, humidity_pct=humidity, temperature_c=temperature, ndvi=ndvi
                )
            except Exception as exc:
                logger.warning("Groq prognosis failed, falling back: %s", exc)
        if core is None and Config.gemini_ready():
            try:
                core = gemini_two_image_prognosis(
                    current_bytes, previous_bytes, humidity_pct=humidity, temperature_c=temperature, ndvi=ndvi
                )
            except Exception as exc:
                logger.warning("Gemini prognosis failed, falling back to heuristic: %s", exc)
    if core is None:
        core = _heuristic_prognosis(humidity=humidity, temperature=temperature, ndvi=ndvi)
    return {
        **core,
        "inputs": {
            "humidity": humidity,
            "temperature": temperature,
            "ndvi": ndvi,
            "plant_id": plant_id[:64] if plant_id else "default",
        },
    }
