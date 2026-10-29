"use client";

/**
 * Auth API client + types.
 *
 * Strategy: httpOnly cookies set by the backend. The frontend never touches
 * the token directly — the browser handles storage automatically.
 *
 * Every fetch() that hits an authenticated endpoint MUST include
 * `credentials: "include"`, or the cookie won't be sent cross-origin.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface User {
  id: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
  display_name: string | null;
  role: string;
}

export class AuthError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "AuthError";
  }
}

/**
 * Log in. On success, the backend sets the genai_auth cookie automatically.
 * Throws AuthError on failure (e.g., bad credentials).
 */
export async function login(email: string, password: string): Promise<void> {
  // fastapi-users login endpoint uses OAuth2 password flow:
  // form-urlencoded body with `username` and `password` fields.
  const formData = new URLSearchParams();
  formData.append("username", email);
  formData.append("password", password);

  const res = await fetch(`${API_URL}/auth/cookie/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: formData.toString(),
    credentials: "include",
  });

  if (!res.ok) {
    let detail = "Login failed";
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch {
      /* noop */
    }
    throw new AuthError(detail, res.status);
  }
  // 204 No Content on success — cookie is set, nothing to read from body
}

/**
 * Register a new user. Does NOT log them in automatically — they need to
 * follow up with login(). (We could auto-login but separating the two
 * concerns is cleaner.)
 */
export async function register(
  email: string,
  password: string,
  displayName?: string,
): Promise<User> {
  const res = await fetch(`${API_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password,
      display_name: displayName || null,
    }),
  });

  if (!res.ok) {
    let detail = "Registration failed";
    try {
      const j = await res.json();
      // Password-policy errors arrive as {code, reason}; others as a string.
      if (typeof j.detail === "string") detail = j.detail;
      else if (typeof j.detail?.reason === "string") detail = j.detail.reason;
    } catch {
      /* noop */
    }
    throw new AuthError(detail, res.status);
  }
  return res.json();
}

/**
 * Log out. Backend clears the cookie.
 */
export async function logout(): Promise<void> {
  await fetch(`${API_URL}/auth/cookie/logout`, {
    method: "POST",
    credentials: "include",
  }).catch(() => {
    /* logout is best-effort; even if it fails we clear local state */
  });
}

/**
 * Get the current user (if any). Returns null if not authenticated.
 * Used on app mount to determine login state.
 */
export async function fetchCurrentUser(): Promise<User | null> {
  try {
    const res = await fetch(`${API_URL}/users/me`, {
      credentials: "include",
    });
    if (res.status === 401) return null;
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}