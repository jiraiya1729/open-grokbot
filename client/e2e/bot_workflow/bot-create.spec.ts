import { expect, test } from "@playwright/test";

test("creates, edits, pins, and archives an arbitrary Bot", async ({ page }) => {
  test.setTimeout(60_000);
  const name = `Cartographer ${Date.now()}`;
  await page.goto("/");
  await page.getByRole("button", { name: "New Bot" }).click();
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Primary job").fill("Neighborhood accessibility mapper");
  await page.getByRole("button", { name: "Advanced" }).click();
  await page.getByLabel("Description").fill("Maps routes without assuming how people travel.");
  await page.getByLabel(/How should .* work/).fill("Ask about mobility needs and explain tradeoffs plainly.");
  await page.getByRole("button", { name: "Create Bot" }).click();
  await expect(page.getByRole("heading", { level: 1, name, exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Edit Bot" }).click();
  await page.getByLabel("Primary job").fill("Inclusive route researcher");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Inclusive route researcher").first()).toBeVisible();
  await page.getByRole("button", { name: "More options" }).click();
  await page.locator(".header-menu").getByRole("button", { name: "Archive Bot" }).click();
  await expect(page.getByText(name)).toHaveCount(0);
});
