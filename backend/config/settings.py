"""Load environment — never commit real API keys; use .env locally only."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent.parent
load_dotenv(_BASE / ".env", override=True)

# Values often mistaken for Cloudinary cloud_name (e.g. MYSQL_USER=root).
# Legacy Gemini 1.x names are not used as defaults; they are coerced to the default 2.5 Flash id.
_GEMINI_DEPRECATED_MODEL_ALIASES = frozenset(
    {
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro",
        "gemini-1.5-pro-latest",
        "gemini-pro",
        "gemini-pro-vision",
        "gemini-1.0-pro",
        "gemini-1.0-pro-vision",
        "gemini-2.0-flash",
    }
)
# Single default when GEMINI_MODEL is unset in backend/.env (Google AI Gemini API model id).
# gemini-2.5-flash was retired for new users; use a supported 3.x model instead.
_DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"

_DISALLOWED_CLOUDINARY_NAMES = frozenset(
    {
        "root",
        "localhost",
        "admin",
        "mysql",
        "user",
        "test",
        "none",
        "null",
        "your_cloud_name",
        "changeme",
    }
)


class ConfigMeta(type):
    """Metaclass: allow legacy UPPER_CASE env-style attributes on Config."""

    _LEGACY_ATTR_TO_METHOD = {
        "CLOUDINARY_CLOUD_NAME": "cloudinary_cloud_name",
        "CLOUDINARY_API_KEY": "cloudinary_api_key",
        "CLOUDINARY_API_SECRET": "cloudinary_api_secret",
        "HF_API_KEY": "hf_api_key",
        "HF_MODEL_ID": "hf_model_id",
        "HF_INFERENCE_MODELS_BASE": "hf_inference_models_base",
        "GEMINI_API_KEY": "gemini_api_key",
        "MYSQL_HOST": "mysql_host",
        "MYSQL_PORT": "mysql_port",
        "MYSQL_USER": "mysql_user",
        "MYSQL_PASSWORD": "mysql_password",
        "MYSQL_DATABASE": "mysql_database",
        # Common typo / alternate casing seen in stack traces
        "CloudinaryCloudName": "cloudinary_cloud_name",
        "CLOUDINARYCLOUDNAME": "cloudinary_cloud_name",
    }

    def __getattr__(cls, name: str):
        method_name = cls._LEGACY_ATTR_TO_METHOD.get(name)
        if method_name:
            return getattr(cls, method_name)()
        raise AttributeError(f"type object '{cls.__name__}' has no attribute {name!r}")


class Config(metaclass=ConfigMeta):
    """Read env at access time so values stay in sync with load_dotenv order."""

    @staticmethod
    def _env(key: str, default: str = "") -> str:
        raw = os.getenv(key, default)
        if raw is None:
            return default
        return str(raw).strip()

    @classmethod
    def cloudinary_cloud_name(cls) -> str:
        return cls._env("CLOUDINARY_CLOUD_NAME")

    @classmethod
    def cloudinary_api_key(cls) -> str:
        return cls._env("CLOUDINARY_API_KEY")

    @classmethod
    def cloudinary_api_secret(cls) -> str:
        return cls._env("CLOUDINARY_API_SECRET")

    @classmethod
    def cloudinary_upload_preset(cls) -> str:
        """Unsigned upload preset name (browser upload). Not a secret."""
        return cls._env("CLOUDINARY_UPLOAD_PRESET")

    @classmethod
    def cloudinary_credentials_present(cls) -> bool:
        return bool(cls.cloudinary_cloud_name() and cls.cloudinary_api_key() and cls.cloudinary_api_secret())

    @classmethod
    def cloudinary_cloud_name_plausible(cls) -> bool:
        """Reject empty, obvious SQL placeholders, and invalid shapes before calling Cloudinary."""
        raw = cls.cloudinary_cloud_name().strip()
        if len(raw) < 3:
            return False
        lower = raw.lower()
        if lower in _DISALLOWED_CLOUDINARY_NAMES:
            return False
        # Typical dashboard cloud names: alphanumeric, hyphen, underscore
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,128}", raw):
            return False
        return True

    @classmethod
    def hf_api_key(cls) -> str:
        """HF Hub accepts several env names; router inference uses the same bearer token."""
        return cls._env("HF_API_KEY") or cls._env("HUGGINGFACEHUB_API_TOKEN") or cls._env("HF_TOKEN")

    @classmethod
    def hf_model_id(cls) -> str:
        return cls._env("HF_MODEL_ID", "linkanjarad/mobilenet_v2_rai_CropDisease")

    @classmethod
    def hf_inference_models_base(cls) -> str:
        """
        Base URL path for image-classification POST.
        Legacy https://api-inference.huggingface.co returns HTTP 410; use the router instead.
        """
        return cls._env(
            "HF_INFERENCE_MODELS_BASE",
            "https://router.huggingface.co/hf-inference/models",
        ).rstrip("/")

    @classmethod
    def hf_classification_post_url(cls) -> str:
        model = cls.hf_model_id().strip().strip("/")
        return f"{cls.hf_inference_models_base()}/{model}"

    @classmethod
    def gemini_api_key(cls) -> str:
        return cls._env("GEMINI_API_KEY") or cls._env("GOOGLE_API_KEY")

    @classmethod
    def backend_dotenv_path(cls) -> Path:
        """Path to backend/.env loaded at import (see module-level load_dotenv)."""
        return _BASE / ".env"

    @classmethod
    def backend_dotenv_status(cls) -> dict[str, object]:
        """Runtime evidence that backend/.env was found (not the values)."""
        p = cls.backend_dotenv_path().resolve()
        exists = p.is_file()
        return {
            "backend_dotenv_path": str(p),
            "backend_dotenv_exists": exists,
            # Raw env lines are read by load_dotenv; these are os.environ after load:
            "gemini_model_env_set": bool(os.getenv("GEMINI_MODEL")),
            "gemini_model_env_value_preview": (os.getenv("GEMINI_MODEL") or "")[:80],
        }

    @classmethod
    def _coerce_gemini_model_token(cls, raw: str) -> str:
        """Strip models/ prefix; map legacy 1.x / bundled 2.0 id to default 2.5 Flash."""
        s = (raw or "").strip()
        if not s:
            return ""
        if s.lower().startswith("models/"):
            s = s[7:]
        key = s.lower()
        if key in _GEMINI_DEPRECATED_MODEL_ALIASES:
            logger.warning(
                "GEMINI model id %r is legacy/unsupported in this app — coercing to %r. "
                "Set GEMINI_MODEL explicitly in backend/.env to your target Gemini 2.5 id.",
                raw,
                _DEFAULT_GEMINI_MODEL,
            )
            return _DEFAULT_GEMINI_MODEL
        return s

    @classmethod
    def gemini_model_id(cls) -> str:
        """
        Primary model id: GEMINI_MODEL from backend/.env, else gemini-2.5-flash.
        No other file overrides this.
        """
        raw = cls._env("GEMINI_MODEL", "").strip()
        if not raw:
            return _DEFAULT_GEMINI_MODEL
        return cls._coerce_gemini_model_token(raw)

    @classmethod
    def gemini_model_candidates(cls) -> list[str]:
        """
        Ordered, deduped list: primary gemini_model_id(), then optional GEMINI_MODEL_FALLBACKS only.
        No hardcoded Gemini 1.5 / 2.0 fallbacks — env must list any extra models.
        """
        ordered: list[str] = []
        seen: set[str] = set()
        primary = cls.gemini_model_id()
        for name in [primary, *cls._gemini_fallback_tokens()]:
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered

    @classmethod
    def _gemini_fallback_tokens(cls) -> list[str]:
        raw = cls._env("GEMINI_MODEL_FALLBACKS", "").strip()
        if not raw:
            return []
        out: list[str] = []
        for part in raw.split(","):
            tok = cls._coerce_gemini_model_token(part.strip())
            if tok:
                out.append(tok)
        return out

    @classmethod
    def gemini_client_options(cls):
        """
        Optional google.api_core ClientOptions, e.g. custom API endpoint.
        Set GEMINI_API_ENDPOINT=https://generativelanguage.googleapis.com if needed.
        """
        endpoint = cls._env("GEMINI_API_ENDPOINT", "").strip()
        if not endpoint:
            return None
        from google.api_core.client_options import ClientOptions

        return ClientOptions(api_endpoint=endpoint)

    @classmethod
    def mysql_host(cls) -> str:
        return cls._env("MYSQL_HOST", "127.0.0.1")

    @classmethod
    def mysql_port(cls) -> int:
        return int(cls._env("MYSQL_PORT", "3306"))

    @classmethod
    def mysql_user(cls) -> str:
        return cls._env("MYSQL_USER", "root")

    @classmethod
    def mysql_password(cls) -> str:
        return cls._env("MYSQL_PASSWORD")

    @classmethod
    def mysql_database(cls) -> str:
        for key in ("MYSQL_DATABASE", "MYSQL_DB"):
            v = cls._env(key)
            if v:
                return v
        return "agrosense_auth"

    @classmethod
    def cloudinary_ready(cls) -> bool:
        return cls.cloudinary_credentials_present() and cls.cloudinary_cloud_name_plausible()

    @classmethod
    def hf_ready(cls) -> bool:
        return bool(cls.hf_api_key())

    @classmethod
    def gemini_ready(cls) -> bool:
        return bool(cls.gemini_api_key())
