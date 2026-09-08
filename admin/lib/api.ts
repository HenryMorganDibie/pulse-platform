// Talks to the pulse-platform /admin/* API. The admin secret is entered at
// runtime on /login and kept in sessionStorage only — never a build-time
// env var, never persisted beyond the browser tab. Every call attaches it
// as a Bearer token; a 401 clears it and bounces back to /login, since it
// means the secret is wrong, revoked, or was never set for this tab.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const SECRET_KEY = "pulse_admin_secret";

export function getAdminSecret(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(SECRET_KEY);
}

export function setAdminSecret(secret: string): void {
  sessionStorage.setItem(SECRET_KEY, secret);
}

export function clearAdminSecret(): void {
  sessionStorage.removeItem(SECRET_KEY);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const secret = getAdminSecret();

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${secret ?? ""}`,
      ...init?.headers,
    },
  });

  if (response.status === 401) {
    clearAdminSecret();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "Not authenticated");
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // response body wasn't JSON — fall back to statusText
    }
    throw new ApiError(response.status, detail);
  }

  return response.json() as Promise<T>;
}
