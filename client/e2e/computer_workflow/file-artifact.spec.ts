import { expect, test } from "@playwright/test";

test("uploads a source and receives a durable Bot artifact", async ({ page, request }) => {
  test.setTimeout(120_000);
  const name = `Filewright ${Date.now()}`;
  const created = await request.post("http://localhost:8000/api/v1/bots", {
    data: {
      name,
      role_title: "Document craftsperson",
      description: "Turns source files into durable results.",
      system_instructions: "Read source files carefully and produce concise documents.",
      avatar_value: "F",
    },
  });
  expect(created.ok()).toBeTruthy();

  await page.goto("/");
  await page.getByText(name, { exact: true }).first().click();
  await page.getByLabel("Choose files").setInputFiles({
    name: "field-notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("durable upload evidence\n"),
  });
  await expect(page.getByText("field-notes.txt", { exact: true })).toBeVisible();

  await page.getByRole("textbox", { name: "Message", exact: true }).fill("Create a concise report from this source.");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText("Result.md", { exact: true })).toBeVisible({ timeout: 90_000 });
  const resultHref = await page.getByRole("link", { name: "Download Result.md" }).getAttribute("href");
  expect(resultHref).toBeTruthy();
  const result = await request.get(resultHref!);
  expect((await result.text()).startsWith("# Result")).toBeTruthy();

  await page.getByRole("button", { name: "Files", exact: true }).click();
  const drawer = page.getByRole("complementary", { name: "Conversation files" });
  await expect(drawer.getByText("field-notes.txt", { exact: true })).toBeVisible();
  await expect(drawer.getByText("Result.md", { exact: true })).toBeVisible();
  const href = await drawer.getByRole("link", { name: "Download field-notes.txt" }).getAttribute("href");
  expect(href).toBeTruthy();
  const downloaded = await request.get(href!);
  expect(await downloaded.body()).toEqual(Buffer.from("durable upload evidence\n"));

  await page.reload();
  await page.getByText(name, { exact: true }).first().click();
  await page.getByRole("button", { name: "Files", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Conversation files" }).getByText("field-notes.txt", { exact: true })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Conversation files" }).getByText("Result.md", { exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/v02-files-artifacts.png", fullPage: true });
});
