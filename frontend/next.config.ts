import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";

// The browser calls the API directly, so its origin must be allowed in
// connect-src. NEXT_PUBLIC_API_URL is a build-time value (also inlined into
// the client bundle).
function apiOrigin(): string {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").origin;
  } catch {
    return "http://localhost:8000";
  }
}

const contentSecurityPolicy = [
  "default-src 'self'",
  // Next.js injects inline bootstrap scripts and app/layout.tsx has an inline
  // theme script, so 'unsafe-inline' is required without nonce-based CSP.
  // Dev mode also needs eval for fast refresh.
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "media-src 'self' blob:", // TTS playback uses blob: object URLs
  `connect-src 'self' ${apiOrigin()}${isDev ? " ws: wss:" : ""}`,
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // The mic button needs microphone access on this origin.
  { key: "Permissions-Policy", value: "camera=(), geolocation=(), microphone=(self)" },
  // Ignored by browsers over plain HTTP; effective once served over HTTPS.
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  eslint: {
    ignoreDuringBuilds: true,
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
