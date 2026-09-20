import { expect, test } from "@playwright/test";

test("-5 streams, persists, and cancels conversation work", async ({ page }) => {
  const name = `Fieldnote ${Date.now()}`;
  await page.goto("/");
  await page.getByRole("button", { name: "New Bot" }).click();
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Primary job").fill("Field research editor");
  await page.getByLabel(/How should .* work/).fill("Always use the phrase field signal and keep answers concise.");
  await page.getByRole("button", { name: "Create Bot" }).click();
  await page.getByRole("textbox", { name: "Message", exact: true }).fill("What should I capture?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".message.bot").filter({ hasText: /field signal/i }).last()).toBeVisible({ timeout: 20_000 });
  await page.reload();
  await page.getByRole("button", { name: new RegExp(name) }).click();
  await expect(page.getByText("What should I capture?")).toBeVisible();
  await expect(page.locator(".message.bot").filter({ hasText: /field signal/i }).last()).toBeVisible();
  await page.getByRole("textbox", { name: "Message", exact: true }).fill("Give me a long slow response.");
  await page.getByRole("button", { name: "Send message" }).click();
  await page.getByRole("button", { name: "Stop response" }).click();
  // A live provider can finish between rendering the stop control and the
  // cancellation request reaching the API. Both are valid terminal outcomes;
  // deterministic cancellation semantics are covered by the API tests.
  await expect(page.getByText(/^(Stopped|Finished)$/)).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: new RegExp(name) }).click();
  await expect(page.getByText("Give me a long slow response.")).toBeVisible();
});
