import type { NextConfig } from "next";

const apiOrigin = process.env.NEXT_PUBLIC_API_BASE_URL
  ? new URL(process.env.NEXT_PUBLIC_API_BASE_URL).origin
  : "http://localhost:8000";
const oidcOrigin = process.env.NEXT_PUBLIC_OIDC_AUTHORITY
  ? new URL(process.env.NEXT_PUBLIC_OIDC_AUTHORITY).origin
  : "";
const production = process.env.NODE_ENV === "production";
const contentSecurityPolicy = (frameAncestors: "'none'" | "'self'") =>
  [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline'${production ? "" : " 'unsafe-eval'"}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src 'self' ${apiOrigin}${oidcOrigin ? ` ${oidcOrigin}` : ""}`,
    `frame-src 'self'${oidcOrigin ? ` ${oidcOrigin}` : ""}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    `frame-ancestors ${frameAncestors}`,
  ].join("; ");

const nextConfig: NextConfig = {
  // Let the alternate loopback origin load enough client code to perform the
  // canonical localhost redirect before OIDC state is created.
  allowedDevOrigins: ["127.0.0.1"],
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    const securityHeaders = [
      { key: "Content-Security-Policy", value: contentSecurityPolicy("'none'") },
      { key: "Referrer-Policy", value: "no-referrer" },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
    ];
    if (production) {
      securityHeaders.push({
        key: "Strict-Transport-Security",
        value: "max-age=63072000; includeSubDomains; preload",
      });
    }
    return [
      { source: "/:path*", headers: securityHeaders },
      {
        // oidc-client-ts renders this route in a hidden same-origin iframe.
        // Keep every other route non-frameable while allowing silent renewal.
        source: "/auth/silent-callback",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy("'self'") },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
        ],
      },
    ];
  },
};

export default nextConfig;
