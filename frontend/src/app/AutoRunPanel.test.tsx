import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import AutoRunPanel, { type AutoRun } from './AutoRunPanel';

const workflowId = '00000000-0000-4000-8000-000000000010';
const approvalId = '00000000-0000-4000-8000-000000000011';
const runId = '00000000-0000-4000-8000-000000000012';
const tr = (vi: string) => vi;
const plan = { action: { policy_id: 'ai', action_type: 'AI_INFERENCE', action_payload: { mode: 'WORKFLOW_AUTO_RUN' }, resource_type: 'workflow', resource_id: workflowId, scope: 'ONCE' },
  action_hash: 'h', summary: { task_count: 8, ai_task_count: 7, max_cost_usd: '1.000000', source_count: 2, models: ['claude-haiku-5-5'] } };
const active: AutoRun = { id: runId, status: 'ACTIVE', stop_reason: null, expires_at: '2026-11-06T18:00:00Z', created_at: '2026-11-06T06:00:00Z', ended_at: null };

function api(overrides: Record<string, unknown> = {}) {
  return vi.fn(async (path: string, init?: RequestInit) => {
    for (const [needle, value] of Object.entries(overrides)) if (path.includes(needle)) { if (value instanceof Error) throw value; return value; }
    if (path.includes('/auto-run-action')) return plan;
    if (path === '/approvals' && init?.method === 'POST') return { id: approvalId };
    if (path.endsWith('/submit')) return { approval_id: '00000000-0000-4000-8000-000000000013' };
    if (path.endsWith('/auto-run') && init?.method === 'POST') return active;
    if (path.endsWith('/auto-run/stop')) return { ...active, status: 'STOPPED', stop_reason: 'Stopped by Owner' };
    return { id: workflowId, status: 'QUEUED', version: 2 };
  });
}

function renderPanel(props: Partial<Parameters<typeof AutoRunPanel>[0]> & { request: ReturnType<typeof api> }) {
  const onChanged = vi.fn(async () => undefined);
  render(<AutoRunPanel tr={tr} locale="vi-VN" workflowId={workflowId} status="RUNNING" aiPolicyId="ai" internalPolicyId="internal" hasAITasks autoRun={null} onChanged={onChanged} {...props}/>);
  return onChanged;
}

const posts = (request: ReturnType<typeof api>) => request.mock.calls.filter(([, init]) => init?.method === 'POST').map(([path]) => path);

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('approves the whole running workflow once and starts the auto-run', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
  const request = api();
  const onChanged = renderPanel({ request });
  expect(screen.getByTestId('auto-run-status')).toHaveTextContent('chưa bật');
  fireEvent.click(screen.getByRole('button', { name: 'Phê duyệt & chạy tự động' }));
  await waitFor(() => expect(onChanged).toHaveBeenCalled());
  expect(confirm.mock.calls[0][0]).toContain('8 bước (7 bước AI trả phí)');
  expect(confirm.mock.calls[0][0]).toContain('1.000000 USD');
  expect(confirm.mock.calls[0][0]).toContain('claude-haiku-5-5');
  expect(posts(request)).toEqual(['/approvals', `/approvals/${approvalId}/approve`, `/workflows/${workflowId}/auto-run`]);
  for (const [, init] of request.mock.calls.filter(([, init]) => init?.method === 'POST')) expect((init?.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy();
  const started = request.mock.calls.find(([path]) => path.endsWith('/auto-run'));
  expect(JSON.parse(String(started?.[1]?.body))).toEqual({ ai_policy_id: 'ai', internal_policy_id: 'internal', approval_id: approvalId });
});

it('starts a draft workflow before binding the approval to the current plan', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  const request = api();
  const onChanged = renderPanel({ request, status: 'DRAFT' });
  fireEvent.click(screen.getByRole('button', { name: 'Phê duyệt & chạy tự động' }));
  await waitFor(() => expect(onChanged).toHaveBeenCalled());
  expect(posts(request)).toEqual([`/workflows/${workflowId}/submit`, '/approvals/00000000-0000-4000-8000-000000000013/approve', `/workflows/${workflowId}/start`,
    '/approvals', `/approvals/${approvalId}/approve`, `/workflows/${workflowId}/auto-run`]);
});

it('does nothing when the Owner declines the confirmation', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(false);
  const request = api();
  const onChanged = renderPanel({ request });
  fireEvent.click(screen.getByRole('button', { name: 'Phê duyệt & chạy tự động' }));
  await waitFor(() => expect(onChanged).toHaveBeenCalled());
  expect(posts(request)).toEqual([]);
});

it('explains a missing source in plain language', async () => {
  const request = api({ '/auto-run-action': new Error('Add at least one research source before auto-run') });
  renderPanel({ request });
  fireEvent.click(screen.getByRole('button', { name: 'Phê duyệt & chạy tự động' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('chưa có nguồn nào');
  expect(posts(request)).toEqual([]);
});

it('shows an active auto-run and lets the Owner stop it', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  const request = api();
  const onChanged = renderPanel({ request, autoRun: active });
  expect(screen.getByTestId('auto-run-status')).toHaveTextContent('đang chạy tự động');
  expect(screen.queryByRole('button', { name: 'Phê duyệt & chạy tự động' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Dừng chạy tự động' }));
  await waitFor(() => expect(onChanged).toHaveBeenCalled());
  expect(posts(request)).toEqual([`/workflows/${workflowId}/auto-run/stop`]);
});

it('shows why a stopped auto-run stopped and blocks without an AI policy', () => {
  renderPanel({ request: api(), aiPolicyId: undefined, autoRun: { ...active, status: 'STOPPED', stop_reason: 'Workflow, configuration or sources changed after the auto-run approval' } });
  expect(screen.getByTestId('auto-run-status')).toHaveTextContent('đã thay đổi sau khi duyệt');
  expect(screen.getByRole('alert')).toHaveTextContent('Chưa có chính sách AI');
  expect(screen.getByRole('button', { name: 'Phê duyệt & chạy tự động' })).toBeDisabled();
});
