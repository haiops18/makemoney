import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';

test('Owner approves a workflow and a separately approved task, then cancels the dependent task', async ({ page, request }) => {
  test.skip(!process.env.E2E_STEP5, 'Requires isolated Step 5 Compose runtime and worker');
  test.setTimeout(120000);
  let authorization = '';
  page.on('request', req => { if (req.url().includes('/api/v1/') && req.headers().authorization) authorization = req.headers().authorization; });
  page.on('dialog', dialog => void dialog.accept());
  expect((await request.get('/api/v1/workflows')).status()).toBe(401);
  await page.goto('/opportunities');
  await page.getByLabel('Tên đăng nhập Admin').fill('admin');
  await page.getByLabel('Mật khẩu Admin').fill(process.env.E2E_ADMIN_PASSWORD || 'change-me-admin-password');
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  const suffix = String(Date.now());
  const opportunity = `Workflow opportunity ${suffix}`;
  const flow = `Workflow ${suffix}`;
  await page.getByLabel('Tên cơ hội').fill(opportunity);
  await page.getByRole('button', { name: 'Tạo cơ hội' }).click();
  await page.getByRole('button', { name: opportunity, exact: true }).click();
  await page.getByLabel('target_market').fill('Owner-provided test market');
  await page.getByRole('button', { name: 'Lưu Chỉnh sửa' }).click();
  await expect(page.getByText('Đã lưu và xác minh phản hồi.')).toBeVisible();

  await page.getByRole('link', { name: 'Workflow', exact: true }).click();
  await page.getByLabel('Tên workflow').fill(flow);
  await page.getByLabel('Cơ hội', { exact: true }).selectOption({ label: opportunity });
  const [createdResponse] = await Promise.all([page.waitForResponse(response => response.url().endsWith('/api/v1/workflows') && response.request().method() === 'POST' && response.status() === 201), page.getByRole('button', { name: 'Tạo', exact: true }).click()]);
  const workflowId = (await createdResponse.json()).id as string;
  await expect(page.getByRole('heading', { name: flow })).toBeVisible();
  await page.getByLabel('Tên task').fill('Owner validation');
  const [taskResponse] = await Promise.all([page.waitForResponse(response => response.url().endsWith(`/api/v1/workflows/${workflowId}/tasks`) && response.request().method() === 'POST' && response.status() === 201), page.getByRole('button', { name: 'Thêm task', exact: true }).click()]);
  const taskId = (await taskResponse.json()).id as string;
  await expect(page.getByText('Owner validation · PENDING')).toBeVisible();
  await page.getByLabel('Tên task').fill('Evidence validation');
  await page.getByLabel('Handler nội bộ').selectOption('VALIDATE_EVIDENCE');
  await page.getByRole('checkbox', { name: 'Owner validation' }).check();
  const [childResponse] = await Promise.all([page.waitForResponse(response => response.url().endsWith(`/api/v1/workflows/${workflowId}/tasks`) && response.request().method() === 'POST' && response.status() === 201), page.getByRole('button', { name: 'Thêm task', exact: true }).click()]);
  const childTaskId = (await childResponse.json()).id as string;
  await expect(page.getByText('Evidence validation · PENDING')).toBeVisible();
  await page.getByRole('button', { name: 'Gửi phê duyệt' }).click();
  const start = page.getByRole('button', { name: 'Bắt đầu', exact: true });
  await expect(start).toBeDisabled();
  expect((await request.post(`/api/v1/workflows/${workflowId}/start`, { headers: { Authorization: authorization, 'Idempotency-Key': `e2e-denied-${suffix}` } })).status()).toBe(403);

  async function approvePending() {
    await page.getByRole('link', { name: 'Phê duyệt', exact: true }).click();
    const pending = page.locator('.row.approval').filter({ has: page.getByRole('button', { name: 'Phê duyệt', exact: true }) }).first();
    await pending.getByRole('button', { name: 'Phê duyệt', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('Lý do quyết định').fill('Owner reviewed the exact internal action');
    await Promise.all([page.waitForResponse(response => response.url().includes('/approve') && response.request().method() === 'POST' && response.status() === 200), dialog.getByRole('button', { name: 'Xác nhận' }).click()]);
    await page.getByRole('link', { name: 'Workflow', exact: true }).click();
    await page.getByRole('button', { name: flow, exact: true }).click();
  }
  await approvePending();
  await page.getByRole('button', { name: 'Bắt đầu', exact: true }).click();
  await expect(page.getByText('Owner validation · READY')).toBeVisible({ timeout: 20000 });
  await expect(page.getByText('Evidence validation · BLOCKED')).toBeVisible();
  const policyResponse = await request.get('/api/v1/policies', { headers: { Authorization: authorization } });
  const policyId = (await policyResponse.json())[0].id as string;
  const preparedResponse = await request.get(`/api/v1/workflows/${workflowId}/tasks/${childTaskId}/approval-action`, { params: { policy_id: policyId }, headers: { Authorization: authorization } });
  expect(preparedResponse.status()).toBe(200);
  const action = (await preparedResponse.json()).action;
  const approvalBody = { policy_id: action.policy_id, action_type: action.action_type, action_payload: action.action_payload, resource_type: action.resource_type, resource_id: action.resource_id, scope: action.scope, expires_at: new Date(Date.now() + 15 * 60000).toISOString() };
  const childApproval = await request.post('/api/v1/approvals', { headers: { Authorization: authorization, 'Idempotency-Key': `e2e-child-approval-${suffix}` }, data: approvalBody });
  expect(childApproval.status()).toBe(201);
  const childApprovalId = (await childApproval.json()).id as string;
  expect((await request.post(`/api/v1/approvals/${childApprovalId}/approve`, { headers: { Authorization: authorization, 'Idempotency-Key': `e2e-child-decision-${suffix}` }, data: { reason: 'Owner reviewed dependency' } })).status()).toBe(200);
  expect((await request.post(`/api/v1/workflows/${workflowId}/tasks/${childTaskId}/queue`, { headers: { Authorization: authorization, 'Idempotency-Key': `e2e-blocked-${suffix}` }, data: { policy_id: policyId, approval_id: childApprovalId } })).status()).toBe(403);
  await Promise.all([page.waitForResponse(response => response.url().endsWith('/api/v1/approvals') && response.request().method() === 'POST' && response.status() === 201), page.getByRole('button', { name: 'Yêu cầu duyệt task', exact: true }).click()]);
  await approvePending();
  const project = process.env.E2E_COMPOSE_PROJECT;
  if (project) {
    if (!['step5-local', 'step5-ci', 'step5-release'].includes(project) || process.env.E2E_BASE_URL !== 'http://127.0.0.1:18006') throw new Error('Worker restart is restricted to the isolated Step 5 test stack');
    const compose = (...args: string[]) => execFileSync('docker', ['compose', '-p', project, '-f', '../compose.step5-test.yml', ...args], { encoding: 'utf8' });
    compose('stop', 'worker');
    try {
      const [queuedResponse] = await Promise.all([page.waitForResponse(response => response.url().endsWith(`/tasks/${taskId}/queue`) && response.request().method() === 'POST' && response.status() === 201), page.getByRole('button', { name: 'Chạy task', exact: true }).click()]);
      const queuedId = (await queuedResponse.json()).id as string;
      const claimScript = 'from app.db.session import SessionLocal\nfrom app.orchestration.worker import claim_one\nr=claim_one(SessionLocal)\nassert r is not None\nprint(r[0])';
      const claimedId = compose('exec', '-T', 'backend', 'python', '-c', claimScript).trim();
      expect(claimedId).toBe(queuedId);
      if (!/^[0-9a-f-]{36}$/.test(claimedId)) throw new Error('Unexpected execution ID');
      const expireScript = `from datetime import UTC, datetime, timedelta\nfrom uuid import UUID\nfrom app.db.session import SessionLocal\nfrom app.db.models import TaskExecution\ns=SessionLocal()\ne=s.get(TaskExecution, UUID('${claimedId}'))\nassert e is not None and e.status == 'RUNNING'\ne.lease_expires_at=datetime.now(UTC)-timedelta(seconds=1)\ns.commit()\ns.close()`;
      compose('exec', '-T', 'backend', 'python', '-c', expireScript);
    } finally {
      compose('start', 'worker');
    }
    await expect(page.getByText('Owner validation · RETRY_WAIT')).toBeVisible({ timeout: 20000 });
    await expect(page.getByText(/ABANDONED/).first()).toBeVisible();
    await Promise.all([page.waitForResponse(response => response.url().endsWith('/api/v1/approvals') && response.request().method() === 'POST' && response.status() === 201), page.getByRole('button', { name: 'Yêu cầu duyệt task', exact: true }).click()]);
    await approvePending();
    await page.getByRole('button', { name: 'Thử lại task', exact: true }).click();
  } else {
    await page.getByRole('button', { name: 'Chạy task', exact: true }).click();
  }
  await expect(page.getByText('Owner validation · SUCCEEDED')).toBeVisible({ timeout: 20000 });
  await expect(page.getByText('Evidence validation · READY')).toBeVisible({ timeout: 10000 });
  await page.getByRole('button', { name: 'Hủy workflow', exact: true }).click();
  await expect(page.getByText('Evidence validation · CANCELLED')).toBeVisible();
  await expect(page.getByText(/TASK_CANCELLED/).first()).toBeVisible();
  await expect(page.getByText(/SUCCEEDED/).first()).toBeVisible();
  await page.getByRole('link', { name: 'Nhật ký audit' }).click();
  await expect(page.getByText('workflow.execution_claimed').first()).toBeVisible();
});
