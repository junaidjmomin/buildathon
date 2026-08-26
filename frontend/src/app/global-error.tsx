"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function GlobalError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error("sl3dge global boundary caught an error", {
      digest: error.digest ?? "client-error",
    });
  }, [error]);

  return (
    <html lang="en">
      <head>
        <title>sl3dge · Recovery required</title>
      </head>
      <body style={styles.body}>
        <main style={styles.main}>
          <section aria-labelledby="global-error-title" role="alert" style={styles.panel}>
            <div aria-hidden="true" style={styles.icon}>
              !
            </div>
            <p style={styles.eyebrow}>Safe recovery mode</p>
            <h1 id="global-error-title" style={styles.heading}>
              sl3dge could not start
            </h1>
            <p style={styles.copy}>
              The application shell encountered an unexpected error. No financial decision was changed.
            </p>
            {error.digest ? <p style={styles.reference}>Reference: {error.digest}</p> : null}
            <div style={styles.actions}>
              <button onClick={() => retry()} style={styles.primaryButton} type="button">
                Try again
              </button>
              <Link href="/" style={styles.secondaryButton}>
                Control overview
              </Link>
            </div>
          </section>
        </main>
      </body>
    </html>
  );
}

const styles = {
  body: {
    background: "#f3f4ef",
    color: "#17211d",
    fontFamily: "Arial, sans-serif",
    margin: 0,
  },
  main: {
    alignItems: "center",
    display: "flex",
    justifyContent: "center",
    minHeight: "100vh",
    padding: "32px 20px",
  },
  panel: {
    background: "#ffffff",
    border: "1px solid #dde1d9",
    borderRadius: "16px",
    boxShadow: "0 10px 35px rgba(17, 42, 43, 0.08)",
    boxSizing: "border-box" as const,
    maxWidth: "560px",
    padding: "40px",
    textAlign: "center" as const,
    width: "100%",
  },
  icon: {
    alignItems: "center",
    background: "#fff0e8",
    borderRadius: "12px",
    color: "#bd4e24",
    display: "flex",
    fontSize: "20px",
    fontWeight: 700,
    height: "48px",
    justifyContent: "center",
    margin: "0 auto",
    width: "48px",
  },
  eyebrow: {
    color: "#bd522a",
    fontSize: "10px",
    fontWeight: 700,
    letterSpacing: "0.15em",
    margin: "20px 0 0",
    textTransform: "uppercase" as const,
  },
  heading: {
    fontSize: "26px",
    letterSpacing: "-0.035em",
    margin: "8px 0 0",
  },
  copy: {
    color: "#66716b",
    fontSize: "14px",
    lineHeight: 1.6,
    margin: "12px auto 0",
    maxWidth: "420px",
  },
  reference: {
    color: "#7b857f",
    fontFamily: "monospace",
    fontSize: "10px",
    margin: "16px 0 0",
  },
  actions: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: "12px",
    justifyContent: "center",
    marginTop: "28px",
  },
  primaryButton: {
    background: "#112a2b",
    border: "1px solid #112a2b",
    borderRadius: "8px",
    color: "#ffffff",
    cursor: "pointer",
    fontSize: "14px",
    fontWeight: 600,
    padding: "10px 16px",
  },
  secondaryButton: {
    background: "#ffffff",
    border: "1px solid #cfd9d1",
    borderRadius: "8px",
    color: "#24332c",
    fontSize: "14px",
    fontWeight: 600,
    padding: "10px 16px",
    textDecoration: "none",
  },
};
