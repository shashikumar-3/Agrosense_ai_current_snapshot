import { useCallback, useState } from "react";
import { getApiBase } from "@/lib/api-base";

/** Matches backend HF_UNAVAILABLE — stable UX when Hugging Face / network fails. */
const HF_SERVICE_UX_MESSAGE =
  "AI analysis service is temporarily unavailable. Please try again.";

export interface InsightBlock {
  causes?: string;
  treatment?: string;
  prevention?: string;
  fertilizers?: string;
  recovery_time?: string;
  validation_note?: string;
}

export interface PredictionResult {
  disease: string;
  confidence: number;
  treatment: string;
  image_url?: string;
  severity?: string;
  insights?: InsightBlock;
  trend?: string;
  comparison_analysis?: string;
  plant_id?: string;
}

export interface PrognosisInputs {
  humidity: number;
  temperature: number;
  ndvi: number;
  plant_id: string;
}

export interface PrognosisResult {
  risk_level: "low" | "moderate" | "high";
  disease_outbreak_likely: boolean;
  summary: string;
  visual_changes: string;
  env_interpretation: string;
  precautions: string[];
  watch_signs: string[];
  inputs: PrognosisInputs;
}

export async function submitPrognosis(params: {
  imageCurrent: File;
  imagePrevious: File;
  humidity: number;
  temperature: number;
  ndvi: number;
  plantId?: string;
}): Promise<PrognosisResult> {
  const fd = new FormData();
  fd.append("image_current", params.imageCurrent, params.imageCurrent.name);
  fd.append("image_previous", params.imagePrevious, params.imagePrevious.name);
  fd.append("humidity", String(params.humidity));
  fd.append("temperature", String(params.temperature));
  fd.append("ndvi", String(params.ndvi));
  if (params.plantId?.trim()) fd.append("plant_id", params.plantId.trim());

  const res = await fetch(`${getApiBase()}/prognosis`, { method: "POST", body: fd });
  const rawText = await res.text();
  let data = {} as { error?: string; error_code?: string; details?: string } & Partial<PrognosisResult>;
  try {
    if (rawText) data = JSON.parse(rawText) as typeof data;
  } catch {
    throw new Error("Invalid server response. Please try again.");
  }
  if (!res.ok) {
    const code = typeof data.error_code === "string" ? data.error_code : "";
    const base = typeof data.error === "string" ? data.error : "Prognosis failed.";
    if (code === "GEMINI_AUTH")
      throw new Error("Gemini is not configured. Set GEMINI_API_KEY in backend/.env.");
    if (code === "GEMINI_MODEL") throw new Error(base);
    throw new Error(base);
  }

  const risk = data.risk_level;
  if (risk !== "low" && risk !== "moderate" && risk !== "high") {
    (data as PrognosisResult).risk_level = "moderate";
  }
  return data as PrognosisResult;
}

export function usePredict() {
  const [result, setResult] = useState<PredictionResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const predict = async (file: File, plantId?: string) => {
    setIsLoading(true);
    setError(null);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("image", file);
      if (plantId?.trim()) formData.append("plant_id", plantId.trim());

      const res = await fetch(`${getApiBase()}/predict`, {
        method: "POST",
        body: formData,
      });
      const rawText = await res.text();
      let data = {} as {
        error?: string;
        error_code?: string;
      } & PredictionResult;
      try {
        if (rawText) data = JSON.parse(rawText) as typeof data;
      } catch {
        if (!res.ok) throw new Error(HF_SERVICE_UX_MESSAGE);
        throw new Error("Invalid server response. Please try again.");
      }
      if (!res.ok) {
        const code = typeof data.error_code === "string" ? data.error_code : "";
        if (import.meta.env.DEV && code === "CLOUDINARY_CONFIG") {
          console.warn("[Agrosense] Check backend/.env: CLOUDINARY_CLOUD_NAME, API_KEY, API_SECRET.");
        }
        if (import.meta.env.DEV && code === "HF_UNAVAILABLE") {
          console.warn("[Agrosense] Hugging Face inference failed — see backend logs for status/body.");
        }
        if (import.meta.env.DEV && code === "HF_AUTH") {
          console.warn("[Agrosense] Hugging Face token/permisson or endpoint issue — check backend error text.");
        }
        if (import.meta.env.DEV && (code === "GEMINI_MODEL" || code === "GEMINI_AUTH")) {
          console.warn("[Agrosense] Gemini issue — call GET /health/gemini and verify GEMINI_MODEL / GEMINI_API_KEY.");
        }
        const serverMsg = typeof data.error === "string" ? data.error : "Prediction failed";
        const msg =
          code === "CLOUDINARY_CONFIG"
            ? "Image upload configuration is missing. Check Cloudinary env setup."
            : code === "HF_UNAVAILABLE"
              ? HF_SERVICE_UX_MESSAGE
              : code === "GEMINI_AUTH"
                ? "Google Gemini API key is invalid or not allowed. Check GEMINI_API_KEY in backend/.env."
                : code === "GEMINI_MODEL"
                  ? "Gemini model failed for this API. Open GET /health/gemini, set GEMINI_MODEL in backend/.env to a id from models_preview (e.g. gemini-2.5-flash), and check the response details field."
                  : serverMsg;
        throw new Error(msg);
      }
      setResult(data);
      return data;
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : HF_SERVICE_UX_MESSAGE;
      setError(message);
      throw err instanceof Error ? err : new Error(message);
    } finally {
      setIsLoading(false);
    }
  };

  const reset = () => {
    setResult(null);
    setError(null);
  };

  return { predict, result, isLoading, error, reset };
}

export interface HistoryItem {
  id: string;
  disease: string;
  confidence: number;
  image_url: string;
  date: string;
  treatment?: string;
}

export function useHistory() {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`${getApiBase()}/history`);
      if (!res.ok) throw new Error("Failed to fetch history");
      const data = await res.json();
      setHistory(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const clearHistory = useCallback(async () => {
    setIsClearing(true);
    setError(null);
    try {
      const res = await fetch(`${getApiBase()}/history`, { method: "DELETE" });
      if (!res.ok) throw new Error("Failed to clear history");
      setHistory([]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      throw err;
    } finally {
      setIsClearing(false);
    }
  }, []);

  return { history, fetchHistory, clearHistory, isLoading, isClearing, error };
}

export interface CorrelationPoint {
  date: string;
  temperature: number;
  humidity: number;
  risk: number;
}

export interface AgriDataPoint {
  date: string;
  temperature: number;
  humidity: number;
  soil_moisture: number;
  ndvi: number;
  risk: number;
}

export interface AgriDataResponse {
  location: {
    latitude: number;
    longitude: number;
    place: string;
  };
  current: {
    temperature: number;
    humidity: number;
    soil_moisture: number;
    ndvi: number;
    risk: number;
  };
  history: AgriDataPoint[];
  correlation: CorrelationPoint[];
}

/** Live Open-Meteo conditions at lat/lon (same source as Insights “current”). */
export interface WeatherCurrentResponse {
  location: { latitude: number; longitude: number; place: string };
  temperature: number;
  humidity: number;
  soil_moisture: number;
  ndvi: number;
  risk: number;
}

export async function fetchWeatherCurrent(latitude: number, longitude: number): Promise<WeatherCurrentResponse> {
  const res = await fetch(`${getApiBase()}/weather/current?lat=${latitude}&lon=${longitude}`);
  let payload: Record<string, unknown> = {};
  try {
    payload = (await res.json()) as Record<string, unknown>;
  } catch {
    if (!res.ok) throw new Error(`Weather request failed (${res.status}).`);
  }
  if (!res.ok) {
    const msg = typeof payload.error === "string" ? payload.error : `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return payload as unknown as WeatherCurrentResponse;
}

export function useAgriData() {
  const [data, setData] = useState<AgriDataResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAgriData = useCallback(async (latitude: number, longitude: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`${getApiBase()}/data?lat=${latitude}&lon=${longitude}`);
      let payload: Record<string, unknown> = {};
      try {
        payload = (await res.json()) as Record<string, unknown>;
      } catch {
        if (!res.ok) throw new Error(`Weather request failed (${res.status}). Is the backend running on port 5000?`);
      }
      if (!res.ok) {
        const msg = typeof payload.error === "string" ? payload.error : `Request failed (${res.status})`;
        throw new Error(msg);
      }
      setData(payload);
      return payload as AgriDataResponse;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { data, fetchAgriData, isLoading, error };
}
