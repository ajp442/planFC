const { test, expect } = require("@playwright/test");

// The Members area in a real browser. The Django tests (accounts/tests_members.py)
// cover the rules: who is refused, what each action changes, how invitation
// links expire. These check that an admin can actually get through the pages
// on a phone-sized screen, including the detour to re-enter their password.
//
// create-member.sh makes the two accounts and passes their credentials in.
const EMAIL = process.env.E2E_EMAIL;
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL;
const PASSWORD = process.env.E2E_PASSWORD;

async function signIn(page, email) {
  await page.goto("/accounts/login/");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page.locator(".me")).toBeVisible();
}

test.describe("members area", () => {
  test.skip(!EMAIL || !ADMIN_EMAIL || !PASSWORD, "Set E2E_EMAIL, E2E_ADMIN_EMAIL and E2E_PASSWORD");

  test("a member has no Members link and is refused the page", async ({ page }) => {
    await signIn(page, EMAIL);
    await expect(page.locator("#admin_menu")).toHaveCount(0);

    const response = await page.goto("/members/");
    expect(response.status()).toBe(403);
    await expect(page.getByRole("heading", { name: "Admins only" })).toBeVisible();
  });

  test("an admin adds a member, then removes them again", async ({ page }, testInfo) => {
    // A fresh address per run and device, so reruns never collide.
    const email = `e2e-invited-${testInfo.project.name}-${Date.now()}@example.com`;
    await signIn(page, ADMIN_EMAIL);
    // The Admin dropdown in the header is the only way in for an installed app.
    await page.locator("#admin_menu summary").click();
    await page.locator("#admin_menu").getByRole("link", { name: "Members", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Members" })).toBeVisible();

    await page.getByRole("link", { name: "Add a member" }).click();
    await page.getByLabel("First name").fill("Invited");
    await page.getByLabel("Last name").fill("Player");
    await page.getByLabel("Email").fill(email);
    await page.getByRole("button", { name: "Add and send the invitation" }).click();
    await expect(page.getByText("an invitation was sent")).toBeVisible();
    await expect(page.getByRole("button", { name: "Send the invitation again" })).toBeVisible();

    // They show up in a search of the list.
    await page.goto("/members/");
    await page.getByLabel("Search members").fill(email);
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.locator(".member-list li")).toHaveCount(1);
    await page.locator(".member-list a").click();

    // Deleting asks for the admin's password again first.
    await page.getByRole("link", { name: "Delete this account" }).click();
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Confirm" }).click();
    await page.getByRole("button", { name: /^Delete Invited Player/ }).click();
    await expect(page.getByText("account has been deleted")).toBeVisible();

    await page.goto("/members/activity/");
    await expect(page.getByText(`Account deleted: Invited Player <${email}>`)).toBeVisible();
  });
});
