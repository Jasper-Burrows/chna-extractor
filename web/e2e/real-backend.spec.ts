import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

test("bundled report completes against the real API and exports reviewed data", async ({ page }) => {
  await page.goto("/");
  const demoButton = page.getByRole("button", { name: /try sample report/i });
  await expect(demoButton).toBeEnabled();
  await demoButton.click();

  await expect(page.getByRole("heading", { name: /review the findings/i })).toBeVisible({ timeout: 15_000 });
  const hospitalName = page.getByRole("textbox", { name: /hospital name/i });
  await expect(hospitalName).toHaveValue("Example County Community Hospital");
  await expect(page.getByText(/deterministic output from the bundled synthetic fixture/i)).toBeVisible();

  const firstEvidence = page.locator("details.evidence-disclosure").first();
  await firstEvidence.locator("summary").click();
  await expect(firstEvidence.locator("blockquote")).toContainText("Example County Community Hospital");

  await hospitalName.fill("Example County Reviewed Hospital");
  await page.getByRole("button", { name: /save review/i }).click();
  await expect(page.getByText(/review saved just now/i)).toBeVisible();

  const [jsonDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "JSON" }).click(),
  ]);
  expect(jsonDownload.suggestedFilename()).toMatch(/\.json$/);
  const jsonPath = await jsonDownload.path();
  expect(jsonPath).not.toBeNull();
  const exportedJson = JSON.parse(await readFile(jsonPath as string, "utf8")) as {
    records: Array<{ hospital_name: string }>;
  };
  expect(exportedJson.records[0]?.hospital_name).toBe("Example County Reviewed Hospital");

  const [csvDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "CSV" }).click(),
  ]);
  expect(csvDownload.suggestedFilename()).toMatch(/\.csv$/);
  const csvPath = await csvDownload.path();
  expect(csvPath).not.toBeNull();
  const exportedCsv = await readFile(csvPath as string, "utf8");
  expect(exportedCsv).toContain("Example County Reviewed Hospital");
  expect(exportedCsv).toContain("Hospital Name");
});
