import { expect, test } from "@playwright/test";

test("Library saves the transcription choice and restores it on reload", async ({
  page,
}) => {
  await page.goto("/");
  const before = await (await page.request.get("/api/v1/health")).json();
  const session = await (await page.request.get("/api/v1/session")).json();
  try {
    await page.getByRole("button", { name: /My library/ }).click();
    const toggle = page.getByRole("switch", {
      name: "Transcribe audio and video",
    });
    await expect(toggle).toBeEnabled();
    await toggle.setChecked(false);
    await expect(toggle).not.toBeChecked();
    await expect(toggle).toBeEnabled();
    await page.reload();
    await page.getByRole("button", { name: /My library/ }).click();
    await expect(toggle).toBeEnabled();
    await expect(toggle).not.toBeChecked();
    await toggle.setChecked(true);
    await expect(toggle).toBeChecked();
    await expect(toggle).toBeEnabled();
    await page.reload();
    await page.getByRole("button", { name: /My library/ }).click();
    await expect(toggle).toBeEnabled();
    await expect(toggle).toBeChecked();
  } finally {
    await page.request.put("/api/v1/index/media", {
      headers: { "X-Fileora-Token": session.token },
      data: { enabled: before.media_enabled },
    });
  }
});

test("video matches use the sampled frame, highlighted words, and timestamp playback", async ({
  page,
}) => {
  const remote: string[] = [];
  page.on("request", (request) => {
    if (!request.url().startsWith("http://127.0.0.1"))
      remote.push(request.url());
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Video", exact: true }).click();
  await page.getByLabel("Search your files").fill("virtual memory");
  await page.getByLabel("Run search").click();
  await page
    .locator(".result-row")
    .filter({ hasText: "computer_science_lecture.mp4" })
    .first()
    .click();
  const player = page.getByLabel("Video evidence player");
  await expect(player).toBeVisible();
  await expect
    .poll(() =>
      player.evaluate((element: HTMLVideoElement) => element.currentTime),
    )
    .toBeGreaterThan(25);
  await expect(
    page.getByRole("img", { name: "Matching words in image" }),
  ).toBeVisible();
  await expect(page.getByLabel("File preview")).toContainText(
    "This video has no audio track",
  );
  await expect(
    page.getByRole("link", { name: "Open original" }),
  ).toHaveAttribute("href", /#t=\d/);
  await page.screenshot({
    animations: "disabled",
    path: "../docs/screenshots/media.png",
    fullPage: false,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(player).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  expect(remote).toEqual([]);
});

test("audio evidence jumps between matches and media readiness appears in Library", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Audio", exact: true }).click();
  await page
    .getByLabel("Search your files")
    .fill("semaphore counter wait signal");
  await page.getByLabel("Run search").click();
  await page
    .locator(".result-row")
    .filter({ hasText: "computer_science_lecture.wav" })
    .first()
    .click();
  const player = page.getByLabel("Audio evidence player");
  await expect(player).toBeVisible();
  const jumps = page.getByRole("button", { name: /^Jump to/ });
  await expect.poll(() => jumps.count()).toBeGreaterThan(1);
  const last = jumps.last();
  const timestamp = (await last.textContent())!.trim().split(":").map(Number);
  const seconds = timestamp[0] * 60 + timestamp[1];
  await last.click();
  await expect(last).toHaveAttribute("aria-pressed", "true");
  await expect
    .poll(() =>
      player.evaluate((element: HTMLAudioElement) =>
        Math.floor(element.currentTime),
      ),
    )
    .toBe(seconds);
  expect(
    await player.evaluate((element: HTMLAudioElement) => element.paused),
  ).toBeTruthy();
  await page.getByRole("button", { name: /My library/ }).click();
  const status = page.getByLabel("Media search capabilities");
  await expect(
    status.getByText("Available locally", { exact: true }),
  ).toHaveCount(2);
});
