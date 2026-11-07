const { test, expect } = require("@playwright/test");

// Account flows in a real browser. The Django tests cover the rules (who may
// sign in, what deleting removes); these cover what only a browser shows: the
// pages render on both engines, and the service worker keeps private pages
// out of its cache.
//
// Signing in needs a member whose address is already confirmed, because the
// confirmation email goes to the server's log, not to the browser. CI creates
// one before this suite runs (see .github/workflows/ci.yml) and passes its
// credentials as E2E_EMAIL and E2E_PASSWORD; without them the signed-in tests
// are skipped.
const EMAIL = process.env.E2E_EMAIL;
const PASSWORD = process.env.E2E_PASSWORD;

async function signIn(page) {
  await page.goto("/accounts/login/");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page.locator(".me")).toBeVisible();
}

async function cachedUrls(page) {
  return page.evaluate(async () => {
    const urls = [];
    for (const key of await caches.keys()) {
      const cache = await caches.open(key);
      urls.push(...(await cache.keys()).map((request) => new URL(request.url).pathname));
    }
    return urls;
  });
}

test("signed-out home page offers sign-up and sign-in", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Create an account" })).toBeVisible();
  await expect(page.locator(".topbar").getByRole("link", { name: "Sign in" })).toBeVisible();
});

test("signing up asks the member to confirm their email", async ({ page }, testInfo) => {
  // A fresh address per run and device, so reruns never collide.
  const email = `e2e-${testInfo.project.name}-${Date.now()}@example.com`;
  await page.goto("/accounts/signup/");
  await page.getByLabel("First name").fill("Test");
  await page.getByLabel("Last name").fill("Player");
  await page.getByLabel("Email").fill(email);
  await page.locator("#id_password1").fill("a-long-e2e-password-123");
  await page.locator("#id_password2").fill("a-long-e2e-password-123");
  await page.getByRole("button", { name: "Sign Up" }).click();

  await expect(page).toHaveURL(/\/accounts\/confirm-email\/$/);
  await expect(page.getByRole("heading", { name: "Verify Your Email Address" })).toBeVisible();
});

test("the profile page needs sign-in", async ({ page }) => {
  await page.goto("/profile/");
  await expect(page).toHaveURL(/\/accounts\/login\/\?next=(\/|%2F)profile(\/|%2F)$/);
});

test("the offline page is pre-cached", async ({ page }) => {
  await page.goto("/");
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  await expect.poll(() => cachedUrls(page)).toContain("/offline/");
});

test.describe("signed in", () => {
  test.skip(!EMAIL || !PASSWORD, "Set E2E_EMAIL and E2E_PASSWORD for a confirmed member");

  test("header shows the member, and sign-out ends the session", async ({ page }) => {
    await signIn(page);
    await page.locator(".me").click();
    await expect(page).toHaveURL(/\/profile\/$/);

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.locator(".topbar").getByRole("link", { name: "Sign in" })).toBeVisible();
    await page.goto("/profile/");
    await expect(page).toHaveURL(/\/accounts\/login\//);
  });

  test("the service worker never caches a signed-in page", async ({ page }) => {
    await page.goto("/");
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
    await signIn(page);
    // Visit through the worker, which would cache them if allowed to.
    await page.goto("/profile/");
    await page.goto("/");

    const cached = await cachedUrls(page);
    expect(cached).not.toContain("/profile/");
    // / was cached signed out by earlier tests at most; this visit, signed
    // in, must not have replaced it with the member's version.
    const home = await page.evaluate(async () => {
      const hit = await caches.match("/");
      return hit ? hit.text() : "";
    });
    expect(home).not.toContain('class="me"');
  });

  test("offline, a signed-in page falls back to the offline page", async ({ page, context }, testInfo) => {
    // Same WebKit limitation as in pwa.spec.js.
    test.skip(testInfo.project.name === "ios", "WebKit offline emulation bypasses the service worker");
    await page.goto("/");
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
    await signIn(page);
    await page.goto("/profile/");

    await context.setOffline(true);
    await page.reload();
    await expect(page.getByRole("heading", { name: "You're offline" })).toBeVisible();
  });
});
