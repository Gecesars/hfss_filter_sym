const {test, expect} = require("@playwright/test");

test("engineering modules and simulated VNA are operational", async ({page}) => {
  const browserErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  await page.goto("/");
  await expect(page.locator(".version-block")).toContainText("Version 0.4.0");
  await expect(page.locator("#couplingMatrix tr")).toHaveCount(7);
  await page.locator("#matrixFit").click();
  await expect(page.locator("#operationStatus")).toHaveText(
    "Coupling matrix response updated"
  );

  await page.locator('[data-module="dipmux"]').click();
  await expect(page.locator("#moduleDialog")).toBeVisible();
  await expect(page.locator(".channel-row")).toHaveCount(2);
  await page.locator("#moduleExecute").click();
  await expect(page.locator("#moduleOutput")).toContainText('"channels"');
  await expect(page.locator("#moduleStatus")).toHaveText("Completed");

  await page.locator("#closeModule").click();
  await page.locator('[data-module="cavity"]').click();
  await page.locator("#moduleSecondary").click();
  await expect(page.locator("#moduleOutput")).toContainText('"recipe": "cavity"');
  await page.screenshot({
    path: "data/screenshots/cavity-module-0.4.0.png",
    fullPage: false
  });

  await page.locator("#closeModule").click();
  await page.locator("#openIntegration").click();
  await page.locator('[data-integration-view="vnaView"]').click();
  await page.locator("#connectVna").click();
  await expect(page.locator("#operationStatus")).toHaveText("VNA connected");
  await page.locator("#applySweep").click();
  await expect(page.locator("#operationStatus")).toHaveText("VNA sweep configured");
  await page.locator("#singleSweep").click();
  await expect(page.locator("#operationStatus")).toContainText("VNA sweep acquired");
  await page.locator("#closeVna").click();

  expect(browserErrors).toEqual([]);
});

test("mobile workbench does not overflow horizontally", async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto("/");
  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
});
