import { expect, test } from "@playwright/test";

async function mockApi(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const json = url.includes("/auth/login") ? { access_token: "test-session", token_type: "bearer", expires_in: 3600 }
      : url.includes("/dashboard") ? { agents_total: 7, agents_enabled: 7, audit_events_last_24h: 0, monthly_budget_usd: 50, timezone: "Asia/Ho_Chi_Minh", external_execution_enabled: false }
      : url.includes("/budgets/current") ? { account: { limit_amount: "50", reserve_amount: "5", currency: "USD" }, committed_amount: "0", available_amount: "45", usage_percent: "0", warning_thresholds_reached: [], hard_stop: false }
      : url.includes("/approvals") ? { items: [] } : [];
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(json) });
  });
}

test("admin login, language switch, unavailable module, and mobile navigation", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByLabel("Tên đăng nhập Admin").fill("admin");
  await expect(page.getByRole("heading", { name: "Đăng nhập Owner" })).toBeVisible();
  await expect(page.getByRole("navigation")).toHaveCount(0);
  await page.getByLabel("Mật khẩu Admin").fill("test-password");
  await page.getByLabel("Mật khẩu Admin").press("Enter");
  await expect(page.getByText("Tổng agent")).toBeVisible();
  await page.getByLabel("Chuyển ngôn ngữ").click();
  await expect(page.getByText("Dashboard")).toBeVisible();
  await page.getByText("Projects", { exact: true }).click();
  await expect(page.getByText("Projects is unavailable")).toBeVisible();
  await page.setViewportSize({ width: 375, height: 667 });
  await page.getByLabel("Open").click();
  await expect(page.getByText("Finance & Budget")).toBeVisible();
});

test("remember me keeps the Owner signed in across a reload until sign-out", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByLabel("Tên đăng nhập Admin").fill("admin");
  await page.getByLabel("Mật khẩu Admin").fill("test-password");
  await page.getByLabel("Ghi nhớ đăng nhập").check();
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await expect(page.getByText("Tổng agent")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Tổng agent")).toBeVisible();
  await page.getByRole("button", { name: "Đăng xuất" }).click();
  await expect(page.getByRole("heading", { name: "Đăng nhập Owner" })).toBeVisible();
  await expect(page.getByLabel("Tên đăng nhập Admin")).toHaveValue("admin");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Đăng nhập Owner" })).toBeVisible();
});

test("without remember me a reload in the same tab keeps the session, a new tab does not", async ({ page, context }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByLabel("Tên đăng nhập Admin").fill("admin");
  await page.getByLabel("Mật khẩu Admin").fill("test-password");
  await page.getByLabel("Mật khẩu Admin").press("Enter");
  await expect(page.getByText("Tổng agent")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Tổng agent")).toBeVisible();
  const other = await context.newPage();
  await mockApi(other);
  await other.goto("/");
  await expect(other.getByRole("heading", { name: "Đăng nhập Owner" })).toBeVisible();
});
