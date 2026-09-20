import { expect, test } from "@playwright/test";

test("renders approvals, steering, takeover, and audit coherently", async ({ page, request }) => {
  // Provisioning a fresh headed Docker sandbox can take longer on a cold host.
  test.setTimeout(180_000);
  const name = `Safetywright ${Date.now()}`;
  const created = await request.post("http://localhost:8000/api/v1/bots", {
    data: {
      name,
      role_title: "Controlled publisher",
      description: "Demonstrates understandable and controllable work.",
      system_instructions: "Follow steering and stop at consequential action boundaries.",
      avatar_value: "S",
    },
  });
  expect(created.ok()).toBeTruthy();

  await page.goto("/");
  await page.getByText(name, { exact: true }).first().click();

  await page.getByRole("textbox", { name: "Message", exact: true }).fill("/action publish draft release notes");
  await page.getByRole("button", { name: "Send message" }).click();
  const firstApproval = page.getByTestId("approval-card").last();
  await expect(firstApproval.getByText("Needs your approval")).toBeVisible({ timeout: 20_000 });
  await expect(firstApproval.getByText(/draft release notes/)).toBeVisible();
  await page.getByRole("textbox", { name: "Message", exact: true }).fill("Use the concise release format");
  await page.getByRole("button", { name: "Steer active work" }).click();
  await expect(page.getByText("New direction received")).toBeVisible();
  await firstApproval.getByRole("button", { name: "Deny" }).click();
  await expect(firstApproval.getByText("denied", { exact: true })).toBeVisible();

  await page.getByRole("textbox", { name: "Message", exact: true }).fill("/action publish approved release notes");
  await page.getByRole("button", { name: "Send message" }).click();
  const secondApproval = page.getByTestId("approval-card").last();
  await expect(secondApproval.getByText(/approved release notes/)).toBeVisible({ timeout: 20_000 });
  await secondApproval.getByRole("button", { name: "Approve exact action" }).click();
  await expect(page.getByText(/approved publish action completed once/i)).toBeVisible({ timeout: 20_000 });

  await page.getByRole("button", { name: "Activity and audit" }).click();
  const activity = page.getByRole("complementary", { name: "Activity and audit details" });
  await expect(activity.getByText(/approval · approved/i)).toBeVisible();
  await expect(activity.getByText(/action · succeeded/i)).toBeVisible();
  await activity.getByRole("button", { name: "Close activity" }).click();

  await page.getByRole("button", { name: "Computer", exact: true }).click();
  const preview = page.getByRole("complementary", { name: "Computer preview" });
  await expect(preview).toBeVisible({ timeout: 30_000 });
  const viewerFrame = page.frameLocator('iframe[title="Live computer"]');
  await expect(viewerFrame.locator("#noVNC_container canvas")).toBeVisible({ timeout: 30_000 });
  await expect(viewerFrame.locator("#noVNC_status")).toContainText(/connected/i, { timeout: 30_000 });
  await preview.getByRole("button", { name: "Take over" }).click();
  await expect(preview.getByText("You have exclusive control. Agent input is paused.")).toBeVisible();
  await expect(viewerFrame.locator("#noVNC_status")).toContainText(/connected/i, { timeout: 30_000 });
  await preview.getByRole("button", { name: "Return control" }).click();
  await expect(preview.getByText("Bot has control")).toBeVisible();
  await expect(viewerFrame.locator("#noVNC_status")).toContainText(/connected/i, { timeout: 30_000 });
  await expect(page.locator(".conversation-title").getByText("Ready", { exact: true })).toBeVisible();
  await preview.getByRole("button", { name: "Close computer preview" }).click();

  await page.getByRole("button", { name: "Activity and audit" }).click();
  const controlActivity = page.getByRole("complementary", { name: "Activity and audit details" });
  await expect(controlActivity.getByText(/computer · takeover/i)).toBeVisible();
  await expect(controlActivity.getByText(/computer · control returned/i)).toBeVisible();
  await controlActivity.getByRole("button", { name: "Close activity" }).click();

  await page.screenshot({ path: "test-results/v03-safety-control.png", fullPage: true });
  await page.reload();
  await page.getByText(name, { exact: true }).first().click();
  await expect(page.getByTestId("approval-card")).toHaveCount(2);
});
