export type User = {
  id: string;
  name: string;
  email: string;
  role: string;
};

export type ApiHealth = {
  message: string;
};

export type FloodPrediction = {
  city: string;
  state: string;
  coverage: "trained" | "exploratory";
  risk: number;
  level: "low" | "moderate" | "high" | "critical";
  forecastRain7mm: number;
  forecastRiverRatio: number;
  lat: number;
  lng: number;
};

export type FloodPredictionResponse = {
  model: string;
  scope: string;
  generatedAt: string;
  horizonDays: number;
  predictions: FloodPrediction[];
  warning: string;
  unavailableDistricts: number;
};

export type RescueChatResponse = {
  answer: string;
  provider: string;
  model: string;
  grounded: boolean;
};

export class ApiError extends Error {
  readonly status: number;

  constructor(
    message: string,
    status: number,
  ) {
    super(message);
    this.status = status;
  }
}

const REQUEST_TIMEOUT_MS = 10000;

async function request<T>(path: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const requestUrl = path.startsWith("http") ? path : `/api${path}`;
    const response = await fetch(requestUrl, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...init?.headers },
      ...init,
      signal: controller.signal,
    });
    if (!response.ok) {
      const body = await response.text();
      throw new ApiError(body || response.statusText, response.status);
    }
    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("The server took too long to respond.", 408);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

export const getStatus = () => request<ApiHealth>("/");
export const getFloodPredictions = () =>
  request<FloodPredictionResponse>(
    `${appConfig.backendUrl}/api/predictions/flood`,
    undefined,
    60000,
  );
export const login = (email: string, password: string) =>
  request<User>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
export const getCurrentUser = () => request<User>("/auth/me");
export const askRescueCopilot = (question: string, zones: unknown[]) =>
  request<RescueChatResponse>(
    `${appConfig.backendUrl}/api/rescue/chat`,
    { method: "POST", body: JSON.stringify({ question, zones }) },
    150000,
  );
import { appConfig } from "./config";
