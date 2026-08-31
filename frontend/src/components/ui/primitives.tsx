import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

/** Shared, data-agnostic primitives for the sl3dge evidence workspace. */

export function Panel({
  children,
  className = "",
  as: As = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article";
}) {
  return <As className={`panel rounded-[10px] ${className}`}>{children}</As>;
}

type Status = "PASS" | "VIOLATION" | "UNRESOLVED" | "PENDING" | "INFO" | "DRAFT";

const badgeStyles: Record<Status, string> = {
  PASS: "border-[var(--evergreen-line)] bg-[var(--evergreen-soft)] text-[var(--evergreen-deep)]",
  VIOLATION: "border-[var(--crimson-line)] bg-[var(--crimson-soft)] text-[var(--crimson-deep)]",
  UNRESOLVED: "border-[var(--amber-line)] bg-[var(--amber-soft)] text-[var(--amber)]",
  PENDING: "border-[var(--amber-line)] bg-[var(--amber-soft)] text-[var(--amber)]",
  INFO: "border-[var(--sky-line)] bg-[var(--sky-soft)] text-[var(--sky)]",
  DRAFT: "border-[var(--line-strong)] bg-[var(--ink-700)] text-[var(--paper-dim)]",
};

export function Badge({ status, label }: { status: Status; label?: string }) {
  return (
    <span
      className={`inline-flex min-h-6 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.07em] ${badgeStyles[status]}`}
      data-status={status}
    >
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
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
    <header className="mb-7 max-w-4xl">
      {back ? (
        <Link
          className="mb-4 inline-flex min-h-8 items-center gap-1.5 rounded-sm text-xs font-medium text-[var(--paper-dim)] transition-colors hover:text-[var(--evergreen)]"
          href={back.href}
        >
          <ArrowLeft aria-hidden="true" size={14} />
          {back.label}
        </Link>
      ) : null}
      <p className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--evergreen)]">
        {eyebrow}
      </p>
      <h1 className="text-[clamp(1.75rem,3vw,2.25rem)] font-semibold leading-[1.15] tracking-[-0.035em] text-[var(--paper)]">
        {title}
      </h1>
      {subtitle ? (
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--paper-dim)]">{subtitle}</p>
      ) : null}
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
    <div className="panel rounded-[10px] p-5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.11em] text-[var(--paper-faint)]">
        {label}
      </p>
      <p
        className={`number-tabular mt-2 font-mono text-2xl font-semibold tracking-[-0.03em] ${toneClass}`}
      >
        {value}
      </p>
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
    <div className="rounded-[10px] border border-dashed border-[var(--line-strong)] bg-[var(--ink-800)] p-8">
      <h2 className="text-sm font-semibold text-[var(--paper)]">{title}</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--paper-dim)]">{body}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ what, onRetry }: { what: string; onRetry: () => void }) {
  return (
    <div
      className="rounded-[10px] border border-[var(--crimson-line)] bg-[var(--crimson-soft)] p-6 text-sm text-[var(--crimson-deep)]"
      role="alert"
    >
      <p className="font-medium">{what} could not be loaded.</p>
      <button
        className="mt-3 rounded-sm font-semibold text-[var(--crimson-deep)] underline decoration-[var(--crimson-line)] underline-offset-4"
        onClick={onRetry}
        type="button"
      >
        Retry
      </button>
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={`skeleton ${className}`} />;
}

export function PageSkeleton({ cards = 4, rows = 4 }: { cards?: number; rows?: number }) {
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
