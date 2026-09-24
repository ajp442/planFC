const { test, expect } = require("@playwright/test");

// Resolves once a service worker controls the page. clients.claim() in sw.js
// hands control to a freshly installed worker without a reload.
async function waitForServiceWorkerControl(page) {
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
}

test("page renders with the database connected", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "planFC" })).toBeVisible();
  await expect(page.getByText("Database connected")).toBeVisible();
});

test("service worker registers with whole-site scope", async ({ page, baseURL }) => {
  await page.goto("/");
  await expect(page.locator("#sw_text")).toHaveText(
    `Service worker registered (scope ${new URL("/", baseURL).href})`
  );
  await waitForServiceWorkerControl(page);
});

test("manifest and every icon it names are served", async ({ page, request }) => {
  await page.goto("/");
  const href = await page.locator('link[rel="manifest"]').getAttribute("href");
  const response = await request.get(href);
  expect(response.ok()).toBeTruthy();
  const manifest = await response.json();

  for (const icon of manifest.icons) {
    const iconResponse = await request.get(icon.src);
    expect(iconResponse.ok(), icon.src).toBeTruthy();
    expect(iconResponse.headers()["content-type"]).toBe("image/png");
  }
});

test("apple-touch-icon is served", async ({ page, request }) => {
  await page.goto("/");
  const href = await page.locator('link[rel="apple-touch-icon"]').getAttribute("href");
  const response = await request.get(href);
  expect(response.ok()).toBeTruthy();
});

test("caches the page for offline use", async ({ page, baseURL }) => {
  await page.goto("/");
  await waitForServiceWorkerControl(page);
  // The first load happened before the worker existed, so / is not cached
  // yet; a reload through the worker puts it there.
  await page.reload();

  const cached = await page.evaluate(async () => {
    const urls = [];
    for (const key of await caches.keys()) {
      const cache = await caches.open(key);
      urls.push(...(await cache.keys()).map((request) => request.url));
    }
    return urls;
  });
  expect(cached).toContain(new URL("/", baseURL).href);
});

test("reloads offline from the service worker cache", async ({ page, context }, testInfo) => {
  // Playwright's WebKit fails an offline navigation before the service worker
  // sees it (setOffline and route.abort alike), so only Chromium can check
  // the fallback itself. The test above shows WebKit caches the page.
  test.skip(testInfo.project.name === "ios", "WebKit offline emulation bypasses the service worker");

  await page.goto("/");
  await waitForServiceWorkerControl(page);
  await page.reload();

  await context.setOffline(true);
  await page.reload();
  await expect(page.getByRole("heading", { name: "planFC" })).toBeVisible();
});

test("reports running in a browser tab", async ({ page }) => {
  await page.goto("/");
  // Installed display modes cannot be emulated; this checks the script ran
  // and took the browser-tab branch.
  await expect(page.locator("#mode_text")).toHaveText(
    "Running in a browser tab (display-mode: browser)"
  );
});

test("iOS gets the Add to Home Screen hint, Android does not", async ({ page }, testInfo) => {
  await page.goto("/");
  const hint = page.locator("#ios_hint");
  if (testInfo.project.name === "ios") {
    await expect(hint).toBeVisible();
  } else {
    await expect(hint).toBeHidden();
  }
});
