const API = "/api";

const BASE_HEADERS: Record<string, string> = {
  "ngrok-skip-browser-warning": "true",
};

export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = {
    ...BASE_HEADERS,
    ...(init.headers as Record<string, string> || {}),
  };
  return fetch(`${API}${path}`, { ...init, headers });
}

export default apiFetch;
