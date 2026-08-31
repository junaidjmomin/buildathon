import type { ReactNode } from "react";

import { PageSkeleton } from "@/components/ui/primitives";

export function WorkspaceLoading({ label }: { label: string }) {
  return (
    <main
      aria-busy="true"
      aria-label={label}
      className="mx-auto max-w-[1240px] px-5 py-8 md:px-8 md:py-10"
      role="status"
    >
      <PageSkeleton cards={4} rows={3} />
    </main>
  );
}

export function SummaryStrip({
  label,
  items,
  columns = "four",
  className = "",
}: {
  label: string;
  items: Array<{
    label: string;
    value: ReactNode;
    detail?: ReactNode;
    tone?: "default" | "positive" | "warning" | "negative";
  }>;
  columns?: "three" | "four" | "five";
  className?: string;
}) {
  const columnClass = {
    three: "lg:grid-cols-3",
    four: "lg:grid-cols-4",
    five: "lg:grid-cols-5",
  }[columns];

  return (
    <section aria-label={label} className={`panel overflow-hidden rounded-xl ${className}`}>
      <dl className={`grid sm:grid-cols-2 ${columnClass}`}>
        {items.map((item, index) => {
          const toneClass = {
            default: "text-[var(--paper)]",
            positive: "text-[var(--evergreen)]",
            warning: "text-[var(--amber)]",
            negative: "text-[var(--crimson)]",
          }[item.tone ?? "default"];
          return (
            <div
              className={`min-w-0 px-5 py-4 ${index ? "border-t border-[var(--line)] sm:border-t-0" : ""} ${index > 1 ? "sm:border-t" : ""} lg:border-t-0 lg:border-l lg:first:border-l-0`}
              key={`${item.label}-${index}`}
            >
              <dt className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--paper-faint)]">
                {item.label}
              </dt>
              <dd className={`number-tabular mt-1.5 truncate font-mono text-lg font-semibold ${toneClass}`}>
                {item.value}
              </dd>
              {item.detail ? (
                <p className="mt-1 truncate text-[11px] text-[var(--paper-dim)]">{item.detail}</p>
              ) : null}
            </div>
          );
        })}
      </dl>
    </section>
  );
}

export function SectionHeader({
  title,
  description,
  meta,
}: {
  title: string;
  description?: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <header className="flex flex-col justify-between gap-3 border-b border-[var(--line)] px-5 py-4 sm:flex-row sm:items-start">
      <div>
        <h2 className="text-sm font-semibold text-[var(--paper)]">{title}</h2>
        {description ? (
          <p className="mt-1 max-w-3xl text-xs leading-5 text-[var(--paper-dim)]">{description}</p>
        ) : null}
      </div>
      {meta ? <div className="shrink-0 text-xs text-[var(--paper-dim)]">{meta}</div> : null}
    </header>
  );
}

export function EmptySection({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="px-5 py-10 text-center">
      <p className="text-sm font-medium text-[var(--paper)]">{title}</p>
      <p className="mx-auto mt-1 max-w-lg text-xs leading-5 text-[var(--paper-dim)]">{body}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function InlineNotice({
  children,
  tone = "neutral",
  className = "",
}: {
  children: ReactNode;
  tone?: "neutral" | "positive" | "warning" | "negative";
  className?: string;
}) {
  const toneClass = {
    neutral: "border-[var(--line-strong)] text-[var(--paper-dim)]",
    positive: "border-[var(--evergreen)] text-[var(--evergreen)]",
    warning: "border-[var(--amber)] text-[var(--amber)]",
    negative: "border-[var(--crimson)] text-[var(--crimson)]",
  }[tone];
  return (
    <div
      className={`rounded-lg border-l-2 bg-[var(--ink-700)] px-4 py-3 text-xs leading-5 ${toneClass} ${className}`}
      role={tone === "negative" ? "alert" : undefined}
    >
      {children}
    </div>
  );
}

