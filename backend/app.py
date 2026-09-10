from __future__ import annotations

import logging
import os
import re
import sqlite3
import secrets
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean

import pymysql
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Load .env before any local import that reads Config / os.environ.
load_dotenv(BASE_DIR / ".env", override=True)

from models.disease_predictions import list_predictions_for_plant
from services.prediction_service import run_crop_prediction
from utils.errors import PredictionPipelineError

DB_PATH = BASE_DIR / "agrosense.db"
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

app = Flask(__name__)
CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    supports_credentials=False,
    allow_headers=["Content-Type", "Authorization", "Accept"],
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    else:
        response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept"
    return response


def _log_gemini_startup() -> None:
    from config.settings import Config

    if Config.gemini_ready():
        app.logger.info("Gemini enabled (GEMINI_MODEL=%s)", Config.gemini_model_id())
    else:
        app.logger.warning(
            "Gemini: GEMINI_API_KEY / GOOGLE_API_KEY not set — disease insights and Hugging Face→Gemini "
            "fallback require a key in backend/.env. GET /health/gemini will report not configured."
        )


_log_gemini_startup()
_hf_log = logging.getLogger("services.huggingface_service")
if not _hf_log.handlers:
    _hf_handler = logging.StreamHandler(sys.stderr)
    _hf_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    _hf_log.addHandler(_hf_handler)
_hf_log.setLevel(logging.INFO)
_hf_log.propagate = False
MYSQL_READY = False
MYSQL_INIT_ERROR = ""


class DatabaseConnection(sqlite3.Connection):
    """Close SQLite connections after their transaction context completes."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, factory=DatabaseConnection)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                disease TEXT NOT NULL,
                confidence REAL NOT NULL,
                treatment TEXT NOT NULL,
                image_url TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS env_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                day TEXT NOT NULL,
                temperature REAL NOT NULL,
                humidity REAL NOT NULL,
                soil_moisture REAL NOT NULL,
                ndvi REAL NOT NULL,
                risk REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def init_sqlite_auth_tables() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )


def get_mysql_connection():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE") or os.getenv("MYSQL_DB", "agrosense_auth"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def _require_mysql_ready():
    if MYSQL_READY:
        return None
    message = MYSQL_INIT_ERROR or "MySQL is not configured. Set backend/.env and restart backend."
    return jsonify({"error": message}), 503


def init_mysql() -> None:
    db_name = os.getenv("MYSQL_DATABASE") or os.getenv("MYSQL_DB", "agrosense_auth")
    connection = pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
    finally:
        connection.close()

    with get_mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    name VARCHAR(150) NOT NULL,
                    email VARCHAR(191) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token VARCHAR(128) PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            from models.disease_predictions import ensure_disease_predictions_table

            ensure_disease_predictions_table(cursor)


def _get_bearer_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def validate_auth_input(name: str, email: str, password: str, *, is_signup: bool) -> str | None:
    """Return a user-safe validation message, or None when the input is acceptable."""
    if not email or not password or (is_signup and not name):
        return "name, email, and password are required" if is_signup else "email and password are required"
    if not EMAIL_PATTERN.fullmatch(email) or len(email) > 191:
        return "Enter a valid email address"
    if len(password) > 128:
        return "Password must be 128 characters or fewer"
    if is_signup:
        if not 2 <= len(name) <= 150:
            return "Name must be between 2 and 150 characters"
        if len(password) < 8:
            return "Password must be at least 8 characters"
        if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            return "Password must include at least one letter and one number"
    return None


@app.route("/auth/signup", methods=["POST"])
def auth_signup() -> tuple:
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    validation_error = validate_auth_input(name, email, password, is_signup=True)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    password_hash = generate_password_hash(password)

    if MYSQL_READY:
        try:
            with get_mysql_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
                        (name, email, password_hash),
                    )
                    user_id = cursor.lastrowid
                    token = secrets.token_hex(32)
                    cursor.execute("INSERT INTO sessions (token, user_id) VALUES (%s, %s)", (token, user_id))
                    return (
                        jsonify(
                            {
                                "token": token,
                                "user": {"id": str(user_id), "name": name, "email": email},
                            }
                        ),
                        201,
                    )
        except pymysql.err.IntegrityError:
            return jsonify({"error": "Email is already registered"}), 409
        except Exception as exc:
            return jsonify({"error": f"MySQL signup failed: {exc}"}), 500

    try:
        init_sqlite_auth_tables()
        with get_db() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                    (name, email, password_hash),
                )
                user_id = cursor.lastrowid
            except sqlite3.IntegrityError:
                return jsonify({"error": "Email is already registered"}), 409
            token = secrets.token_hex(32)
            conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))
            return (
                jsonify(
                    {
                        "token": token,
                        "user": {"id": str(user_id), "name": name, "email": email},
                    }
                ),
                201,
            )
    except Exception as exc:
        return jsonify({"error": f"SQLite signup failed: {exc}"}), 500


@app.route("/auth/login", methods=["POST"])
def auth_login() -> tuple:
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    validation_error = validate_auth_input("", email, password, is_signup=False)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    if MYSQL_READY:
        try:
            with get_mysql_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id, name, email, password_hash FROM users WHERE email = %s", (email,))
                    user = cursor.fetchone()
                    if not user or not check_password_hash(user["password_hash"], password):
                        return jsonify({"error": "Invalid credentials"}), 401
                    token = secrets.token_hex(32)
                    cursor.execute("INSERT INTO sessions (token, user_id) VALUES (%s, %s)", (token, user["id"]))
                    return (
                        jsonify(
                            {
                                "token": token,
                                "user": {
                                    "id": str(user["id"]),
                                    "name": user["name"],
                                    "email": user["email"],
                                },
                            }
                        ),
                        200,
                    )
        except Exception as exc:
            return jsonify({"error": f"MySQL login failed: {exc}"}), 500

    try:
        init_sqlite_auth_tables()
        with get_db() as conn:
            user = conn.execute(
                "SELECT id, name, email, password_hash FROM users WHERE email = ?",
                (email,),
            ).fetchone()
            if not user or not check_password_hash(user["password_hash"], password):
                return jsonify({"error": "Invalid credentials"}), 401
            token = secrets.token_hex(32)
            conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user["id"]))
            return (
                jsonify(
                    {
                        "token": token,
                        "user": {
                            "id": str(user["id"]),
                            "name": user["name"],
                            "email": user["email"],
                        },
                    }
                ),
                200,
            )
    except Exception as exc:
        return jsonify({"error": f"SQLite login failed: {exc}"}), 500


@app.route("/auth/me", methods=["GET"])
def auth_me() -> tuple:
    token = _get_bearer_token()
    if not token:
        return jsonify({"error": "Missing auth token"}), 401

    if MYSQL_READY:
        try:
            with get_mysql_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT u.id, u.name, u.email
                        FROM sessions s
                        INNER JOIN users u ON u.id = s.user_id
                        WHERE s.token = %s
                        """,
                        (token,),
                    )
                    user = cursor.fetchone()
                    if not user:
                        return jsonify({"error": "Invalid session"}), 401
                    return (
                        jsonify({"user": {"id": str(user["id"]), "name": user["name"], "email": user["email"]}}),
                        200,
                    )
        except Exception as exc:
            return jsonify({"error": f"MySQL session check failed: {exc}"}), 500

    try:
        init_sqlite_auth_tables()
        with get_db() as conn:
            user = conn.execute(
                """
                SELECT u.id, u.name, u.email
                FROM sessions s
                INNER JOIN users u ON u.id = s.user_id
                WHERE s.token = ?
                """,
                (token,),
            ).fetchone()
            if not user:
                return jsonify({"error": "Invalid session"}), 401
            return (
                jsonify({"user": {"id": str(user["id"]), "name": user["name"], "email": user["email"]}}),
                200,
            )
    except Exception as exc:
        return jsonify({"error": f"SQLite session check failed: {exc}"}), 500


@app.route("/auth/logout", methods=["POST"])
def auth_logout() -> tuple:
    token = _get_bearer_token()
    if not token:
        return jsonify({"ok": True}), 200

    if MYSQL_READY:
        try:
            with get_mysql_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM sessions WHERE token = %s", (token,))
            return jsonify({"ok": True}), 200
        except Exception as exc:
            return jsonify({"error": f"MySQL logout failed: {exc}"}), 500

    try:
        init_sqlite_auth_tables()
        with get_db() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        return jsonify({"ok": True}), 200
    except Exception as exc:
        return jsonify({"error": f"SQLite logout failed: {exc}"}), 500


def calculate_risk(temperature: float, humidity: float, soil_moisture: float) -> float:
    temp_factor = min(max((temperature - 18.0) / 20.0, 0.0), 1.0)
    humidity_factor = min(max((humidity - 45.0) / 45.0, 0.0), 1.0)
    moisture_factor = min(max((soil_moisture - 20.0) / 45.0, 0.0), 1.0)
    risk = (temp_factor * 0.35) + (humidity_factor * 0.35) + (moisture_factor * 0.30)
    return round(risk * 100.0, 2)


def estimate_ndvi(temperature: float, humidity: float, soil_moisture: float) -> float:
    # Lightweight NDVI estimate when a satellite feed is unavailable.
    ndvi = 0.2 + (0.003 * humidity) + (0.004 * soil_moisture) - (0.002 * abs(temperature - 26.0))
    return round(max(0.15, min(ndvi, 0.92)), 3)


def reverse_geocode(lat: float, lon: float) -> str:
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "jsonv2"},
            timeout=8,
            headers={"User-Agent": "AgroSenseAI/1.0"},
        )
        response.raise_for_status()
        data = response.json()
        address = data.get("address", {})
        city = address.get("city") or address.get("town") or address.get("village") or ""
        state = address.get("state") or ""
        country = address.get("country") or ""
        parts = [p for p in [city, state, country] if p]
        return ", ".join(parts) if parts else data.get("display_name", "Unknown location")
    except Exception:
        return f"{lat:.4f}, {lon:.4f}"


def _soil_moisture_pct(
    i: int,
    moistures: list,
    humidity: float,
    temperature: float,
) -> float:
    """Open-Meteo often omits or nulls soil moisture for a grid cell — use a proxy when missing."""
    if i < len(moistures) and moistures[i] is not None:
        try:
            return float(moistures[i]) * 100.0
        except (TypeError, ValueError):
            pass
    proxy = humidity * 0.72 + max(0.0, 28.0 - temperature) * 0.35
    return round(min(92.0, max(6.0, proxy)), 2)


def _first_valid_hourly_index(temperatures: list, humidities: list, n: int) -> int:
    for j in range(min(n, len(temperatures), len(humidities))):
        if temperatures[j] is not None and humidities[j] is not None:
            return j
    return 0


def _hour_index_aligned_with_current(weather: dict) -> int:
    """Align soil/series with Open-Meteo `current.time` when present, else first valid hour."""
    hourly = weather.get("hourly") or {}
    times = hourly.get("time") or []
    temperatures = hourly.get("temperature_2m") or []
    humidities = hourly.get("relative_humidity_2m") or []
    if not times:
        return 0
    cur = weather.get("current") or {}
    ct = cur.get("time")
    if isinstance(ct, str):
        if ct in times:
            return times.index(ct)
        for i, t in enumerate(times):
            if len(ct) >= 13 and len(t) >= 13 and t[:13] == ct[:13]:
                return i
    return _first_valid_hourly_index(temperatures, humidities, len(times))


def _live_snapshot(weather: dict) -> dict[str, float]:
    """Use Open-Meteo `current` (true local now) for T/H; soil + NDVI/risk from same hour slot."""
    hourly = weather.get("hourly") or {}
    times = hourly.get("time") or []
    temperatures = hourly.get("temperature_2m") or []
    humidities = hourly.get("relative_humidity_2m") or []
    moistures = hourly.get("soil_moisture_0_to_1cm") or []

    cur = weather.get("current") or {}
    t_raw = cur.get("temperature_2m")
    h_raw = cur.get("relative_humidity_2m")

    temp_v: float | None = None
    hum_v: float | None = None
    if t_raw is not None and h_raw is not None:
        try:
            temp_v = float(t_raw)
            hum_v = float(h_raw)
        except (TypeError, ValueError):
            temp_v = None
            hum_v = None

    if temp_v is None or hum_v is None:
        idx = _first_valid_hourly_index(temperatures, humidities, len(times) if times else 0)
        if not times or idx >= len(temperatures) or idx >= len(humidities):
            raise ValueError("No hourly temperature/humidity in weather payload")
        temp_v = float(temperatures[idx])
        hum_v = float(humidities[idx])

    idx_soil = _hour_index_aligned_with_current(weather) if times else 0
    if times:
        idx_soil = min(max(0, idx_soil), len(times) - 1)
    soil_v = _soil_moisture_pct(idx_soil, moistures, hum_v, temp_v)
    ndvi = estimate_ndvi(temp_v, hum_v, soil_v)
    risk = calculate_risk(temp_v, hum_v, soil_v)
    return {
        "temperature": round(temp_v, 2),
        "humidity": round(hum_v, 2),
        "soil_moisture": soil_v,
        "ndvi": ndvi,
        "risk": risk,
    }


def fetch_weather(lat: float, lon: float) -> dict:
    url = "https://api.open-meteo.com/v1/forecast"
    headers = {"User-Agent": "AgroSenseAI/1.0 (https://github.com/agrosense)"}
    common = {
        "latitude": lat,
        "longitude": lon,
        "forecast_days": 7,
        "timezone": "auto",
        "current": "temperature_2m,relative_humidity_2m",
    }
    last_err = "Weather API returned no usable data"
    for hourly_vars in (
        "temperature_2m,relative_humidity_2m,soil_moisture_0_to_1cm",
        "temperature_2m,relative_humidity_2m",
    ):
        try:
            response = requests.get(
                url,
                params={**common, "hourly": hourly_vars},
                timeout=25,
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            last_err = str(exc)
            continue
        if payload.get("error"):
            last_err = str(payload.get("reason", payload.get("error")))
            continue
        hourly = payload.get("hourly") or {}
        if hourly.get("time"):
            return payload
    raise RuntimeError(last_err)


@app.route("/config/cloudinary", methods=["GET"])
def cloudinary_public_config():
    """Public values for browser unsigned upload (cloud name + preset are not API secrets)."""
    from config.settings import Config

    cloud = Config.cloudinary_cloud_name()
    preset = Config.cloudinary_upload_preset()
    if not cloud or not preset:
        return jsonify({"configured": False}), 200
    return (
        jsonify(
            {
                "configured": True,
                "cloud_name": cloud,
                "upload_preset": preset,
            }
        ),
        200,
    )


@app.route("/health/hf", methods=["GET"])
def health_hf():
    """Quick probe of Hugging Face router inference (tiny JPEG). Helps verify HF_API_KEY permissions."""
    import io

    from PIL import Image

    from config.settings import Config

    if not Config.hf_ready():
        return (
            jsonify(
                {
                    "configured": False,
                    "ok": False,
                    "hint": "Set HF_API_KEY, HUGGINGFACEHUB_API_TOKEN, or HF_TOKEN in backend/.env",
                }
            ),
            200,
        )

    im = Image.new("RGB", (32, 32), color=(20, 120, 40))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=75)
    raw = buf.getvalue()
    url = Config.hf_classification_post_url()
    try:
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {Config.hf_api_key()}",
                "Connection": "close",
            },
            data=raw,
            timeout=(20, 60),
        )
    except requests.RequestException as exc:
        return (
            jsonify(
                {
                    "configured": True,
                    "ok": False,
                    "url": url,
                    "error": str(exc)[:300],
                    "hint": "Network error talking to Hugging Face router.",
                }
            ),
            200,
        )

    preview = (r.text or "")[:800]
    payload = {
        "configured": True,
        "ok": r.status_code == 200,
        "status_code": r.status_code,
        "url": url,
        "body_preview": preview,
    }
    if r.status_code == 403:
        payload["hint"] = (
            "Token cannot call Inference Providers. "
            "Use a fine-grained token with \"Make calls to Inference Providers\" at "
            "https://huggingface.co/settings/tokens"
        )
    elif r.status_code == 401:
        payload["hint"] = "Invalid or expired token; create a new key and update backend/.env."
    elif r.status_code == 410:
        payload["hint"] = "Inference URL deprecated; set HF_INFERENCE_MODELS_BASE or update the app."
    return jsonify(payload), 200


@app.route("/health/gemini", methods=["GET"])
def health_gemini():
    """List Gemini models (generateContent) and run a tiny generate — verifies API key and model IDs."""
    from services.gemini_service import gemini_health_probe

    payload = gemini_health_probe()
    return jsonify(payload), 200


@app.route("/chat/gemini", methods=["POST"])
def chat_gemini():
    """Multimodal crop assistant: multipart ``image`` + form field ``message``."""
    from config.settings import Config
    from services.gemini_service import gemini_crop_chat

    if not Config.gemini_ready():
        return (
            jsonify(
                {
                    "error": "Gemini is not configured. Set GEMINI_API_KEY in backend/.env.",
                    "error_code": "GEMINI_AUTH",
                }
            ),
            503,
        )
    message = (request.form.get("message") or "").strip()
    image = request.files.get("image")
    if not message:
        return jsonify({"error": 'Form field "message" is required.'}), 400
    if not image or not getattr(image, "filename", None):
        return jsonify({"error": 'Multipart file field "image" is required.'}), 400
    image.stream.seek(0)
    raw = image.read()
    if not raw:
        return jsonify({"error": "Empty image file."}), 400
    try:
        reply = gemini_crop_chat(message, raw)
        return jsonify({"reply": reply}), 200
    except PredictionPipelineError as exc:
        payload: dict = {"error": exc.message}
        if exc.error_code:
            payload["error_code"] = exc.error_code
        if exc.details:
            payload["details"] = exc.details[:2000]
        return jsonify(payload), exc.status_code
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/prognosis", methods=["POST"])
def prognosis():
    """
    Two plant photos (current + older) plus humidity (%), temperature (°C), NDVI (-1..1).
    Returns risk assessment and precautions (Gemini). Does not require MySQL.
    """
    from config.settings import Config
    from services.prognosis_service import parse_observation_floats, run_prognosis

    if not Config.gemini_ready():
        cur = request.files.get("image_current")
        prev = request.files.get("image_previous")
        if not cur or not getattr(cur, "filename", None):
            return jsonify({"error": 'Multipart file field "image_current" is required.'}), 400
        if not prev or not getattr(prev, "filename", None):
            return jsonify({"error": 'Multipart file field "image_previous" is required.'}), 400
        plant_id = (request.form.get("plant_id") or "default").strip()[:64] or "default"
        try:
            h, t, n = parse_observation_floats(
                request.form.get("humidity", ""),
                request.form.get("temperature", ""),
                request.form.get("ndvi", ""),
            )
        except PredictionPipelineError as exc:
            return jsonify({"error": exc.message}), exc.status_code
        payload = run_prognosis(b"", b"", humidity=h, temperature=t, ndvi=n, plant_id=plant_id)
        return jsonify(payload), 200

    cur = request.files.get("image_current")
    prev = request.files.get("image_previous")
    if not cur or not getattr(cur, "filename", None):
        return jsonify({"error": 'Multipart file field "image_current" is required.'}), 400
    if not prev or not getattr(prev, "filename", None):
        return jsonify({"error": 'Multipart file field "image_previous" is required.'}), 400

    cur.stream.seek(0)
    prev.stream.seek(0)
    b_cur = cur.read()
    b_prev = prev.read()
    if not b_cur or not b_prev:
        return jsonify({"error": "One or both image files are empty."}), 400

    plant_id = (request.form.get("plant_id") or "default").strip()[:64] or "default"
    try:
        h, t, n = parse_observation_floats(
            request.form.get("humidity", ""),
            request.form.get("temperature", ""),
            request.form.get("ndvi", ""),
        )
    except PredictionPipelineError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    try:
        payload = run_prognosis(b_cur, b_prev, humidity=h, temperature=t, ndvi=n, plant_id=plant_id)
        return jsonify(payload), 200
    except PredictionPipelineError as exc:
        out: dict = {"error": exc.message}
        if exc.error_code:
            out["error_code"] = exc.error_code
        if exc.details:
            out["details"] = exc.details[:2000]
        return jsonify(out), exc.status_code
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/predict", methods=["POST"])
def predict() -> tuple:
    if not MYSQL_READY:
        return (
            jsonify(
                {
                    "error": MYSQL_INIT_ERROR
                    or "MySQL is required for the disease-detection pipeline. Check backend/.env and restart.",
                }
            ),
            503,
        )
    try:
        plant_id = request.form.get("plant_id") or "default"
        image = request.files.get("image")
        client_image_url = (request.form.get("image_url") or "").strip() or None
        result = run_crop_prediction(image, plant_id, client_image_url=client_image_url)
        treatment = (result.get("insights") or {}).get("treatment", "")
        created_at = datetime.utcnow().isoformat()
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO predictions (disease, confidence, treatment, image_url, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (result["disease"], result["confidence"], treatment, result.get("image_url", ""), created_at),
            )
        return (
            jsonify(
                {
                    "disease": result["disease"],
                    "confidence": result["confidence"],
                    "treatment": treatment,
                    "severity": result.get("severity"),
                    "insights": result.get("insights"),
                    "trend": result.get("trend"),
                    "comparison_analysis": result.get("comparison_analysis"),
                    "image_url": result.get("image_url", ""),
                    "plant_id": result.get("plant_id"),
                }
            ),
            200,
        )
    except PredictionPipelineError as exc:
        payload: dict = {"error": exc.message}
        if exc.error_code:
            payload["error_code"] = exc.error_code
        if exc.details:
            payload["details"] = exc.details[:4000]
        return jsonify(payload), exc.status_code
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _history_payload() -> tuple:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, disease, confidence, treatment, image_url, created_at
            FROM predictions
            ORDER BY datetime(created_at) DESC
            LIMIT 100
            """
        ).fetchall()

    payload = [
        {
            "id": str(row["id"]),
            "disease": row["disease"],
            "confidence": row["confidence"],
            "treatment": row["treatment"],
            "image_url": row["image_url"] or "",
            "date": row["created_at"],
        }
        for row in rows
    ]
    return jsonify(payload), 200


@app.route("/history", methods=["GET"])
def history() -> tuple:
    plant_id = request.args.get("plant_id")
    if plant_id and plant_id.strip():
        if not MYSQL_READY:
            return jsonify({"error": MYSQL_INIT_ERROR or "MySQL not configured"}), 503
        try:
            rows = list_predictions_for_plant(plant_id.strip(), limit=100)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        payload = []
        for r in rows:
            ins = r.get("insights") or {}
            payload.append(
                {
                    "id": str(r["id"]),
                    "disease": r["disease_name"],
                    "confidence": r["confidence"],
                    "treatment": ins.get("treatment", ""),
                    "image_url": r.get("image_url") or "",
                    "date": r["date"],
                    "severity": r.get("severity"),
                    "trend": r.get("trend"),
                    "insights": ins,
                    "comparison_analysis": r.get("comparison_analysis"),
                }
            )
        return jsonify(payload), 200
    return _history_payload()


@app.route("/history", methods=["DELETE"])
def clear_history() -> tuple:
    with get_db() as conn:
        conn.execute("DELETE FROM predictions")
    return jsonify({"ok": True}), 200


@app.route("/histroy", methods=["GET"])
def histroy_alias() -> tuple:
    # Alias retained to match requested route spelling.
    return _history_payload()


@app.route("/histroy", methods=["DELETE"])
def histroy_clear_alias() -> tuple:
    # Alias retained to match requested route spelling.
    return clear_history()


@app.route("/weather/current", methods=["GET"])
def weather_current() -> tuple:
    """Current air temperature & humidity at lat/lon (Open-Meteo `current`), plus derived soil/NDVI/risk."""
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon query params are required"}), 400
    try:
        weather = fetch_weather(lat, lon)
        live = _live_snapshot(weather)
        place = reverse_geocode(lat, lon)
    except Exception as exc:
        return jsonify({"error": f"Weather fetch failed: {exc}"}), 502
    return (
        jsonify(
            {
                "location": {"latitude": lat, "longitude": lon, "place": place},
                **live,
            }
        ),
        200,
    )


@app.route("/data", methods=["GET"])
def data() -> tuple:
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon query params are required"}), 400

    try:
        weather = fetch_weather(lat, lon)
    except Exception as exc:
        return jsonify({"error": f"Weather fetch failed: {exc}"}), 502

    hourly = weather.get("hourly") or {}
    times = hourly.get("time") or []
    temperatures = hourly.get("temperature_2m") or []
    humidities = hourly.get("relative_humidity_2m") or []
    moistures = hourly.get("soil_moisture_0_to_1cm") or []

    grouped: dict[str, dict[str, list[float]]] = {}
    for i, ts in enumerate(times):
        if i >= len(temperatures) or i >= len(humidities):
            continue
        t_raw, h_raw = temperatures[i], humidities[i]
        if t_raw is None or h_raw is None:
            continue
        temp_v = float(t_raw)
        hum_v = float(h_raw)
        soil_v = _soil_moisture_pct(i, moistures, hum_v, temp_v)
        day = ts.split("T")[0]
        grouped.setdefault(day, {"temperature": [], "humidity": [], "soil": []})
        grouped[day]["temperature"].append(temp_v)
        grouped[day]["humidity"].append(hum_v)
        grouped[day]["soil"].append(soil_v)

    history_rows = []
    for day in sorted(grouped.keys())[:7]:
        temp = round(mean(grouped[day]["temperature"]), 2)
        humidity = round(mean(grouped[day]["humidity"]), 2)
        soil = round(mean(grouped[day]["soil"]), 2)
        ndvi = estimate_ndvi(temp, humidity, soil)
        risk = calculate_risk(temp, humidity, soil)
        history_rows.append(
            {
                "date": day,
                "temperature": temp,
                "humidity": humidity,
                "soil_moisture": soil,
                "ndvi": ndvi,
                "risk": risk,
            }
        )

    if not history_rows:
        return jsonify({"error": "No weather data available"}), 502

    latest = history_rows[-1]
    place = reverse_geocode(lat, lon)

    try:
        live = _live_snapshot(weather)
    except Exception:
        live = {
            "temperature": latest["temperature"],
            "humidity": latest["humidity"],
            "soil_moisture": latest["soil_moisture"],
            "ndvi": latest["ndvi"],
            "risk": latest["risk"],
        }

    with get_db() as conn:
        now = datetime.utcnow().isoformat()
        conn.executemany(
            """
            INSERT INTO env_snapshots
            (latitude, longitude, day, temperature, humidity, soil_moisture, ndvi, risk, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    lat,
                    lon,
                    row["date"],
                    row["temperature"],
                    row["humidity"],
                    row["soil_moisture"],
                    row["ndvi"],
                    row["risk"],
                    now,
                )
                for row in history_rows
            ],
        )

    correlation = [
        {
            "date": row["date"],
            "temperature": row["temperature"],
            "humidity": row["humidity"],
            "risk": row["risk"],
        }
        for row in history_rows
    ]

    return (
        jsonify(
            {
                "location": {"latitude": lat, "longitude": lon, "place": place},
                "current": {
                    "temperature": live["temperature"],
                    "humidity": live["humidity"],
                    "soil_moisture": live["soil_moisture"],
                    "ndvi": live["ndvi"],
                    "risk": live["risk"],
                },
                "history": history_rows,
                "correlation": correlation,
            }
        ),
        200,
    )


if __name__ == "__main__":
    init_db()
    init_sqlite_auth_tables()
    try:
        init_mysql()
        MYSQL_READY = True
        MYSQL_INIT_ERROR = ""
    except Exception as exc:
        MYSQL_READY = False
        MYSQL_INIT_ERROR = (
            f"MySQL init failed: {exc}. Set MYSQL_* values in backend/.env with valid credentials."
        )
        print(MYSQL_INIT_ERROR)
        print("Falling back to SQLite auth storage for signup/login.")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
