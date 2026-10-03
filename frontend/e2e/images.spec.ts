import { expect, test } from "@playwright/test";

test("image OCR evidence highlights actual words and leaves unrelated keyword tabs empty", async ({
  page,
}) => {
  const remote: string[] = [];
  page.on("request", (request) => {
    if (
      /^https?:/.test(request.url()) &&
      new URL(request.url()).hostname !== "127.0.0.1"
    )
      remote.push(request.url());
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Images", exact: true }).click();
  await page.getByLabel("Search your files").fill("virtual memory");
  await page.getByLabel("Run search").click();
  const result = page.locator(".result-row").filter({ hasText: "paging.png" });
  await expect(result).toBeVisible({ timeout: 45000 });
  await result.click();
  await expect(
    page.getByRole("img", { name: "Preview of paging.png" }),
  ).toBeVisible();
  const overlay = page.getByRole("img", { name: "Matching words in image" });
  await expect(overlay).toBeVisible();
  await expect(overlay.locator("rect").first()).toBeAttached();
  await page.screenshot({
    path: "../docs/screenshots/images.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Hide highlights" }).click();
  await expect(overlay).toHaveCount(0);
  await page.getByRole("button", { name: "Show highlights" }).click();
  await expect(overlay).toBeVisible();
  await page.getByRole("button", { name: "Close preview" }).click();
  await page.getByLabel("Search your files").fill("zzzznonexistentimagetoken");
  await page.getByLabel("Run search").click();
  await expect(page.getByText("No matches this time.")).toBeVisible();
  await page.getByRole("button", { name: /My library/ }).click();
  const capabilities = page.getByRole("region", {
    name: "Image search capabilities",
  });
  await expect(capabilities.getByText("Available locally")).toHaveCount(2);
  expect(remote).toEqual([]);
});

test("image OCR highlights fit a mobile preview", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Images", exact: true }).click();
  await page.getByLabel("Search your files").fill("virtual memory");
  await page.getByLabel("Run search").click();
  await page.locator(".result-row").filter({ hasText: "paging.png" }).click();
  const image = page.getByRole("img", { name: "Preview of paging.png" });
  const overlay = page.getByRole("img", { name: "Matching words in image" });
  await expect(overlay).toBeVisible();
  const imageBox = await image.boundingBox(),
    overlayBox = await overlay.boundingBox();
  expect(imageBox).not.toBeNull();
  expect(overlayBox).not.toBeNull();
  expect(Math.abs(imageBox!.width - overlayBox!.width)).toBeLessThan(1);
  expect(Math.abs(imageBox!.height - overlayBox!.height)).toBeLessThan(1);
  await page.screenshot({
    path: "../docs/screenshots/images-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
