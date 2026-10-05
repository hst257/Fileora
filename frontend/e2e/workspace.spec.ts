import { expect, test } from "@playwright/test";

test("search, source preview, filters and library status", async ({ page }) => {
  const failures: string[] = [];
  page.on("pageerror", (error) => failures.push(error.message));
  await page.goto("/");
  await expect(page.getByText("Local service connected")).toBeVisible();
  await page.screenshot({
    animations: "disabled",
    path: "../docs/screenshots/workspace.png",
    fullPage: false,
  });
  await page.getByLabel("Search your files").fill("semaphore critical section");
  await page.getByLabel("Run search").click();
  const result = page
    .locator(".result-row")
    .filter({ hasText: "semaphores.md" })
    .first();
  await expect(result).toBeVisible({ timeout: 30000 });
  await result.click();
  await expect(page.getByLabel("File preview")).toBeVisible();
  await expect(page.getByRole("link", { name: "Open original" })).toBeVisible();
  await page.screenshot({
    animations: "disabled",
    path: "../docs/screenshots/search.png",
    fullPage: false,
  });
  await page.getByRole("button", { name: "Close preview" }).click();
  await page.getByRole("button", { name: "Filters", exact: true }).click();
  await page.getByLabel("Retrieval mode").selectOption("lexical");
  await page.getByLabel("Search your files").fill("zzzznonexistenttoken");
  await page.getByLabel("Run search").click();
  await expect(page.getByText("No matches this time.")).toBeVisible();
  await page.getByRole("button", { name: /My library/ }).click();
  await expect(page.getByText("A home for what you know.")).toBeVisible();
  await expect(page.getByLabel("Folder path")).toBeVisible();
  await page.screenshot({
    animations: "disabled",
    path: "../docs/screenshots/library.png",
    fullPage: true,
  });
  await page.keyboard.press("Control+k");
  await expect(page.getByLabel("Search your files")).toBeFocused();
  expect(failures).toEqual([]);
});

test("mobile fits without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByLabel("Search your files")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    animations: "disabled",
    path: "../docs/screenshots/mobile.png",
    fullPage: false,
  });
  await page.getByRole("button", { name: /My library/ }).click();
  await expect(
    page.getByRole("switch", { name: "Watch folders" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    animations: "disabled",
    path: "../docs/screenshots/library-mobile.png",
    fullPage: true,
  });
});

test("hybrid keywords do not fill unrelated file-type tabs", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Search your files").fill("Dijkstra");
  await page.getByLabel("Run search").click();
  await expect(
    page.locator(".result-row").filter({ hasText: "Dijkstra.java" }),
  ).toBeVisible();
  await expect(page.getByText("Term match").first()).toBeVisible();
  await page.getByRole("button", { name: "Code", exact: true }).click();
  await expect(
    page.locator(".result-row").filter({ hasText: "Dijkstra.java" }),
  ).toBeVisible();
  for (const tab of ["PDFs", "Images"]) {
    await page.getByRole("button", { name: tab, exact: true }).click();
    await expect(page.getByText("No matches this time.")).toBeVisible();
    await expect(page.locator(".result-row")).toHaveCount(0);
  }
  await page.getByLabel("Search your files").fill("semaphores");
  await page.getByLabel("Run search").click();
  await expect(page.locator(".result-row")).toHaveCount(1);
  await expect(page.getByText("Term match")).toBeVisible();
});

test("API documentation loads entirely from localhost", async ({ page }) => {
  const remote: string[] = [];
  page.on("request", (request) => {
    if (
      /^https?:/.test(request.url()) &&
      new URL(request.url()).hostname !== "127.0.0.1"
    )
      remote.push(request.url());
  });
  await page.goto("/api/docs");
  await expect(page.locator(".swagger-ui .info .title")).toContainText(
    "Fileora local API",
  );
  expect(remote).toEqual([]);
});

test("automatic updates can be changed from Library and survive a page reload", async ({
  page,
}) => {
  await page.goto("/");
  const before = await (await page.request.get("/api/v1/index/watch")).json();
  const session = await (await page.request.get("/api/v1/session")).json();
  try {
    await page.getByRole("button", { name: /My library/ }).click();
    const toggle = page.getByRole("switch", { name: "Watch folders" });
    await expect(toggle).toBeEnabled();
    await toggle.setChecked(true);
    await expect(toggle).toBeChecked();
    await expect(page.getByText(/^Watching \d+ folders?\.$/)).toBeVisible();
    await page.reload();
    await page.getByRole("button", { name: /My library/ }).click();
    await expect(toggle).toBeChecked();
    await toggle.setChecked(false);
    await expect(toggle).not.toBeChecked();
    await expect(page.getByText(/Automatic updates are off/)).toBeVisible();
  } finally {
    await page.request.put("/api/v1/index/watch", {
      headers: { "X-Fileora-Token": session.token },
      data: { enabled: before.enabled },
    });
  }
});

test("audio evidence seeks the original recording to its timestamp", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Audio", exact: true }).click();
  await page
    .getByLabel("Search your files")
    .fill("translation lookaside buffer");
  await page.getByLabel("Run search").click();
  const result = page
    .locator(".result-row")
    .filter({ hasText: "computer_science_lecture.wav" })
    .first();
  await expect(result).toBeVisible({ timeout: 30000 });
  await result.click();
  const audio = page.locator("audio");
  await expect(audio).toBeVisible();
  await expect
    .poll(() => audio.evaluate((element) => element.duration))
    .toBeGreaterThan(70);
  await expect
    .poll(() => audio.evaluate((element) => element.currentTime))
    .toBeGreaterThan(30);
});
