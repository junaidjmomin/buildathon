"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BrainCircuit,
  ChevronDown,
  Database,
  FileCheck2,
  FileUp,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  WalletCards,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { EvidenceMap } from "@/components/brand-assets";
import { Badge, PageHeader } from "@/components/ui/primitives";
import { setActiveRunId } from "@/lib/active-run";
import { api } from "@/lib/api";

const PRODUCTION_MODE = process.env.NEXT_PUBLIC_APP_MODE === "production";

export default function DataSourcesPage() {
  const router = useRouter();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const status = useQuery({ queryKey: ["razorpay-status"], queryFn: api.razorpayStatus });
  const mcp = useQuery({ queryKey: ["razorpay-mcp-capability"], queryFn: api.razorpayMcpCapability });
  const sync = useMutation({ mutationFn: api.syncRazorpay });
  const submit = useMutation({ mutationFn: () => api.submitRazorpaySyncJob(`ui-${Date.now()}-${globalThis.crypto.randomUUID()}`) });
  const upload = useMutation({ mutationFn: api.uploadSources });
  const demo = useMutation({
    mutationFn: api.loadDemo,
    onSuccess: (run) => {
      setActiveRunId(run.run_id, { persist: false });
      router.push("/");
    },
  });
  const execute = useMutation({
    mutationFn: () => {
      const uploadIds = upload.data?.files.map((file) => file.upload_id).filter(Boolean) ?? [];
      if (uploadIds.length !== selectedFiles.length) throw new Error("Every selected file must pass classification before execution.");
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
      return jobStatus && ["SUCCEEDED", "FAILED", "CANCELLED"].includes(jobStatus) ? false : 1500;
    },
  });
  const syncing = PRODUCTION_MODE ? submit.isPending : sync.isPending;
  const connectorBadge = status.isPending
    ? "CHECKING"
    : status.data?.connected
      ? "CONNECTED"
      : status.data?.configured
        ? "READY TO VERIFY"
        : "SETUP REQUIRED";

  return (
    <main className="mx-auto max-w-[1200px] px-5 py-8 md:px-8 md:py-10">
      <section className="mb-6 grid overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)] lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="p-5 md:p-7">
          <PageHeader
            eyebrow="Data workspace"
            title="Bring in financial records"
            subtitle="Connect the live account or upload a related CSV bundle. Both routes create the same evidence-backed control run."
          />
          <div className="flex flex-wrap gap-x-5 gap-y-2 text-[11px] text-[var(--paper-dim)]">
            <span className="inline-flex items-center gap-1.5"><ShieldCheck size={13} className="text-[var(--evergreen)]" /> Read-only ingestion</span>
            <span className="inline-flex items-center gap-1.5"><FileCheck2 size={13} className="text-[var(--evergreen)]" /> Source classification before execution</span>
          </div>
        </div>
        <div className="relative min-h-48 border-t border-[var(--line)] bg-[var(--ink-700)] lg:border-l lg:border-t-0">
          <EvidenceMap eager className="absolute inset-0 h-full w-full object-cover" />
        </div>
      </section>

      <section className="mb-5 grid gap-5 lg:grid-cols-[1.25fr_0.75fr]" aria-label="Choose a data source">
        <article className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)]">
          <div className="flex flex-col justify-between gap-4 border-b border-[var(--line)] bg-[var(--ink-700)] px-5 py-4 sm:flex-row sm:items-start">
            <div className="flex items-start gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--ink-800)] text-[var(--evergreen)]"><WalletCards size={18} /></span>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--paper-faint)]">Recommended for ongoing review</p>
                <h2 className="mt-1 text-base font-semibold text-[var(--paper)]">Razorpay account</h2>
                <p className="mt-1 text-xs leading-5 text-[var(--paper-dim)]">Import payments, refunds, settlements and reconciliation records with read-only access.</p>
              </div>
            </div>
            <Badge status={status.data?.connected ? "PASS" : status.isPending ? "INFO" : "DRAFT"} label={connectorBadge} />
          </div>

          <div className="p-5">
            {status.isError ? (
              <div className="mb-4 flex flex-col justify-between gap-3 rounded-lg border border-[var(--line)] bg-[var(--ink-700)] p-4 sm:flex-row sm:items-center" role="alert">
                <div>
                  <p className="text-xs font-semibold text-[var(--paper)]">Connector health is unavailable</p>
                  <p className="mt-1 text-[11px] text-[var(--paper-dim)]">The account status could not be checked.</p>
                </div>
                <button type="button" onClick={() => void status.refetch()} className="text-xs font-semibold text-[var(--evergreen)] hover:underline">Retry status</button>
              </div>
            ) : null}

            <div className="grid overflow-hidden rounded-lg border border-[var(--line)] sm:grid-cols-3" aria-live="polite">
              <ConnectorFact label="Connection" value={status.isPending ? "Checking…" : status.data?.connected ? "Verified" : status.data?.configured ? "Not verified" : "Not configured"} />
              <ConnectorFact label="Mode" value={status.data?.mode ? status.data.mode.replaceAll("_", " ") : "—"} />
              <ConnectorFact label="Last sync" value={status.data?.last_sync_status || "—"} />
            </div>

            {!status.isPending && !status.isError && !status.data?.configured ? (
              <p className="mt-4 text-xs leading-5 text-[var(--paper-dim)]">An administrator needs to finish connector setup before a live sync can run. Technical setup details are available below.</p>
            ) : null}

            <div className="mt-5 flex flex-col justify-between gap-3 border-t border-[var(--line)] pt-4 sm:flex-row sm:items-center">
              <p className="flex items-start gap-2 text-[11px] leading-5 text-[var(--paper-dim)]"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-[var(--evergreen)]" /> This workspace cannot create, refund or settle payments.</p>
              <button
                type="button"
                onClick={() => (PRODUCTION_MODE ? submit.mutate() : sync.mutate())}
                disabled={!status.data?.configured || syncing}
                className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-[var(--evergreen)] px-3.5 py-2.5 text-xs font-semibold text-[var(--ink-800)] disabled:cursor-not-allowed disabled:opacity-45"
              >
                {syncing ? <LoaderCircle size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                {syncing ? "Syncing…" : PRODUCTION_MODE ? "Queue account sync" : "Sync account now"}
              </button>
            </div>

            {PRODUCTION_MODE && (submit.data || job.data) ? (
              <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4" aria-live="polite">
                <SyncMetric label="Job" value={job.data?.id ?? submit.data?.job.id ?? "—"} />
                <SyncMetric label="Status" value={job.data?.status ?? submit.data?.job.status ?? "—"} />
                <SyncMetric label="Attempts" value={job.data?.attempt_count ?? submit.data?.job.attempt_count ?? 0} />
                <SyncMetric label="Last verified sync" value={status.data?.last_sync_status ?? "—"} />
              </div>
            ) : !PRODUCTION_MODE && sync.data ? (
              <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4" aria-live="polite">
                <SyncMetric label="Payments" value={sync.data.payments_imported} />
                <SyncMetric label="Refunds" value={sync.data.refunds_imported} />
                <SyncMetric label="Settlements" value={sync.data.settlements_imported} />
                <SyncMetric label="Reconciliation records" value={sync.data.reconciliation_records_imported} />
              </div>
            ) : null}
            {(sync.error || submit.error || job.data?.error) ? <p className="mt-4 text-xs text-[var(--crimson)]" role="alert">{job.data?.error?.message ?? sync.error?.message ?? submit.error?.message}</p> : null}
          </div>
        </article>

        <article className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)]">
          <div className="border-b border-[var(--line)] bg-[var(--ink-700)] px-5 py-4">
            <div className="flex items-start justify-between gap-3">
              <span className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--ink-800)] text-[var(--evergreen)]"><FileUp size={18} /></span>
              <Badge status="INFO" label="CSV bundle" />
            </div>
            <h2 className="mt-4 text-base font-semibold text-[var(--paper)]">Upload source files</h2>
            <p className="mt-1 text-xs leading-5 text-[var(--paper-dim)]">Choose related CSVs together. Each file is classified and checked before controls can run.</p>
          </div>
          <div className="p-5">
            <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-[var(--line-strong)] bg-[var(--ink-700)] px-4 py-5 text-xs font-semibold text-[var(--paper)] transition-colors hover:bg-[var(--ink-600)]">
              {upload.isPending ? <LoaderCircle size={15} className="animate-spin" /> : <FileUp size={15} className="text-[var(--evergreen)]" />}
              {upload.isPending ? "Classifying files…" : "Choose CSV files"}
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

            <div className="mt-3 text-[10px] leading-4 text-[var(--paper-dim)]" aria-live="polite">
              {upload.data ? (
                <div>
                  <p className="number-tabular mb-2 font-mono font-semibold text-[var(--paper)]">{upload.data.accepted_count} accepted · {upload.data.rejected_count} rejected</p>
                  <div className="max-h-56 divide-y divide-[var(--line)] overflow-y-auto rounded-lg border border-[var(--line)]">
                    {upload.data.files.map((file) => (
                      <div key={`${file.filename}-${file.upload_id ?? "rejected"}`} className="bg-[var(--ink-700)] px-3 py-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate font-semibold text-[var(--paper)]" title={file.filename}>{file.filename}</p>
                          <span className={file.status === "ACCEPTED" ? "text-[var(--evergreen)]" : "text-[var(--crimson)]"}>{file.status}</span>
                        </div>
                        <p className="mt-1">
                          {file.status === "ACCEPTED" ? `${file.source_type.replaceAll("_", " ")} · ${file.row_count.toLocaleString("en-IN")} rows · ${Math.round(Number(file.classification_confidence) * 100)}% confidence` : file.error}
                        </p>
                        {file.status === "ACCEPTED" && file.schema_drift ? <p className="mt-1 text-[var(--amber)]">Review unmapped columns: {file.drift_columns.join(", ")}</p> : null}
                      </div>
                    ))}
                  </div>
                  <UploadExecution uploadData={upload.data} execute={() => execute.mutate()} pending={execute.isPending} />
                  {execute.error ? <p className="mt-3 text-[var(--crimson)]" role="alert">{execute.error.message}</p> : null}
                </div>
              ) : upload.error ? (
                <p className="text-[var(--crimson)]" role="alert">{upload.error.message}</p>
              ) : (
                <p>CSV only · select every file needed for one financial period.</p>
              )}
            </div>
          </div>
        </article>
      </section>

      {!PRODUCTION_MODE ? (
        <section className="mb-5 flex flex-col justify-between gap-4 rounded-xl border border-[var(--line)] bg-[var(--ink-800)] px-5 py-4 sm:flex-row sm:items-center">
          <div className="flex items-start gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--ink-700)] text-[var(--evergreen)]"><Database size={17} /></span>
            <div>
              <div className="flex flex-wrap items-center gap-2"><h2 className="text-sm font-semibold text-[var(--paper)]">Sample agreement workspace</h2><Badge status="INFO" label="Sandbox" /></div>
              <p className="mt-1 text-xs leading-5 text-[var(--paper-dim)]">Explore the review flow with agreement extraction data before connecting a live account.</p>
            </div>
          </div>
          <button type="button" onClick={() => demo.mutate()} disabled={demo.isPending} className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-3.5 py-2.5 text-xs font-semibold text-[var(--paper)] hover:bg-[var(--ink-700)] disabled:opacity-60">
            {demo.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <ArrowRight size={13} />}
            {demo.isPending ? "Loading data…" : "Load agreement extraction data"}
          </button>
        </section>
      ) : null}

      <details className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--ink-800)]">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 text-xs font-semibold text-[var(--paper)] hover:bg-[var(--ink-700)] [&::-webkit-details-marker]:hidden">
          <span className="inline-flex items-center gap-2"><KeyRound size={14} className="text-[var(--paper-dim)]" /> Advanced connector diagnostics</span>
          <ChevronDown size={14} className="text-[var(--paper-faint)]" />
        </summary>
        <div className="space-y-5 border-t border-[var(--line)] px-5 py-5">
          {!status.data?.configured ? (
            <div className="rounded-lg border border-[var(--line)] bg-[var(--ink-700)] p-4">
              <p className="text-xs font-semibold text-[var(--paper)]">Backend credential setup</p>
              <p className="mt-1 text-[11px] leading-5 text-[var(--paper-dim)]">Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in the backend environment. Credentials are never requested by or returned to this browser.</p>
            </div>
          ) : null}

          <div>
            <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
              <div>
                <h2 className="flex items-center gap-2 text-xs font-semibold text-[var(--paper)]"><BrainCircuit size={14} className="text-[var(--evergreen)]" /> Investigation context connector</h2>
                <p className="mt-1 text-[11px] leading-5 text-[var(--paper-dim)]">Optional read-only context. Direct ingestion and deterministic controls remain authoritative.</p>
              </div>
              {mcp.data ? <Badge status={mcp.data.enabled ? "INFO" : "DRAFT"} label={mcp.data.enabled ? "Enabled · read only" : "Disabled"} /> : null}
            </div>
            {mcp.isPending ? <p className="mt-3 inline-flex items-center gap-2 text-[11px] text-[var(--paper-dim)]"><LoaderCircle size={12} className="animate-spin" /> Checking capability…</p> : null}
            {mcp.isError ? <p className="mt-3 text-[11px] text-[var(--crimson)]" role="alert">Capability status could not be loaded. <button type="button" onClick={() => void mcp.refetch()} className="font-semibold underline">Retry</button></p> : null}
            {mcp.data ? (
              <div className="mt-3">
                {mcp.data.allowed_tools.length > 0 ? <p className="font-mono text-[10px] leading-5 text-[var(--paper-faint)]">Allowed tools · {mcp.data.allowed_tools.join(" · ")}</p> : null}
                <p className="mt-2 text-[11px] leading-5 text-[var(--paper-dim)]">{mcp.data.result_policy}</p>
              </div>
            ) : null}
          </div>
        </div>
      </details>
    </main>
  );
}

function ConnectorFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 border-b border-[var(--line)] px-3.5 py-3 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0">
      <p className="truncate text-xs font-semibold capitalize text-[var(--paper)]" title={value}>{value}</p>
      <p className="mt-1 text-[9px] font-medium uppercase tracking-[0.08em] text-[var(--paper-faint)]">{label}</p>
    </div>
  );
}

function UploadExecution({ uploadData, execute, pending }: { uploadData: Awaited<ReturnType<typeof api.uploadSources>>; execute: () => void; pending: boolean }) {
  const accepted = uploadData.files.filter((file) => file.status === "ACCEPTED");
  const durable = uploadData.rejected_count === 0 && accepted.length > 0 && accepted.every((file) => file.storage_status === "PRIVATE_STORAGE");
  if (durable) {
    return (
      <button type="button" onClick={execute} disabled={pending} className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--evergreen)] px-3 py-2.5 text-xs font-semibold text-[var(--ink-800)] disabled:cursor-wait disabled:opacity-60">
        {pending ? <LoaderCircle size={13} className="animate-spin" /> : <ArrowRight size={13} />}
        {pending ? "Running controls…" : "Create control run"}
      </button>
    );
  }
  if (uploadData.rejected_count === 0 && accepted.length > 0) {
    return <p className="mt-3 rounded-lg bg-[var(--ink-700)] px-3 py-2 text-[11px] leading-5 text-[var(--paper-dim)]">Files passed classification but are not stored yet. An administrator must configure private storage before this run can execute.</p>;
  }
  return null;
}

function SyncMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-0 rounded-lg bg-[var(--ink-700)] p-3">
      <p className="number-tabular truncate font-mono text-sm font-semibold text-[var(--paper)]" title={String(value)}>{value}</p>
      <p className="mt-1 text-[9px] font-medium uppercase tracking-[0.08em] text-[var(--paper-faint)]">{label}</p>
    </div>
  );
}
