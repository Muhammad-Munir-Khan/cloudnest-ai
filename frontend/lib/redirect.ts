/**
 * Validate a post-login redirect target taken from the URL (?next=...).
 *
 * Only same-origin paths are allowed. The value is resolved with the URL
 * parser against a placeholder origin, so tricks a simple startsWith("/")
 * check would miss ("//evil.com", "/\evil.com", "/\t/evil.com") are caught:
 * browsers normalise all of them to another origin.
 */
const PLACEHOLDER_ORIGIN = "http://same-origin.invalid";

export function safeRedirectPath(raw: string | null | undefined, fallback = "/chat"): string {
  if (!raw || !raw.startsWith("/")) return fallback;
  try {
    const url = new URL(raw, PLACEHOLDER_ORIGIN);
    if (url.origin !== PLACEHOLDER_ORIGIN) return fallback;
    return url.pathname + url.search + url.hash;
  } catch {
    return fallback;
  }
}
