import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import Workflows from './Workflows';

const id = '00000000-0000-4000-8000-000000000001';
const oppId = '00000000-0000-4000-8000-000000000002';
const policyId = '00000000-0000-4000-8000-000000000003';
const item = { id, opportunity_id: oppId, name: 'Research flow', description: null, status: 'DRAFT', version: 1, created_at: '2026-11-03T00:00:00Z', updated_at: '2026-11-03T00:00:00Z', task_count: 0, succeeded_tasks: 0, last_execution: null };
const ok = (value: unknown) => ({ ok: true, status: 200, json: async () => value }) as Response;
const renderPage = (token = 'test-session') => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><Workflows token={token}/></QueryClientProvider>);

beforeEach(async () => {
  await i18n.changeLanguage('vi');
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const path = String(input);
    if (path.includes('/workflows/summary')) return ok({ total: 1, counts: { DRAFT: 1 }, total_tasks: 0, task_success_rate: null });
    if (path.includes('/opportunities?')) return ok({ items: [{ id: oppId, title: 'Real opportunity', status: 'DRAFT' }], total: 1 });
    if (path.endsWith('/agents')) return ok([{ role: 'research', enabled: true }]);
    if (path.endsWith('/policies')) return ok([{ id: '00000000-0000-4000-8000-000000000004', name: 'AI policy', enabled: true, rules_json: { allowed_action_types: ['AI_CONTROL_ENABLE'] } }, { id: policyId, name: 'Owner policy', enabled: true, rules_json: { allowed_action_types: ['INTERNAL_WORKFLOW'] } }]);
    if (path.endsWith('/approvals')) return ok({ items: [] });
    if (path.includes('/tasks?') || path.includes('/events?') || path.includes('/executions?') || path.includes('/recent-executions?')) return ok([]);
    if (path.endsWith('/submit') && init?.method === 'POST') return ok({ workflow: { ...item, status: 'PENDING_APPROVAL' }, approval_id: policyId, action_hash: 'hash' });
    if (path.endsWith(`/workflows/${id}`)) return ok(item);
    if (path.includes('/workflows?')) return ok({ items: [item], total: 1 });
    if (path.endsWith('/workflows') && init?.method === 'POST') return ok(item);
    return { ok: false, status: 404, json: async () => ({ detail: 'Not found' }) } as Response;
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('requires the Owner session and renders an empty-data state without fabricated results', () => {
  renderPage('');
  expect(screen.getByText('Vui lòng đăng nhập Owner.')).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

it('renders real workflow data and creates via an idempotent request', async () => {
  renderPage();
  expect(await screen.findByRole('button', { name: 'Research flow' })).toBeInTheDocument();
  expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Tên workflow'), { target: { value: 'Research flow' } });
  fireEvent.change(screen.getByLabelText('Cơ hội'), { target: { value: oppId } });
  fireEvent.click(screen.getByRole('button', { name: /^Tạo$/ }));
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url, init]) => String(url).endsWith('/workflows') && init?.method === 'POST')).toBe(true));
  const call = vi.mocked(fetch).mock.calls.find(([url, init]) => String(url).endsWith('/workflows') && init?.method === 'POST');
  expect((call?.[1]?.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy();
});

it('requires confirmation before submit and shows controls for the current state', async () => {
  const confirmation = vi.spyOn(window, 'confirm').mockReturnValue(false);
  renderPage();
  fireEvent.click(await screen.findByRole('button', { name: 'Research flow' }));
  const submit = await screen.findByRole('button', { name: 'Gửi phê duyệt' });
  fireEvent.click(submit);
  expect(confirmation).toHaveBeenCalled();
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/submit'))).toBe(false);
  expect(screen.queryByRole('button', { name: 'Bắt đầu' })).not.toBeInTheDocument();
});

it('supports English and surfaces API errors', async () => {
  await i18n.changeLanguage('en');
  vi.mocked(fetch).mockImplementation(async () => ({ ok: false, status: 503, json: async () => ({ detail: 'API unavailable' }) }) as Response);
  renderPage();
  expect(screen.getByRole('heading', { name: 'Workflow orchestration' })).toBeInTheDocument();
  expect((await screen.findAllByRole('alert')).every(alert => alert.textContent?.includes('API unavailable'))).toBe(true);
});
