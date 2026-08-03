import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { vi } from "vitest";
import { App } from "./App";
import { configFixture, jobFixture, resultFixture } from "./test/fixtures";

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
}

function mockHappyApi() {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/api/v1/config")) return json(configFixture);
    if (url.endsWith("/api/v1/extractions/demo") && init?.method === "POST") {
      return json({ ...jobFixture, status: "queued", progress: 0, message: "Queued" }, 202);
    }
    if (url.endsWith(`/api/v1/extractions/${jobFixture.id}/events`)) {
      return json({ items: [{ sequence: 1, stage: "extracting_text", message: "Reading report pages", progress: 55, created_at: jobFixture.created_at }] });
    }
    if (url.endsWith(`/api/v1/extractions/${jobFixture.id}/result`) && init?.method === "PATCH") {
      const body = JSON.parse(String(init.body)) as { records: typeof resultFixture.records };
      return json({
        ...resultFixture,
        records: body.records.map((record, index) => ({
          ...resultFixture.records[index],
          ...record,
        })),
      });
    }
    if (url.endsWith(`/api/v1/extractions/${jobFixture.id}/result`)) return json(resultFixture);
    if (url.endsWith(`/api/v1/extractions/${jobFixture.id}`)) return json(jobFixture);
    throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
  }));
}

describe("CHNA Lens", () => {
  it("renders an accessible upload experience", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(configFixture)));
    const { container } = renderApp();
    expect(screen.getByRole("heading", { name: /turn a health report/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /drop a pdf here/i })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /try sample report/i })).toBeEnabled());
    const report = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(report.violations).toHaveLength(0);
  });

  it("runs the synthetic demo through review and saves an edit", async () => {
    mockHappyApi();
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: /try sample report/i }));
    expect(await screen.findByRole("heading", { name: /review the findings/i }, { timeout: 3_000 })).toBeInTheDocument();

    const name = screen.getByRole("textbox", { name: /hospital name/i });
    await user.clear(name);
    await user.type(name, "Example County Reviewed Hospital");
    const save = screen.getByRole("button", { name: /save review/i });
    expect(save).toBeEnabled();
    await user.click(save);
    await waitFor(() => expect(screen.getByText(/review saved just now/i)).toBeInTheDocument());
  });

  it("rejects a non-PDF before upload", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(configFixture)));
    renderApp();
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    fireEvent.change(input as HTMLInputElement, { target: { files: [new File(["notes"], "notes.txt", { type: "text/plain" })] } });
    expect(screen.getByRole("alert")).toHaveTextContent(/choose a pdf report/i);
  });
});
