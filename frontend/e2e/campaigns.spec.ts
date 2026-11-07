import { expect, test } from '@playwright/test';

const SCORES = Object.fromEntries(['market_demand', 'monetization_potential', 'automation_feasibility', 'experiment_cost', 'competitive_advantage', 'scalability', 'evidence_confidence'].map(key => [key, 80]));

test('real API: Owner builds a Level B affiliate campaign without any external action', async ({ page, request }) => {
  test.skip(!process.env.E2E_BASE_URL, 'Requires isolated runtime with real PostgreSQL');
  expect((await request.get('/api/v1/campaigns')).status()).toBe(401);
  const password = process.env.E2E_ADMIN_PASSWORD || 'change-me-admin-password';
  const login = await request.post('/api/v1/auth/login', { data: { username: 'admin', password } });
  expect(login.ok()).toBeTruthy();
  const auth = { Authorization: `Bearer ${(await login.json()).access_token}` };
  const title = `E2E Shopee thời trang nữ ${Date.now()}`;
  const opportunity = await (await request.post('/api/v1/opportunities', { headers: { ...auth, 'Idempotency-Key': crypto.randomUUID() }, data: { title, business_model: 'AFFILIATE' } })).json();
  expect((await request.post(`/api/v1/opportunities/${opportunity.id}/evaluate`, { headers: { ...auth, 'Idempotency-Key': crypto.randomUUID() }, data: { scores: SCORES, risk_level: 'LOW' } })).ok()).toBeTruthy();

  await page.goto('/campaigns');
  await page.getByLabel('Tên đăng nhập Admin').fill('admin');
  await page.getByLabel('Mật khẩu Admin').fill(password);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await page.getByLabel('Cơ hội đã đánh giá').selectOption({ label: `${title} · AFFILIATE · 80` });
  const name = `Chiến dịch ${Date.now()}`;
  await page.getByLabel('Tên chiến dịch').fill(name);
  await page.getByRole('button', { name: 'Tạo chiến dịch' }).click();
  await expect(page.getByText('Đã tạo chiến dịch.')).toBeVisible();
  await expect(page.getByRole('heading', { name: new RegExp(name) })).toBeVisible();

  await page.getByRole('tab', { name: 'Nguồn' }).click();
  await page.getByLabel('Tên nguồn').fill('GHN — hoa hồng Shopee');
  await page.getByLabel('Trích đoạn').fill('Ngành hàng thời trang nữ có tỷ lệ hoa hồng là 3.68%.');
  await page.getByRole('button', { name: 'Thêm nguồn' }).click();
  await expect(page.getByText('Đã thêm nguồn (chưa xác minh).')).toBeVisible();
  page.once('dialog', dialog => void dialog.accept());
  await page.getByLabel('Ghi chú xác minh').fill('Owner đã đối chiếu trang GHN');
  await page.getByRole('button', { name: 'Xác minh' }).click();
  await expect(page.getByText('Nguồn đã xác minh')).toBeVisible();

  await page.getByRole('tab', { name: 'Chương trình & điều khoản' }).click();
  await page.getByLabel('Tên chương trình').fill('Shopee Affiliate');
  await page.getByLabel('Tên miền link được phép (cách nhau bằng dấu phẩy)').fill('s.shopee.vn, shope.ee');
  await page.getByLabel('Tham số theo dõi được thêm (tuỳ chọn)').fill('sub_id');
  await page.getByRole('button', { name: 'Thêm chương trình' }).click();
  await expect(page.getByText('Đã thêm chương trình.')).toBeVisible();
  await page.getByRole('combobox', { name: /^Chương trình/ }).selectOption({ label: 'Shopee Affiliate' });
  await page.getByLabel('Nội dung').fill('Thời trang nữ 3.68%');
  await page.getByLabel('Đơn vị số').selectOption('PERCENT');
  await page.getByLabel('Giá trị số').fill('3.68');
  await page.getByRole('combobox', { name: /^Nguồn/ }).selectOption({ label: 'GHN — hoa hồng Shopee · đã xác minh' });
  await page.getByRole('button', { name: 'Ghi điều khoản' }).click();
  await expect(page.getByText('Thời trang nữ 3.68% · 3.680000 PERCENT')).toBeVisible();

  await page.getByRole('tab', { name: 'Link affiliate' }).click();
  await page.getByRole('combobox', { name: /^Chương trình/ }).selectOption({ label: 'Shopee Affiliate' });
  await page.getByLabel('Nhãn').fill('Váy maxi');
  await page.getByLabel('Link affiliate gốc (https)').fill('https://evil.example/s.shopee.vn');
  await page.getByRole('button', { name: 'Lưu link' }).click();
  await expect(page.getByRole('alert')).toContainText('not allowed');
  await page.getByLabel('Link affiliate gốc (https)').fill('https://s.shopee.vn/AbC123');
  await page.getByLabel(/Tham số theo dõi/).fill('sub_id=reels01');
  await page.getByRole('button', { name: 'Lưu link' }).click();
  await expect(page.getByText('https://s.shopee.vn/AbC123?sub_id=reels01')).toBeVisible();

  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByRole('tab', { name: 'Link affiliate' })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole('link', { name: 'Nhật ký audit' }).click();
  await expect(page.getByText('campaign.link_added').first()).toBeVisible();
});
