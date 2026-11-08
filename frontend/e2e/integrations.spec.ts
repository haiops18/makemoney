import { expect, test } from '@playwright/test';

test('real API: Owner stores an integration once and the token never comes back', async ({ page, request }) => {
  test.skip(!process.env.E2E_STEP6, 'Requires isolated Step 6 Compose runtime (credential encryption key)');
  expect((await request.get('/api/v1/integrations')).status()).toBe(401);
  const password = process.env.E2E_ADMIN_PASSWORD || 'change-me-admin-password';
  await page.goto('/integrations');
  await page.getByLabel('Tên đăng nhập Admin').fill('admin');
  await page.getByLabel('Mật khẩu Admin').fill(password);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  const label = `ACCESSTRADE ${Date.now()}`;
  const token = `e2e-secret-${Date.now()}`;
  await page.getByLabel('Loại').selectOption('ACCESSTRADE');
  await page.getByLabel('Tên gợi nhớ (tuỳ chọn)').fill(label);
  await page.getByLabel('Access key').fill(token);
  const saved = page.waitForResponse(response => response.url().endsWith('/api/v1/integrations') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Lưu kết nối' }).click();
  const response = await saved;
  expect(response.status()).toBe(201);
  expect(await response.text()).not.toContain(token);
  await expect(page.getByText('Đã lưu. Token được mã hóa và không hiển thị lại.')).toBeVisible();
  const card = page.getByTestId('integration').filter({ hasText: label });
  await expect(card).toContainText('Token đã lưu (đã mã hóa)');
  await expect(card).toContainText('Chưa kiểm tra');
  await expect(page.getByLabel('Access key')).toHaveValue('');
  await expect(page.locator('body')).not.toContainText(token);
  await page.reload();
  await expect(page.getByTestId('integration').filter({ hasText: label })).toBeVisible();
  page.once('dialog', dialog => void dialog.accept());
  await page.getByTestId('integration').filter({ hasText: label }).getByRole('button', { name: 'Xóa' }).click();
  await expect(page.getByText('Đã xóa kết nối.')).toBeVisible();
  await expect(page.getByTestId('integration').filter({ hasText: label })).toHaveCount(0);
});

test('real API: discovery asks for a search source before any paid search', async ({ page, request }) => {
  test.skip(!process.env.E2E_STEP6, 'Requires isolated Step 6 Compose runtime (credential encryption key)');
  expect((await request.get('/api/v1/discovery')).status()).toBe(401);
  const password = process.env.E2E_ADMIN_PASSWORD || 'change-me-admin-password';
  await page.goto('/discovery');
  await page.getByLabel('Tên đăng nhập Admin').fill('admin');
  await page.getByLabel('Mật khẩu Admin').fill(password);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Tìm cách kiếm tiền' })).toBeVisible();
  await page.getByLabel('Lĩnh vực / chủ đề').fill('thời trang nữ');
  await expect(page.getByRole('link', { name: 'Kết nối Tavily hoặc Brave Search' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Tìm cơ hội' })).toBeDisabled();
  await page.getByRole('link', { name: 'Kết nối Tavily hoặc Brave Search' }).click();
  await expect(page.getByRole('heading', { name: 'Kết nối tài khoản' })).toBeVisible();
});
