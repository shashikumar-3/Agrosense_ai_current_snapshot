from __future__ import annotations

import logging
from werkzeug.datastructures import FileStorage

from config.settings import Config
from models.disease_predictions import fetch_last_prediction, insert_prediction
from services.cloudinary_service import upload_image_bytes
from services import gemini_service, groq_service
from services.huggingface_service import classify_image, humanize_label
from utils.errors import PredictionPipelineError

logger = logging.getLogger(__name__)


def _heuristic_insights(disease_name: str, confidence: float) -> dict:
    """Used only when neither Groq nor Gemini is configured/reachable — keeps /predict usable."""
    healthy = "healthy" in disease_name.lower()
    if healthy:
        severity = "Low"
        treatment = "No treatment needed — plant appears healthy. Keep up routine care."
        causes = "No disease indicators detected in this image."
        prevention = "Maintain regular watering, balanced fertilization, and good airflow."
        fertilizers = "Continue your standard feeding schedule."
        recovery = "N/A"
    else:
        severity = "Moderate" if confidence >= 0.6 else "Mild"
        treatment = (
            f"Isolate affected plants where possible, remove visibly damaged leaves, and apply a "
            f"treatment appropriate for {disease_name} (consult a local agronomist or extension "
            f"service to confirm the exact product)."
        )
        causes = f"Symptoms consistent with {disease_name}; exact cause not verified by an AI vision check."
        prevention = "Improve airflow, avoid overhead watering, and rotate crops where applicable."
        fertilizers = "Balanced NPK; avoid excess nitrogen until the plant recovers."
        recovery = "1-3 weeks, depending on severity and treatment."
    return {
        "is_crop_leaf_image": True,
        "severity": severity,
        "causes": causes,
        "treatment": treatment,
        "prevention": prevention,
        "fertilizers": fertilizers,
        "recovery_time": recovery,
        "validation_note": "",
    }


def _classify_with_fallback(raw: bytes) -> tuple[str, float]:
    try:
        return classify_image(raw)
    except PredictionPipelineError as hf_exc:
        if Config.groq_ready():
            try:
                logger.warning(
                    "Hugging Face classification failed (%s) — using Groq vision fallback",
                    hf_exc.error_code,
                )
                return groq_service.groq_classify_from_image_bytes(raw)
            except Exception as groq_exc:
                logger.warning("Groq classification fallback failed: %s", groq_exc)
        if Config.gemini_ready():
            try:
                logger.warning(
                    "Hugging Face classification failed (%s) — using Gemini vision fallback",
                    hf_exc.error_code,
                )
                return gemini_service.gemini_classify_from_image_bytes(raw)
            except Exception as gemini_exc:
                logger.warning("Gemini classification fallback failed: %s", gemini_exc)
        raise


def _generate_insights(image_url: str, disease_display: str, hf_score: float, raw: bytes) -> dict:
    if Config.groq_ready():
        try:
            return groq_service.generate_insights_and_validate(image_url, disease_display, hf_score, image_bytes=raw)
        except Exception as exc:
            logger.warning("Groq insights failed, falling back: %s", exc)
    if Config.gemini_ready():
        try:
            return gemini_service.generate_insights_and_validate(
                image_url, disease_display, hf_score, image_bytes=raw
            )
        except Exception as exc:
            logger.warning("Gemini insights failed, falling back to heuristic: %s", exc)
    return _heuristic_insights(disease_display, hf_score)


def _compare_trend(previous: dict, disease_display: str, hf_score: float, severity: str) -> tuple[str, str]:
    if Config.groq_ready():
        try:
            return groq_service.compare_previous_vs_current(previous, disease_display, float(hf_score), severity)
        except Exception as exc:
            logger.warning("Groq trend comparison failed, falling back: %s", exc)
    if Config.gemini_ready():
        try:
            return gemini_service.compare_previous_vs_current(previous, disease_display, float(hf_score), severity)
        except Exception as exc:
            logger.warning("Gemini trend comparison failed: %s", exc)
    prev_conf = float(previous.get("confidence") or 0)
    if disease_display.lower() != str(previous.get("disease_name", "")).lower():
        return "Same", "Different condition detected than the last record — treat as a new assessment."
    if hf_score < prev_conf - 0.05:
        return "Improving", "Confidence in the condition decreased since the last record."
    if hf_score > prev_conf + 0.05:
        return "Worsening", "Confidence in the condition increased since the last record."
    return "Same", "No significant change since the last record."


def run_crop_prediction(
    image: FileStorage | None,
    plant_id: str,
    *,
    client_image_url: str | None = None,
) -> dict:
    if not image or image.filename == "":
        raise PredictionPipelineError('Missing image file. Send multipart form-data with field "image".', 400)

    plant_id = (plant_id or "default").strip()[:64] or "default"

    image.stream.seek(0)
    raw = image.read()
    if not raw:
        raise PredictionPipelineError("Empty image file.", 400)

    # Prefer URL from client only if provided; default is signed server upload (no unsigned upload preset).
    image_url = (client_image_url or "").strip()
    if not image_url:
        image_url = upload_image_bytes(raw)

    hf_label, hf_score = _classify_with_fallback(raw)
    disease_display = humanize_label(hf_label)

    ai_block = _generate_insights(image_url, disease_display, hf_score, raw)

    if not ai_block.get("is_crop_leaf_image", True):
        note = ai_block.get("validation_note") or "Please upload a clear photograph of a plant leaf."
        raise PredictionPipelineError(note, 400)

    insights = {
        "causes": ai_block.get("causes", ""),
        "treatment": ai_block.get("treatment", ""),
        "prevention": ai_block.get("prevention", ""),
        "fertilizers": ai_block.get("fertilizers", ""),
        "recovery_time": ai_block.get("recovery_time", ""),
        "validation_note": ai_block.get("validation_note", ""),
    }
    severity = str(ai_block.get("severity", "Moderate"))

    previous = fetch_last_prediction(plant_id)
    trend = "Same"
    comparison_analysis = "First record for this plant — no prior comparison."

    if previous:
        trend, comparison_analysis = _compare_trend(previous, disease_display, hf_score, severity)

    insert_prediction(
        plant_id=plant_id,
        image_url=image_url,
        disease_name=disease_display,
        confidence=float(hf_score),
        severity=severity,
        insights=insights,
        trend=trend,
        comparison_analysis=comparison_analysis,
    )

    return {
        "disease": disease_display,
        "confidence": round(float(hf_score), 4),
        "severity": severity,
        "insights": insights,
        "trend": trend,
        "comparison_analysis": comparison_analysis,
        "image_url": image_url,
        "plant_id": plant_id,
    }
