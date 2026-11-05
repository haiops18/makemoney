import { expect, test } from '@playwright/test';

test('Owner can configure and revoke a provider key without enabling AI execution', async ({ page, request }) => {
  test.skip(!process.env.E2E_STEP6, 'Requires isolated Step 6 Compose runtime');
  expect((await request.get('/api/v1/ai/providers')).status()).toBe(401);
  await page.goto('/settings');
  await page.getByLabel('Tên đăng nhập Admin').fill('admin');
  await page.getByLabel('Mật khẩu Admin').fill('change-me-admin-password');
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  const name = `Test provider ${Date.now()}`;
  await page.getByLabel('Tên', { exact: true }).fill(name);
  await page.getByLabel('Model ID', { exact: true }).fill('test-model');
  await page.getByLabel('API key').fill('disposable-browser-test-key');
  const [response] = await Promise.all([
    page.waitForResponse(value => value.url().endsWith('/api/v1/ai/providers') && value.request().method() === 'POST' && value.status() === 201),
    page.getByRole('button', { name: 'Lưu', exact: true }).click(),
  ]);
  const responseText = await response.text();
  expect(responseText).not.toContain('disposable-browser-test-key');
  expect(JSON.parse(responseText).enabled).toBe(false);
  await expect(page.locator('article').filter({ hasText: name })).toBeVisible();
  await expect(page.getByLabel('API key')).toHaveValue('');
  const agentSection = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Model theo agent' }) }).last();
  await agentSection.getByRole('combobox', { name: 'Agent', exact: true }).selectOption({ label: 'Research Agent · research' });
  await agentSection.getByRole('combobox', { name: 'Provider', exact: true }).selectOption({ label: name });
  await agentSection.getByLabel('Model ID của agent').fill('test-agent-model');
  await agentSection.getByRole('button', { name: 'Lưu cấu hình agent' }).click();
  await expect(agentSection.getByText('Đã lưu cấu hình agent.')).toBeVisible();
  const row = page.locator('article').filter({ hasText: name });
  await row.getByRole('button', { name: 'Chọn mặc định' }).click();
  await expect(row).toContainText('Mặc định');
  await row.getByRole('button', { name: 'Cấu hình giá' }).click();
  await page.getByLabel('Phiên bản giá').fill('test-v1');
  await page.getByLabel('USD / 1 triệu input token').fill('0.5');
  await page.getByLabel('USD / 1 triệu output token').fill('1.5');
  await page.getByLabel('Hiệu lực từ (giờ thiết bị)').fill('2026-11-01T08:00');
  await page.getByLabel('Ghi chú nguồn giá').fill('Owner-provided test price');
  await page.getByRole('button', { name: 'Lưu giá' }).click();
  await expect(page.getByText('Đã lưu phiên bản giá.')).toBeVisible();
  page.on('dialog', dialog => void dialog.accept());
  await row.getByRole('button', { name: 'Thu hồi khóa' }).click();
  await expect(row.getByText('Chưa có khóa')).toBeVisible();
  await expect(page.getByText(/Cấu hình không tự kích hoạt AI trả phí\. Chỉ OpenAI, Anthropic và Gemini/)).toBeVisible();
  await expect(row.getByRole('button', { name: 'Kiểm tra kết nối' })).toBeDisabled();
});

test('Owner creates a research draft and manually adds an unverified source', async ({ page, request }) => {
  test.skip(!process.env.E2E_STEP6, 'Requires isolated Step 6 Compose runtime');
  test.setTimeout(120000);
  page.on('dialog', dialog => void dialog.accept());
  let authorization = '';
  page.on('request', item => { if (item.url().includes('/api/v1/') && item.headers().authorization) authorization = item.headers().authorization; });
  expect((await request.get('/api/v1/ai/research')).status()).toBe(401);
  await page.goto('/ai-research');
  await page.getByLabel('Tên đăng nhập Admin').fill('admin');
  await page.getByLabel('Mật khẩu Admin').fill('change-me-admin-password');
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  const objective = `Draft research ${Date.now()}`;
  await page.getByLabel('Mục tiêu nghiên cứu').fill(objective);
  await page.getByLabel('Thị trường mục tiêu').fill('Vietnam');
  await page.getByRole('button', { name: 'Tạo bản nháp' }).click();
  await expect(page.getByText('Đã lưu bản nháp.')).toBeVisible();
  await page.getByLabel('Tên nguồn').fill('Manual test source');
  await page.getByLabel('URL', { exact: true }).fill('https://example.org/test');
  await page.getByLabel('Trích đoạn').fill('A user-provided statement, not verified market evidence.');
  await page.getByRole('button', { name: 'Thêm nguồn' }).click();
  await expect(page.getByText('Manual test source · UNVERIFIED')).toBeVisible();
  await expect(page.getByText(/AI chỉ chạy khi từng task được phê duyệt riêng và có ngân sách/)).toBeVisible();
  await page.getByLabel('Ghi chú xác minh').fill('Owner checked the original document');
  await page.getByRole('button', { name: 'Xác minh', exact: true }).click();
  await expect(page.getByText('Manual test source · VERIFIED')).toBeVisible();
  await expect(page.getByText('Đã ghi nhận xác minh nguồn.')).toBeVisible();
  const flow = `Research validation ${Date.now()}`;
  await page.getByLabel('Tên workflow nghiên cứu').fill(flow);
  const [workflowResponse] = await Promise.all([
    page.waitForResponse(value => value.url().includes('/api/v1/ai/research/') && value.url().endsWith('/workflow') && value.request().method() === 'POST' && value.status() === 201),
    page.getByRole('button', { name: 'Tạo workflow nghiên cứu' }).click(),
  ]);
  const workflowId = (await workflowResponse.json()).id as string;
  // Without enabled profiles and prices for every stage agent, adding AI stages fails closed.
  await page.getByRole('button', { name: 'Thêm giai đoạn AI' }).click();
  await expect(page.getByRole('alert').filter({ hasText: /is required|unavailable/ })).toBeVisible();
  await expect(page.getByText('Workflow không có giai đoạn AI.')).toHaveCount(0);
  await page.getByRole('link', { name: 'Mở Workflow' }).click();
  await page.getByRole('button', { name: flow, exact: true }).click();
  const tasks = await request.get(`/api/v1/workflows/${workflowId}/tasks`, { headers: { Authorization: authorization } });
  const taskId = (await tasks.json())[0].id as string;
  await Promise.all([page.waitForResponse(value => value.url().endsWith(`/api/v1/workflows/${workflowId}/submit`) && value.request().method() === 'POST' && value.status() === 200), page.getByRole('button', { name: 'Gửi phê duyệt' }).click()]);
  async function approve(resourceId: string) {
    await page.getByRole('link', { name: 'Phê duyệt', exact: true }).click();
    const pending = page.locator('.row.approval').filter({ hasText: resourceId }).filter({ has: page.getByRole('button', { name: 'Phê duyệt', exact: true }) }).first();
    await pending.getByRole('button', { name: 'Phê duyệt', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('Lý do quyết định').fill('Owner reviewed internal validation');
    await Promise.all([page.waitForResponse(value => value.url().includes('/approve') && value.request().method() === 'POST' && value.status() === 200), dialog.getByRole('button', { name: 'Xác nhận' }).click()]);
    await page.getByRole('link', { name: 'Workflow', exact: true }).click();
    await page.getByRole('button', { name: flow, exact: true }).click();
  }
  await approve(workflowId);
  await page.getByRole('button', { name: 'Bắt đầu', exact: true }).click();
  await expect(page.getByText('Validate research draft · READY')).toBeVisible({ timeout: 20000 });
  await Promise.all([page.waitForResponse(value => value.url().endsWith('/api/v1/approvals') && value.request().method() === 'POST' && value.status() === 201), page.getByRole('button', { name: 'Yêu cầu duyệt task' }).click()]);
  await approve(taskId);
  const execute = page.getByRole('button', { name: 'Chạy task' });
  await expect(execute).toBeEnabled({ timeout: 15000 });
  await execute.click();
  await expect(page.getByText('Validate research draft · SUCCEEDED')).toBeVisible({ timeout: 20000 });
  await page.getByRole('link', { name: 'Chi phí AI', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Chi phí AI' })).toBeVisible();
  await expect(page.getByText('Chưa có lượt gọi AI nào.')).toBeVisible();
});

test('Owner approval controls global AI consent without enabling execution', async ({ page, request }) => {
  test.skip(!process.env.E2E_STEP6, 'Requires isolated Step 6 Compose runtime');
  expect((await request.get('/api/v1/ai/control')).status()).toBe(401);
  page.on('dialog', dialog => void dialog.accept());
  await page.goto('/settings');
  await page.getByLabel('Tên đăng nhập Admin').fill('admin');
  await page.getByLabel('Mật khẩu Admin').fill('change-me-admin-password');
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await expect(page.getByText(/Quyền Owner: Đã tắt/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Bật quyền AI', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Yêu cầu phê duyệt quyền AI' }).click();
  await expect(page.getByText('Backend đã xác nhận.')).toBeVisible();
  await page.getByRole('link', { name: 'Phê duyệt', exact: true }).click();
  const pending = page.locator('.row.approval').filter({ hasText: 'AI_CONTROL_ENABLE' }).filter({ has: page.getByRole('button', { name: 'Phê duyệt', exact: true }) }).first();
  await pending.getByRole('button', { name: 'Phê duyệt', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Lý do quyết định').fill('Owner reviewed exact AI consent');
  await dialog.getByRole('button', { name: 'Xác nhận' }).click();
  await page.getByRole('link', { name: 'Cài đặt', exact: true }).click();
  const enable = page.getByRole('button', { name: 'Bật quyền AI', exact: true });
  await expect(enable).toBeEnabled({ timeout: 15000 });
  await enable.click();
  await expect(page.getByText(/Quyền Owner: Đã bật/)).toContainText('Thực thi AI: Có thể yêu cầu theo từng task');
  await page.getByRole('button', { name: 'Tắt quyền AI', exact: true }).click();
  await expect(page.getByText(/Quyền Owner: Đã tắt/)).toBeVisible();
});
