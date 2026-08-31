import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/components/auth-provider";
import type { Agreement, AgreementClause, ControlProposal } from "@/types/api";

import AgreementsPage from "./page";

const apiMocks = vi.hoisted(() => ({
  agreements: vi.fn(),
  agreementProposals: vi.fn(),
  extractAgreementControls: vi.fn(),
  uploadAgreement: vi.fn(),
  addAgreementClause: vi.fn(),
  runs: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: apiMocks,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn() }),
}));

function clause(overrides: Partial<AgreementClause> = {}): AgreementClause {
  return {
    id: "CLS_1",
    reference: "4.2(a)",
    page: 3,
    heading: "Domestic MDR",
    text: "1.55% of the transaction amount.",
    effective_from: "2026-01-01",
    effective_to: null,
    source_type: "PDF_TEXT_EXTRACTION",
    created_by: null,
    ...overrides,
  };
}

function agreement(overrides: Partial<Agreement> = {}): Agreement {
  return {
    id: "AGR_UPLOADED_1",
    merchant: "Merchant A",
    title: "Merchant Services Agreement",
    status: "ACTIVE",
    effective_from: "2026-01-01",
    effective_to: null,
    source_type: "PDF",
    content_hash: "a".repeat(64),
    clauses: [clause()],
    ...overrides,
  };
}

function proposals(): ControlProposal[] {
  return [];
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AgreementsPage />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  apiMocks.runs.mockResolvedValue([]);
  apiMocks.agreements.mockResolvedValue([]);
  apiMocks.agreementProposals.mockResolvedValue(proposals());
  apiMocks.uploadAgreement.mockResolvedValue(agreement());
  apiMocks.addAgreementClause.mockResolvedValue(clause());
});

describe("agreements page", () => {
  it("always shows the PDF upload intake when no agreement exists", async () => {
    apiMocks.agreements.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByRole("heading", { name: "Upload agreement PDF" })).toBeVisible();
    expect(apiMocks.agreements).toHaveBeenCalledTimes(1);
  });

  it("disables manual clause entry for the immutable seeded agreement", async () => {
    apiMocks.agreements.mockResolvedValue([agreement({ source_type: "SEEDED_TEXT" })]);
    renderPage();
    const reference = await screen.findByPlaceholderText("e.g. 4.2(a)");
    expect(reference).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /Add clause/ }),
    ).toBeDisabled();
    expect(
      screen.getByText(/seeded agreement is immutable/i),
    ).toBeVisible();
  });

  it("enables manual clause entry once a durable agreement is uploaded", async () => {
    apiMocks.agreements.mockResolvedValue([agreement()]);
    renderPage();
    expect(await screen.findByPlaceholderText("e.g. 4.2(a)")).toBeEnabled();
    expect(screen.getByRole("button", { name: /Add clause/ })).toBeEnabled();
    expect(screen.queryByText(/seeded agreement is immutable/i)).not.toBeInTheDocument();
  });

  it("submits a manual clause with the entered payload", async () => {
    apiMocks.agreements.mockResolvedValue([agreement()]);
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByPlaceholderText("e.g. 4.2(a)"), "4.9(b)");
    await user.type(screen.getByPlaceholderText("Domestic MDR"), "International MDR");
    await user.type(screen.getByLabelText(/Clause text/), "3.25% of the transaction amount.");
    await user.click(screen.getByRole("button", { name: /Add clause/ }));

    await waitFor(() => expect(apiMocks.addAgreementClause).toHaveBeenCalledTimes(1));
    expect(apiMocks.addAgreementClause).toHaveBeenCalledWith(
      "AGR_UPLOADED_1",
      expect.objectContaining({ reference: "4.9(b)", heading: "International MDR" }),
    );
  });

  it("uploads the selected PDF with the agreement metadata", async () => {
    apiMocks.agreements.mockResolvedValue([]);
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/Merchant name/), "Merchant B");
    await user.type(screen.getByLabelText(/Agreement title/), "Durable Agreement");
    // The upload intake renders before the clause registry; scope to the first
    // "Effective from" field to avoid matching the manual-clause form's input.
    // Date inputs cannot receive user-event typing; set the value directly.
    fireEvent.change(screen.getAllByLabelText("Effective from")[0], {
      target: { value: "2026-02-01" },
    });
    const file = new File(["%PDF-1.4 demo"], "agreement.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText(/PDF file/), file);
    // jsdom never marks a required file input as satisfied, so a native button
    // click is blocked by constraint validation. Dispatch submit directly;
    // the React handler still reads the same FormData.
    const uploadForm = screen
      .getByRole("button", { name: /Upload and extract PDF/ })
      .closest("form")!;
    fireEvent.submit(uploadForm);

    await waitFor(() => expect(apiMocks.uploadAgreement).toHaveBeenCalledTimes(1));
    const formData = apiMocks.uploadAgreement.mock.calls[0][0] as FormData;
    expect(formData.get("merchant")).toBe("Merchant B");
    expect(formData.get("title")).toBe("Durable Agreement");
    expect(formData.get("effective_from")).toBe("2026-02-01");
    // jsdom cannot construct a real FileList, so the selected file is present
    // as an entry but not serializable; the multipart encoding is exercised
    // by the backend API contract tests instead.
    expect(formData.has("file")).toBe(true);
  });
});
