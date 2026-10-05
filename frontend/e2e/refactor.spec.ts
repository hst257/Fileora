import { expect, test } from "@playwright/test";

test("appearance persists and system appearance follows the device", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByLabel("Appearance")).toHaveValue("dark");
  await page.getByLabel("Appearance").selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const dark = await page.evaluate(
    () => getComputedStyle(document.body).backgroundColor,
  );
  await page.reload();
  await expect(page.getByLabel("Appearance")).toHaveValue("dark");
  await page.getByLabel("Appearance").selectOption("light");
  expect(
    await page.evaluate(() => getComputedStyle(document.body).backgroundColor),
  ).not.toBe(dark);
  await page.getByLabel("Appearance").selectOption("system");
  await page.emulateMedia({ colorScheme: "dark" });
  expect(
    await page.evaluate(() => getComputedStyle(document.body).backgroundColor),
  ).toBe(dark);
  await page.emulateMedia({ colorScheme: "light" });
  expect(
    await page.evaluate(() => getComputedStyle(document.body).backgroundColor),
  ).not.toBe(dark);
});

test("compact preview contains focus and restores the selected result on Escape", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("Search your files").fill("virtual memory");
  await page.getByRole("button", { name: "Images", exact: true }).click();
  await page.getByLabel("Run search").click();
  const result = page.locator(".result-row").first();
  await expect(result).toBeVisible();
  await result.click();
  const dialog = page.getByRole("dialog", { name: "File preview" });
  await expect(dialog).toBeVisible();
  expect(
    await page
      .locator(".app-shell")
      .evaluate((element) => (element as HTMLElement).inert),
  ).toBe(true);
  await expect(
    dialog.getByRole("link", { name: "Open original" }),
  ).toBeVisible();
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    expect(
      await dialog.evaluate((element) =>
        element.contains(document.activeElement),
      ),
    ).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(result).toBeFocused();
  expect(
    await page
      .locator(".app-shell")
      .evaluate((element) => (element as HTMLElement).inert),
  ).toBe(false);
});

test("folder navigation applies its scope and can return to all folders", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Search your files").fill("semaphores");
  await page.getByLabel("Run search").click();
  await expect(page.locator(".result-row").first()).toBeVisible();
  const request = page.waitForRequest(
    (request) =>
      request.url().endsWith("/search") && request.method() === "POST",
  );
  await page.locator(".folder-nav").first().click();
  const payload = (await request).postDataJSON();
  expect(payload.filters.root_id).toBeGreaterThan(0);
  await expect(page.locator(".active-scope")).toBeVisible();
  await expect(page.locator(".result-row").first()).toBeVisible();
  const reset = page.waitForRequest(
    (request) =>
      request.url().endsWith("/search") && request.method() === "POST",
  );
  await page.getByLabel("Search all folders").click();
  expect((await reset).postDataJSON().filters.root_id).toBeUndefined();
  await expect(page.locator(".active-scope")).toHaveCount(0);
});

test("light and dark layouts fit narrow phones, tablets and desktop", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const appearance of ["light", "dark"]) {
      await page.getByLabel("Appearance").selectOption(appearance);
      for (const name of ["Search", "My library"]) {
        await page
          .getByRole("navigation", { name: "Main navigation" })
          .getByRole("button", { name: new RegExp(`^${name}`) })
          .click();
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth,
          ),
        ).toBe(true);
      }
    }
  }
  await page.keyboard.press("Control+k");
  await expect(page.getByLabel("Search your files")).toBeFocused();
});
