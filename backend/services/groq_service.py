"""Groq (OpenAI-compatible) chat completions — primary AI provider for this app.

Mirrors the public shape of services/gemini_service.py (classify, insights, compare, chat,
two-image prognosis) so prediction_service.py / prognosis_service.py can try Groq first and fall
back to Gemini, then a local heuristic, without changing their call sites much.

No extra dependency: talks to https://api.groq.com/openai/v1/chat/completions over `requests`,
which is already required by the rest of the backend.
"""
from __future__ import annotations

import base64
import logging
import time
from io import BytesIO
from typing import Any

import requests
from PIL import Image

from config.settings import Config
from utils.errors import PredictionPipelineError
from utils.json_extract import parse_json_response

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_AUTH_CODE = "GROQ_AUTH"
_GROQ_MODEL_CODE = "GROQ_MODEL"
_MAX_ATTEMPTS = 3
_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


def _exception_details(exc: BaseException) -> str:
    parts = [f"{type(exc).__name__}: {exc}"]
    if exc.__cause__:
        parts.append(f"caused_by: {type(exc.__cause__).__name__}: {exc.__cause__}")
    return " | ".join(parts)[:2000]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {Config.groq_api_key()}",
        "Content-Type": "application/json",
    }


def _pil_rgb_upload(image_bytes: bytes) -> Image.Image:
    im = Image.open(BytesIO(image_bytes)).convert("RGB")
    im.thumbnail((1024, 1024))
    return im


def _image_data_url(image_bytes: bytes) -> str:
    """Downscale + JPEG-encode, then base64 as a data: URL for Groq's image_url content part."""
    img = _pil_rgb_upload(image_bytes)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _post_chat(payload: dict) -> dict:
    """POST one chat-completions request. Retries transient errors; raises PredictionPipelineError otherwise."""
    last_err = ""
    for attempt in range(_MAX_ATTEMPTS):
        try:
            resp = requests.post(_ENDPOINT, headers=_headers(), json=payload, timeout=(15, 90))
        except requests.RequestException as exc:
            last_err = str(exc)
            logger.warning("Groq network error attempt=%s/%s %s", attempt + 1, _MAX_ATTEMPTS, exc)
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(min(8.0, (2.0**attempt) * 1.2))
            continue

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                raise PredictionPipelineError(
                    "Groq returned an unparseable response.", 502, details=_exception_details(exc)
                ) from exc

        body_preview = (resp.text or "")[:800]

        if resp.status_code in (401, 403):
            raise PredictionPipelineError(
                "Groq API key is invalid or lacks access. Verify GROQ_API_KEY at "
                "https://console.groq.com/keys and restart the backend.",
                502,
                error_code=_GROQ_AUTH_CODE,
                details=body_preview,
            )

        if resp.status_code in _RETRYABLE_STATUS:
            last_err = f"HTTP {resp.status_code}: {body_preview}"
            logger.warning(
                "Groq retryable status=%s attempt=%s/%s body=%s",
                resp.status_code,
                attempt + 1,
                _MAX_ATTEMPTS,
                body_preview,
            )
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(min(8.0, (2.0**attempt) * 1.2))
            continue

        # 400/404 with a decommissioned/unknown model is handled by the caller (model fallback).
        raise PredictionPipelineError(
            f"Groq request failed (HTTP {resp.status_code}): {body_preview[:300]}",
            502 if resp.status_code >= 500 else 400,
            error_code=_GROQ_MODEL_CODE,
            details=body_preview,
        )

    raise PredictionPipelineError(
        f"Groq request failed after {_MAX_ATTEMPTS} attempts: {last_err}",
        503,
        error_code=_GROQ_MODEL_CODE,
        details=last_err,
    )


def _is_model_unavailable(exc: PredictionPipelineError) -> bool:
    if exc.error_code != _GROQ_MODEL_CODE:
        return False
    msg = (exc.details or exc.message or "").lower()
    return any(
        token in msg
        for token in ("decommission", "model_not_found", "does not exist", "not found", "not supported")
    )


def _chat_with_model_fallback(
    chain: list[str],
    messages: list[dict],
    *,
    json_mode: bool,
    max_tokens: int = 1400,
    reasoning_effort: str = "low",
) -> tuple[str, str]:
    if not Config.groq_ready():
        raise PredictionPipelineError(
            "Groq is not configured (GROQ_API_KEY)", 503, details="No GROQ_API_KEY in backend/.env after load_dotenv."
        )

    last_exc: PredictionPipelineError | None = None
    for idx, model in enumerate(chain):
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "reasoning_effort": reasoning_effort,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            data = _post_chat(payload)
        except PredictionPipelineError as exc:
            if exc.error_code == _GROQ_AUTH_CODE:
                raise
            if _is_model_unavailable(exc):
                logger.warning("Groq model %r unavailable (%s); trying next in chain", model, exc.message)
                last_exc = exc
                continue
            last_exc = exc
            continue

        choice = (data.get("choices") or [{}])[0]
        content = ((choice.get("message") or {}).get("content") or "").strip()
        if not content:
            last_exc = PredictionPipelineError(
                "Groq returned an empty response (finish_reason=%s)." % choice.get("finish_reason"),
                502,
                error_code=_GROQ_MODEL_CODE,
            )
            continue
        if idx > 0:
            logger.warning("Groq succeeded with fallback model %r", model)
        return content, model

    chain_str = ", ".join(chain)
    detail = last_exc.details if last_exc else "unknown error"
    raise PredictionPipelineError(
        f"No Groq model in the configured chain succeeded ([{chain_str}]). "
        "Set GROQ_TEXT_MODEL / GROQ_VISION_MODEL in backend/.env to a live id from GET /health/groq.",
        502,
        error_code=_GROQ_MODEL_CODE,
        details=detail,
    ) from last_exc


def groq_health_probe() -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "api_key_configured": Config.groq_ready(),
        "text_model_chain": Config.groq_text_model_candidates(),
        "vision_model_chain": Config.groq_vision_model_candidates(),
        "models_preview": [],
        "generate_content_ok": None,
        "model_used_for_generate": None,
        "generate_sample": None,
        "hint": None,
    }
    if not Config.groq_ready():
        result["hint"] = "Set GROQ_API_KEY in backend/.env"
        return result

    try:
        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers=_headers(),
            timeout=(10, 20),
        )
        if resp.status_code == 200:
            data = resp.json()
            result["models_preview"] = sorted(
                m["id"] for m in data.get("data", []) if m.get("active")
            )[:60]
        else:
            result["hint"] = f"GET /models returned HTTP {resp.status_code}"
    except requests.RequestException as exc:
        result["hint"] = f"Could not list Groq models: {exc}"

    try:
        content, model_used = _chat_with_model_fallback(
            Config.groq_text_model_candidates(),
            [{"role": "user", "content": "Reply with exactly the single word: OK"}],
            json_mode=False,
            max_tokens=200,
        )
        result["generate_content_ok"] = True
        result["model_used_for_generate"] = model_used
        result["generate_sample"] = content[:120]
        result["ok"] = True
    except PredictionPipelineError as exc:
        result["generate_content_ok"] = False
        result["generate_error"] = exc.message
        result["details"] = exc.details
        result["hint"] = result["hint"] or "generateContent failed — see details."
    return result


_CLASSIFY_PROMPT = """You are a plant pathologist. Look at this crop or plant leaf image.

Respond with ONLY valid JSON (no markdown code fences) using exactly these keys:
{
  "disease_label": "short English name of the most likely disease, or Healthy_leaf if the plant looks healthy",
  "confidence": number between 0.05 and 0.99 for how sure you are
}

Rules:
- If the image is not a plant leaf or is too unclear, still pick your best guess but use confidence below 0.45.
- Use single-word underscores for spaces in the label if you like (e.g. Tomato_Leaf_Mold).
"""


def groq_classify_from_image_bytes(image_bytes: bytes) -> tuple[str, float]:
    try:
        data_url = _image_data_url(image_bytes)
    except Exception as exc:
        raise PredictionPipelineError(
            f"Could not decode image for classification: {exc}", 502, details=_exception_details(exc)
        ) from exc

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": _CLASSIFY_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]
    content, _m = _chat_with_model_fallback(Config.groq_vision_model_candidates(), messages, json_mode=True)
    data = parse_json_response(content, source="Groq")

    label = str(data.get("disease_label", "Unknown")).strip() or "Unknown"
    try:
        score = float(data.get("confidence", 0.55))
    except (TypeError, ValueError):
        score = 0.55
    score = max(0.05, min(0.99, score))
    return label, score


def generate_insights_and_validate(
    image_url: str,
    disease_name: str,
    confidence: float,
    *,
    image_bytes: bytes | None = None,
) -> dict:
    """Same output shape as gemini_service.generate_insights_and_validate."""
    if image_bytes:
        raw = image_bytes
    else:
        try:
            resp_img = requests.get(image_url, timeout=20, headers={"User-Agent": "AgroSenseAI/1.0"})
            resp_img.raise_for_status()
            raw = resp_img.content
        except Exception as exc:
            raise PredictionPipelineError(
                f"Could not load image for AI analysis: {exc}", 502, details=_exception_details(exc)
            ) from exc

    try:
        data_url = _image_data_url(raw)
    except Exception as exc:
        raise PredictionPipelineError(f"Could not decode image: {exc}", 502, details=_exception_details(exc)) from exc

    prompt = f"""You are an agricultural plant-pathology assistant.

The image classifier predicted this label: "{disease_name}" with confidence {confidence:.4f}.

Look at the image. Respond with ONLY valid JSON (no markdown code fences) using exactly these keys:
{{
  "is_crop_leaf_image": true or false,
  "severity": "one of: Low, Mild, Moderate, High, Severe",
  "causes": "short string",
  "treatment": "short actionable string",
  "prevention": "short string",
  "fertilizers": "short string (products or nutrients)",
  "recovery_time": "short string (e.g. 1-2 weeks)",
  "validation_note": "if not a leaf, explain briefly; else empty string"
}}

Rules:
- If the photo is not a plant leaf, flower, or crop close-up suitable for disease diagnosis (e.g. person, car, random object, soil only, very blurry), set "is_crop_leaf_image" to false and set "validation_note" asking the user to upload a clear photograph of a plant leaf.
- If it is suitable, set "is_crop_leaf_image" to true.
- Base severity and agronomic advice on the predicted label and what you see, but do not invent a different disease name — use the given label as the primary condition name context.
"""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]
    content, _m = _chat_with_model_fallback(Config.groq_vision_model_candidates(), messages, json_mode=True)
    return parse_json_response(content, source="Groq")


def compare_previous_vs_current(
    previous: dict,
    current_disease: str,
    current_confidence: float,
    current_severity: str,
) -> tuple[str, str]:
    import json as _json

    prompt = f"""Previous record:
- disease: {previous.get("disease_name")}
- confidence: {previous.get("confidence")}
- severity: {previous.get("severity")}
- insights summary: {_json.dumps(previous.get("insights") or {}, ensure_ascii=False)[:800]}

Current record:
- disease: {current_disease}
- confidence: {current_confidence}
- severity: {current_severity}

Respond with ONLY valid JSON (no markdown): {{
  "trend": "Improving" or "Worsening" or "Same",
  "comparison_analysis": "2-4 sentences: whether the plant situation improved or worsened, and concrete next steps for the farmer"
}}
"""
    try:
        content, _m = _chat_with_model_fallback(
            Config.groq_text_model_candidates(),
            [{"role": "user", "content": prompt}],
            json_mode=True,
        )
        data = parse_json_response(content, source="Groq")
    except Exception as exc:
        return "Same", f"Trend analysis unavailable: {exc}"
    trend = str(data.get("trend", "Same")).strip()
    if trend not in ("Improving", "Worsening", "Same"):
        trend = "Same"
    analysis = str(data.get("comparison_analysis", "")).strip()
    return trend, analysis or "No additional analysis."


_MAX_CHAT_CHARS = 4000


def groq_crop_chat(user_message: str, image_bytes: bytes) -> str:
    text = (user_message or "").strip()
    if not text:
        raise PredictionPipelineError("Message is empty.", 400)
    if len(text) > _MAX_CHAT_CHARS:
        raise PredictionPipelineError(f"Message exceeds {_MAX_CHAT_CHARS} characters.", 400)
    if not image_bytes:
        raise PredictionPipelineError("Image is required for crop chat.", 400)
    try:
        data_url = _image_data_url(image_bytes)
    except Exception as exc:
        raise PredictionPipelineError(f"Could not read image: {exc}", 400) from exc

    prompt = (
        "You are a helpful agricultural assistant for farmers. The user uploaded a photo of a crop or plant. "
        "Answer their question clearly and practically. If the image is unclear or not a plant, say so briefly.\n\n"
        f"User: {text}"
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]
    content, _m = _chat_with_model_fallback(
        Config.groq_vision_model_candidates(), messages, json_mode=False, max_tokens=900
    )
    return content


def _normalize_prognosis_payload(raw: dict) -> dict:
    risk = str(raw.get("risk_level", "moderate")).strip().lower()
    if risk not in ("low", "moderate", "high"):
        risk = "moderate"
    likely = raw.get("disease_outbreak_likely")
    if not isinstance(likely, bool):
        likely = str(likely).lower() in ("true", "1", "yes")

    def _str_list(key: str, min_n: int = 1) -> list[str]:
        v = raw.get(key)
        if not isinstance(v, list):
            return []
        out = [str(x).strip() for x in v if str(x).strip()]
        if len(out) < min_n:
            return []
        return out

    precautions = _str_list("precautions", 1)
    watch = _str_list("watch_signs", 1)
    if not precautions:
        precautions = ["Keep monitoring canopy color and leaf spots daily.", "Improve airflow if humidity stays high."]
    if not watch:
        watch = ["Yellowing or spreading lesions", "Unexpected wilting despite adequate soil moisture"]

    return {
        "risk_level": risk,
        "disease_outbreak_likely": likely,
        "summary": str(raw.get("summary", "")).strip() or "Assessment complete — review precautions below.",
        "visual_changes": str(raw.get("visual_changes", "")).strip() or "No detailed visual comparison returned.",
        "env_interpretation": str(raw.get("env_interpretation", "")).strip()
        or "Environmental data considered with image comparison.",
        "precautions": precautions[:12],
        "watch_signs": watch[:12],
    }


def groq_two_image_prognosis(
    current_bytes: bytes,
    previous_bytes: bytes,
    *,
    humidity_pct: float,
    temperature_c: float,
    ndvi: float,
) -> dict:
    if not current_bytes or not previous_bytes:
        raise PredictionPipelineError("Both current and previous images are required.", 400)
    try:
        url_current = _image_data_url(current_bytes)
        url_previous = _image_data_url(previous_bytes)
    except Exception as exc:
        raise PredictionPipelineError(f"Could not read one of the images: {exc}", 400) from exc

    prompt = f"""You are an expert crop monitoring advisor. Two images are attached IN THIS ORDER:
1) FIRST IMAGE = MORE RECENT photo of the plant or field (current / today).
2) SECOND IMAGE = OLDER photo from about 1-3 days before the first.

Measured conditions (use as context, not as ground truth satellite validation):
- Relative humidity: {humidity_pct:.1f}% (0-100)
- Air temperature: {temperature_c:.1f} C
- NDVI (canopy vigor index): {ndvi:.3f} (typical range -1 to 1; higher often means greener/denser canopy)

Compare the images for visible stress: leaf spots, color shift, wilting, canopy thinning, spread of damage.
Relate humidity (sustained high humidity can favor some fungal issues), temperature extremes, and NDVI meaning
(lower NDVI may suggest canopy decline — combined with visuals).

Respond with ONLY valid JSON (no markdown code fences) using exactly these keys:
{{
  "risk_level": "low" OR "moderate" OR "high",
  "disease_outbreak_likely": true or false,
  "summary": "2-4 clear sentences for the farmer",
  "visual_changes": "short text: what changed between the older and newer photo",
  "env_interpretation": "short text: how humidity, temperature, and NDVI relate to the visible risk",
  "precautions": [ "at least two short actionable precautions" ],
  "watch_signs": [ "at least two signs to monitor in the next days" ]
}}
If images are unclear or not plants, say so in summary, set risk_level to moderate, disease_outbreak_likely to false."""

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": url_current}},
                {"type": "image_url", "image_url": {"url": url_previous}},
            ],
        }
    ]
    content, _m = _chat_with_model_fallback(Config.groq_vision_model_candidates(), messages, json_mode=True)
    data = parse_json_response(content, source="Groq")
    if not isinstance(data, dict):
        raise PredictionPipelineError("Groq returned invalid prognosis structure.", 502)
    return _normalize_prognosis_payload(data)
