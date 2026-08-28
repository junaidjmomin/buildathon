import type { ReactNode } from "react";

/** Shared visual primitives for the Control Room theme. Every page composes
 *  these instead of restyling panels, badges, and headers inline. */

export function Panel({
  children,
  className = "",
  as: As = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article";
}) {
  return <As className={`panel rounded-2xl ${className}`}>{children}</As>;
}

type Status = "PASS" | "VIOLATION" | "UNRESOLVED" | "PENDING" | "INFO" | "DRAFT";

const badgeStyles: Record<Status, string> = {
  PASS: "bg-[rgba(47,189,127,0.14)] text-[var(--evergreen)] border-[rgba(47,189,127,0.35)]",
  VIOLATION: "bg-[rgba(226,96,79,0.14)] text-[var(--crimson)] border-[rgba(226,96,79,0.35)]",
  UNRESOLVED: "bg-[rgba(227,179,65,0.14)] text-[var(--amber)] border-[rgba(227,179,65,0.35)]",
  PENDING: "bg-[rgba(227,179,65,0.14)] text-[var(--amber)] border-[rgba(227,179,65,0.35)]",
  INFO: "bg-[rgba(95,182,217,0.14)] text-[var(--sky)] border-[rgba(95,182,217,0.35)]",
  DRAFT: "bg-[rgba(147,163,155,0.14)] text-[var(--paper-dim)] border-[rgba(147,163,155,0.35)]",
};

export function Badge({ status, label }: { status: Status; label?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.08em] ${badgeStyles[status]}`}
    >
      {label ?? status}
    </span>
  );
}

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  back,
}: {
  eyebrow: ReactNode;
  title: string;
  subtitle?: ReactNode;
  back?: { href: string; label: string };
}) {
  return (
    <header className="mb-7">
      {back ? (
        <a
          href={back.href}
          className="mb-3 inline-flex items-center gap-1.5 text-xs font-medium text-[var(--paper-dim)] transition-colors hover:text-[var(--paper)]"
        >
          ← {back.label}
        </a>
      ) : null}
      <p className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--evergreen)]">
        {eyebrow}
      </p>
      <h1 className="text-3xl font-semibold tracking-[-0.035em] text-[var(--paper)]">{title}</h1>
      {subtitle ? <p className="mt-2 text-sm text-[var(--paper-dim)]">{subtitle}</p> : null}
    </header>
  );
}

export function StatCard({
  label,
  value,
  detail,
  tone = "default",
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: "default" | "pass" | "violation" | "warning";
}) {
  const toneClass = {
    default: "text-[var(--paper)]",
    pass: "text-[var(--evergreen)]",
    violation: "text-[var(--crimson)]",
    warning: "text-[var(--amber)]",
  }[tone];
  return (
    <div className="panel rounded-2xl p-5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--paper-faint)]">
        {label}
      </p>
      <p className={`number-tabular mt-2 font-mono text-2xl font-semibold ${toneClass}`}>{value}</p>
      {detail ? <p className="mt-1.5 text-xs leading-5 text-[var(--paper-dim)]">{detail}</p> : null}
    </div>
  );
}

export function MoneyText({
  amount,
  tone = "default",
  className = "",
}: {
  amount: string;
  tone?: "default" | "pass" | "violation" | "warning";
  className?: string;
}) {
  const toneClass = {
    default: "text-[var(--paper)]",
    pass: "text-[var(--evergreen)]",
    violation: "text-[var(--crimson)]",
    warning: "text-[var(--amber)]",
  }[tone];
  return (
    <span className={`number-tabular font-mono font-semibold ${toneClass} ${className}`}>
      {amount}
    </span>
  );
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel rounded-2xl p-8">
      <h2 className="text-sm font-semibold text-[var(--paper)]">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-[var(--paper-dim)]">{body}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  what,
  onRetry,
}: {
  what: string;
  onRetry: () => void;
}) {
  return (
    <div className="panel rounded-2xl p-8 text-sm text-[var(--crimson)]" role="alert">
      {what} could not be loaded.{" "}
      <button
        type="button"
        onClick={onRetry}
        className="font-semibold underline underline-offset-2"
      >
        Retry
      </button>
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={`skeleton ${className}`} />;
}

export function PageSkeleton({
  cards = 4,
  rows = 4,
}: {
  cards?: number;
  rows?: number;
}) {
  return (
    <div aria-busy="true" role="status">
      <span className="sr-only">Loading…</span>
      <Skeleton className="mb-2 h-3 w-36" />
      <Skeleton className="h-8 w-full max-w-md" />
      <Skeleton className="mt-3 h-4 w-full max-w-2xl" />
      <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: cards }).map((_, index) => (
          <Skeleton className="h-28" key={index} />
        ))}
      </div>
      <Skeleton className="mt-6 h-64 w-full" />
      <div className="mt-4 space-y-3">
        {Array.from({ length: rows }).map((_, index) => (
          <Skeleton className="h-12" key={index} />
        ))}
      </div>
    </div>
  );
}
