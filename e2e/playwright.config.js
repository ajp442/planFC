// Browser tests for the PWA, run against a live stack (Caddy -> gunicorn ->
// Postgres) rather than Django's test client, because the service worker,
// manifest and offline behaviour only exist in a real browser.
const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: ".",
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    // localhost counts as a secure context, so the service worker registers
    // over plain HTTP here just as it does in development.
    baseURL: process.env.BASE_URL || "http://localhost:8080",
    trace: "retain-on-failure",
  },
  // Device emulation sets viewport, pixel ratio, touch, user agent and, for
  // Chromium, mobile layout. The engines are real (Blink as in Android Chrome,
  // WebKit as in iOS Safari) but these are desktop Linux builds, not the phone
  // browsers themselves: installing, standalone mode and iOS storage limits
  // still need a real device.
  projects: [
    { name: "android", use: { ...devices["Pixel 7"] } },
    { name: "ios", use: { ...devices["iPhone 15"] } },
  ],
});
