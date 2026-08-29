"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BrainCircuit,
  Database,
  FileUp,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  WalletCards,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge, ErrorState, PageHeader } from "@/components/ui/primitives";
import { setActiveRunId } from "@/lib/active-run";
import { api } from "@/lib/api";

const PRODUCTION_MODE = process.env.NEXT_PUBLIC_APP_MODE === "production";

export default function DataSourcesPage() {
  const router = useRouter();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const status = useQuery({ queryKey: ["razorpay-status"], queryFn: api.razorpayStatus });
  const mcp = useQuery({
    queryKey: ["razorpay-mcp-capability"],
    queryFn: api.razorpayMcpCapability,
  });
  const sync = useMutation({ mutationFn: api.syncRazorpay });
  const submit = useMutation({
    mutationFn: () =>
      api.submitRazorpaySyncJob(`ui-${Date.now()}-${globalThis.crypto.randomUUID()}`),
  });
  const upload = useMutation({ mutationFn: api.uploadSources });
  const demo = useMutation({
    mutationFn: api.loadDemo,
    onSuccess: (run) => {
      // Opening the demo is a session choice; it must not replace a real
      // uploaded run as the persisted default workspace.
      setActiveRunId(run.run_id, { persist: false });
      router.push("/");
    },
  });
  const execute = useMutation({
    mutationFn: () => {
      const uploadIds = upload.data?.files.map((file) => file.upload_id).filter(Boolean) ?? [];
      if (uploadIds.length !== selectedFiles.length) {
        throw new Error("Every selected file must pass classification before execution.");
      }
      return api.createRunFromUploads(selectedFiles, uploadIds as string[]);
    },
    onSuccess: (run) => {
      setActiveRunId(run.run_id, { persist: true });
      router.push("/");
    },
  });
  const jobId = submit.data?.job.id;
  const job = useQuery({
    queryKey: ["background-job", jobId],
    queryFn: () => api.backgroundJob(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const jobStatus = query.state.data?.status;
      return jobStatus && ["SUCCEEDED", "FAILED", "CANCELLED"].includes(jobStatus)
        ? false
        : 1500;
    },
  });
  const syncing = PRODUCTION_MODE ? submit.isPending : sync.isPending;
  const connectorBadge = status.data?.connected
    ? `CONNECTED · ${status.data.mode.toUpperCase()} MODE`
    : status.data?.configured
      ? "CREDENTIALS CONFIGURED · NOT YET VERIFIED"
      : "BACKEND CREDENTIALS REQUIRED";

  return (
    <main className="mx-auto max-w-[1160px] px-5 py-8 md:px-8 md:py-10">
      <PageHeader
        eyebrow="Ingestion"
        title="Choose a financial data source"
        subtitle="Every source normalizes into the same financial event graph and deterministic control pipeline."
      />

      <section className="mb-6 grid gap-4 md:grid-cols-3">
        <SourceCard
          icon={Database}
          title="NovaCart Demo Dataset"
          description="Seeded 500-payment run with hidden ground truth and stable proof cases."
          badge={PRODUCTION_MODE ? "DEMO DISABLED" : "ACTIVE"}
          badgeTone={PRODUCTION_MODE ? "DRAFT" : "PASS"}
        >
          {!PRODUCTION_MODE ? (
            <button
              type="button"
              onClick={() => demo.mutate()}
              disabled={demo.isPending}
              className="mt-5 flex items-center gap-2 text-xs font-semibold text-[var(--evergreen)] transition-colors duration-150 hover:text-[var(--paper)] disabled:opacity-60"
            >
              {demo.isPending ? (
                <LoaderCircle size={13} className="animate-spin" />
              ) : (
                <ArrowRight size={13} />
              )}
              {demo.isPending ? "Preparing demo…" : "Open demo run"}
            </button>
          ) : null}
        </SourceCard>

        <SourceCard
          icon={WalletCards}
          title="Razorpay Account"
          description="Read-only payment, refund, settlement and reconciliation ingestion."
          badge={status.data?.configured ? "CONFIGURED" : "NOT CONFIGURED"}
          badgeTone={status.data?.configured ? "PASS" : "DRAFT"}
        >
          <button
            type="button"
            onClick={() => (PRODUCTION_MODE ? submit.mutate() : sync.mutate())}
            disabled={!status.data?.configured || syncing}
            className="mt-5 flex items-center gap-2 rounded-lg bg-[var(--evergreen)] px-3 py-2 text-xs font-semibold text-[#06120c] transition-opacity duration-150 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {syncing ? (
              <LoaderCircle size={13} className="animate-spin" />
            ) : (
              <RefreshCw size={13} />
            )}
            {PRODUCTION_MODE ? "Queue durable sync" : "Sync Razorpay"}
          </button>
        </SourceCard>

        <SourceCard
          icon={FileUp}
          title="Upload Files"
          description="Upload related CSVs together. Headers and content are classified deterministically before private storage."
          badge="MULTI-FILE"
          badgeTone="INFO"
        >
          <label className="mt-5 inline-flex cursor-pointer items-center gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--ink-700)] px-3 py-2 text-xs font-semibold text-[var(--paper)] transition-colors duration-150 hover:bg-[var(--ink-600)]">
            {upload.isPending ? (
              <LoaderCircle size={13} className="animate-spin" />
            ) : (
              <FileUp size={13} />
            )}
            {upload.isPending ? "Classifying…" : "Choose CSV files"}
            <input
              className="sr-only"
              type="file"
              accept=".csv,text/csv"
              multiple
              disabled={upload.isPending}
              onChange={(event) => {
                const selected = Array.from(event.currentTarget.files ?? []);
                if (selected.length) {
                  setSelectedFiles(selected);
                  execute.reset();
                  upload.mutate(selected);
                }
                event.currentTarget.value = "";
              }}
            />
          </label>
          <div className="mt-3 min-h-10 text-[10px] leading-4 text-[var(--paper-dim)]" aria-live="polite">
            {upload.data ? (
              <div className="space-y-1.5">
                <p className="number-tabular font-mono font-semibold text-[var(--evergreen)]">
                  {upload.data.accepted_count} accepted · {upload.data.rejected_count} rejected
                </p>
                {upload.data.files.map((file) => (
                  <div
                    key={`${file.filename}-${file.upload_id ?? "rejected"}`}
                    className={`rounded-lg border px-2.5 py-2 ${
                      file.status === "ACCEPTED"
                        ? "border-[rgba(47,189,127,0.35)] bg-[rgba(47,189,127,0.08)]"
                        : "border-[rgba(226,96,79,0.35)] bg-[rgba(226,96,79,0.08)]"
                    }`}
                  >
                    <p className="font-semibold text-[var(--paper)]">{file.filename}</p>
                    <p>
                      {file.status === "ACCEPTED"
                        ? `${file.source_type.replaceAll("_", " ")} · ${file.row_count} rows · ${Math.round(
                            Number(file.classification_confidence) * 100,
                          )}% confidence`
                        : file.error}
                    </p>
                    {file.status === "ACCEPTED" && file.schema_drift ? (
                      <p className="mt-1 text-[var(--amber)]">Schema review: unmapped columns {file.drift_columns.join(", ")}</p>
                    ) : null}
                  </div>
                ))}
                {(() => {
                  const accepted = upload.data.files.filter((file) => file.status === "ACCEPTED");
                  // Execution re-verifies bytes against persisted artifact hashes, so it
                  // requires durable private storage. VALIDATED_ONLY uploads (no storage
                  // backend configured) would deterministically fail with 404.
                  const durable =
                    upload.data.rejected_count === 0 &&
                    accepted.length > 0 &&
                    accepted.every((file) => file.storage_status === "PRIVATE_STORAGE");
                  return durable ? (
                    <button
                      type="button"
                      onClick={() => execute.mutate()}
                      disabled={execute.isPending}
                      className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--evergreen)] px-3 py-2.5 text-xs font-semibold text-[#06120c] transition-opacity duration-150 disabled:cursor-wait disabled:opacity-60"
                    >
                      {execute.isPending ? (
                        <LoaderCircle size={13} className="animate-spin" />
                      ) : (
                        <ArrowRight size={13} />
                      )}
                      {execute.isPending ? "Executing deterministic controls…" : "Create run and execute controls"}
                    </button>
                  ) : (
                    <p className="mt-3 rounded-lg border border-[var(--line)] bg-[var(--ink-700)] px-2.5 py-2 text-[11px] leading-5 text-[var(--paper-dim)]">
                      {upload.data.rejected_count === 0 && accepted.length > 0
                        ? "Classified, but not durably stored: configure private storage (SUPABASE_URL and service role key) on the backend before creating a run."
                        : null}
                    </p>
                  );
                })()}
                {execute.data ? (
                  <p className="number-tabular rounded-lg bg-[rgba(47,189,127,0.14)] px-2.5 py-2 font-mono font-semibold text-[var(--evergreen)]">
                    Run complete · {execute.data.events_created} events · {execute.data.violations_created}{" "}
                    violations
                  </p>
                ) : null}
                {execute.error ? (
                  <p className="text-[var(--crimson)]" role="alert">
                    {execute.error.message}
                  </p>
                ) : null}
              </div>
            ) : null}
            {upload.error && <span className="text-[var(--crimson)]">{upload.error.message}</span>}
          </div>
        </SourceCard>
      </section>

      <section className="panel overflow-hidden rounded-2xl">
        <div className="flex flex-col justify-between gap-3 border-b border-[var(--line)] px-5 py-4 sm:flex-row sm:items-center">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--paper)]">
              <WalletCards size={16} className="text-[var(--evergreen)]" /> Razorpay read-only connector
            </h2>
            <p className="mt-1 text-xs text-[var(--paper-dim)]">
              Actual behaviour enters sl3dge; approved controls still define expected behaviour.
            </p>
          </div>
          <Badge status={status.data?.connected ? "PASS" : "DRAFT"} label={connectorBadge} />
        </div>
        <div className="p-5">
          {status.isError ? (
            <ErrorState what="Connector status" onRetry={() => status.refetch()} />
          ) : null}
          {!status.data?.configured && (
            <div className="mb-5 flex items-start gap-3 rounded-xl border border-[var(--line)] bg-[var(--ink-700)] p-4">
              <KeyRound size={18} className="mt-0.5 text-[var(--paper-dim)]" />
              <div>
                <p className="text-xs font-semibold text-[var(--paper)]">
                  Configure credentials on the backend
                </p>
                <p className="mt-1 text-[11px] leading-5 text-[var(--paper-dim)]">
                  Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in the backend environment. Secrets are
                  never requested by or returned to this browser.
                </p>
              </div>
            </div>
          )}

          {PRODUCTION_MODE ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-live="polite">
              <SyncMetric label="Durable job" value={job.data?.id ?? submit.data?.job.id ?? "—"} />
              <SyncMetric label="Job status" value={job.data?.status ?? submit.data?.job.status ?? "—"} />
              <SyncMetric label="Attempts" value={job.data?.attempt_count ?? 0} />
              <SyncMetric label="Last verified sync" value={status.data?.last_sync_status ?? "—"} />
            </div>
          ) : sync.data ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <SyncMetric label="Payments imported" value={sync.data.payments_imported} />
              <SyncMetric label="Refunds imported" value={sync.data.refunds_imported} />
              <SyncMetric label="Settlements imported" value={sync.data.settlements_imported} />
              <SyncMetric label="Recon records" value={sync.data.reconciliation_records_imported} />
              <SyncMetric label="Last sync" value="Complete" />
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <SyncMetric label="Payments imported" value="—" />
              <SyncMetric label="Refunds imported" value="—" />
              <SyncMetric label="Settlements imported" value="—" />
              <SyncMetric label="Recon records" value="—" />
              <SyncMetric label="Last sync" value={status.data?.last_sync_status ?? "—"} />
            </div>
          )}
          {(sync.error || submit.error || job.data?.error) && (
            <p className="mt-4 text-xs text-[var(--crimson)]" role="alert">
              {job.data?.error?.message ?? sync.error?.message ?? submit.error?.message}
            </p>
          )}
          <div className="mt-5 flex items-center gap-2 border-t border-[var(--line)] pt-4 text-[11px] text-[var(--paper-dim)]">
            <ShieldCheck size={14} className="text-[var(--evergreen)]" /> Connector permissions are
            GET-only. No payment, refund or settlement action is available.
          </div>
        </div>
      </section>

      {mcp.data && (
        <section className="panel mt-6 overflow-hidden rounded-2xl">
          <div className="flex flex-col justify-between gap-3 border-b border-[var(--line)] px-5 py-4 sm:flex-row sm:items-center">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--paper)]">
                <BrainCircuit size={16} className="text-[var(--evergreen)]" /> Optional MCP investigation
                evidence
              </h2>
              <p className="mt-1 text-xs text-[var(--paper-dim)]">
                Supplementary context only; direct API ingestion and deterministic controls remain
                authoritative.
              </p>
            </div>
            <Badge
              status={mcp.data.enabled ? "INFO" : "DRAFT"}
              label={mcp.data.enabled ? "ENABLED · READ ONLY" : "DISABLED BY DEFAULT"}
            />
          </div>
          <div className="p-5">
            <div className="flex flex-wrap gap-2">
              {mcp.data.allowed_tools.map((tool) => (
                <span
                  key={tool}
                  className="rounded-md border border-[var(--line)] bg-[var(--ink-600)] px-2 py-1 font-mono text-[9px] text-[var(--paper-dim)]"
                >
                  {tool}
                </span>
              ))}
            </div>
            <p className="mt-4 flex items-start gap-2 border-t border-[var(--line)] pt-4 text-[11px] leading-5 text-[var(--paper-dim)]">
              <ShieldCheck size={14} className="mt-0.5 shrink-0 text-[var(--evergreen)]" />
              {mcp.data.result_policy}
            </p>
          </div>
        </section>
      )}
    </main>
  );
}

function SourceCard({
  icon: Icon,
  title,
  description,
  badge,
  badgeTone,
  children,
}: {
  icon: typeof Database;
  title: string;
  description: string;
  badge: string;
  badgeTone: "PASS" | "INFO" | "DRAFT";
  children: React.ReactNode;
}) {
  return (
    <div className="panel rounded-2xl p-5">
      <div className="flex items-start justify-between gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-[rgba(47,189,127,0.14)] text-[var(--evergreen)]">
          <Icon size={19} />
        </span>
        <Badge status={badgeTone} label={badge} />
      </div>
      <h2 className="mt-5 text-sm font-semibold text-[var(--paper)]">{title}</h2>
      <p className="mt-2 min-h-12 text-xs leading-5 text-[var(--paper-dim)]">{description}</p>
      {children}
    </div>
  );
}

function SyncMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-0 rounded-xl border border-[var(--line)] bg-[var(--ink-700)] p-3">
      <p className="number-tabular truncate font-mono text-lg font-semibold text-[var(--paper)]" title={String(value)}>
        {value}
      </p>
      <p className="mt-1 text-[10px] text-[var(--paper-faint)]">{label}</p>
    </div>
  );
}
