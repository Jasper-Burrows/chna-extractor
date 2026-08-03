import { expect, test } from "@playwright/test";

const job = {
  id: "e2e-demo",
  status: "succeeded",
  progress: 100,
  message: "Extraction complete",
  mode: "offline",
  source_filename: "synthetic_chna.pdf",
  created_at: "2026-08-03T02:00:00Z",
  updated_at: "2026-08-03T02:00:01Z",
  links: {},
};

const result = {
  job_id: job.id,
  source_file: job.source_filename,
  completed_at: job.updated_at,
  usage: { latency_ms: 1, estimated_cost_usd: 0 },
  warnings: [{
    code: "offline_demo",
    message: "Deterministic output from the bundled synthetic fixture; no AI service was called.",
    severity: "info",
  }],
  records: [{
    hospital_name: "Example County Community Hospital",
    hospital_system: "Civic Health Collaborative (Synthetic)",
    report_year: 2025,
    address: "100 Example Way",
    city: "Demo City",
    state: "CA",
    postal_code: "90000",
    latitude: null,
    longitude: null,
    capacity: 128,
    urban_rural: "urban",
    health_priorities: ["Access to primary care", "Behavioral health", "Nutrition and physical activity"],
    assessment_methodologies: ["Community survey", "Stakeholder interviews", "Secondary data review"],
    warnings: [],
    evidence: {
      hospital_name: [{ page: 1, excerpt: "Example County Community Hospital", confidence: 1, method: "document_text" }],
      hospital_system: [{ page: 1, excerpt: "Civic Health Collaborative (Synthetic)", confidence: 1, method: "document_text" }],
      report_year: [{ page: 1, excerpt: "2025 Community Health Needs Assessment", confidence: 1, method: "document_text" }],
      address: [{ page: 1, excerpt: "Address: 100 Example Way, Demo City, CA 90000", confidence: 1, method: "document_text" }],
      capacity: [{ page: 1, excerpt: "Licensed bed capacity: 128", confidence: 1, method: "document_text" }],
      urban_rural: [{ page: 1, excerpt: "Service area classification: Urban", confidence: 1, method: "document_text" }],
      health_priorities: [{ page: 1, excerpt: "Priorities: Access to primary care; Behavioral health; Nutrition and physical activity", confidence: 1, method: "document_text" }],
      assessment_methodologies: [{ page: 1, excerpt: "Methods: Community survey; Stakeholder interviews; Secondary data review", confidence: 1, method: "document_text" }],
    },
  }],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/config", async (route) => route.fulfill({ json: { offline_demo_available: true, live_available: false, max_upload_mb: 20, model: "gpt-5.6-terra" } }));
  await page.route("**/api/v1/extractions/demo", async (route) => route.fulfill({ status: 202, json: { ...job, status: "queued", progress: 0, message: "Queued" } }));
  await page.route(`**/api/v1/extractions/${job.id}/events`, async (route) => route.fulfill({ json: { items: [{ sequence: 1, stage: "extracting_text", message: "Reading pages", progress: 60, created_at: job.created_at }] } }));
  await page.route(`**/api/v1/extractions/${job.id}/result`, async (route, request) => {
    if (request.method() === "PATCH") {
      const body = request.postDataJSON() as { records: typeof result.records };
      return route.fulfill({
        json: {
          ...result,
          records: body.records.map((record, index) => ({
            ...result.records[index],
            ...record,
          })),
        },
      });
    }
    return route.fulfill({ json: result });
  });
  await page.route(`**/api/v1/extractions/${job.id}`, async (route) => route.fulfill({ json: job }));
});

test("offline demo reaches evidence-backed editable results", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /turn a health report/i })).toBeVisible();
  if (process.env.CAPTURE_SCREENSHOTS && testInfo.project.name === "mocked-chromium") {
    await page.screenshot({ path: "public/screenshots/chna-lens-upload.png", fullPage: true });
  }
  await page.getByRole("button", { name: /try sample report/i }).click();
  await expect(page.getByRole("heading", { name: /review the findings/i })).toBeVisible();
  if (process.env.CAPTURE_SCREENSHOTS && testInfo.project.name === "mocked-chromium") {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(100);
    await page.screenshot({ path: "public/screenshots/chna-lens-review.png", fullPage: true });
  }
  await expect(page.getByRole("textbox", { name: /hospital name/i })).toHaveValue("Example County Community Hospital");
  const firstEvidence = page.locator("details.evidence-disclosure").first();
  await firstEvidence.locator("summary").click();
  await expect(firstEvidence).toHaveAttribute("open", "");
  await expect(firstEvidence.locator("blockquote")).toContainText("Example County Community Hospital");
  await page.getByRole("textbox", { name: /hospital name/i }).fill("Example County Reviewed Hospital");
  await page.getByRole("button", { name: /save review/i }).click();
  await expect(page.getByText(/review saved just now/i)).toBeVisible();
});
