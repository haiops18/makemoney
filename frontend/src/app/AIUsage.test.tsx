import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import AIUsage from './AIUsage';

const reservation = '00000000-0000-4000-8000-000000000009';
const empty = { currency: 'USD', invocations: 0, by_status: {}, input_tokens: 0, output_tokens: 0, estimated_cost: '0.000000', calculated_cost: '0.000000', confirmed_cost: '0.000000', held_amount: '0.000000', needs_reconciliation: 0, by_role: [], by_model: [], items: [], total_items: 0 };
const row = { id: '00000000-0000-4000-8000-000000000001', research_run_id: '00000000-0000-4000-8000-000000000002', task_id: '00000000-0000-4000-8000-000000000003', task_type: 'AI_MARKET_RESEARCH', agent_role: 'research', provider_id: '00000000-0000-4000-8000-000000000004', provider_name: 'OpenAI', provider_kind: 'OPENAI', model_id: 'gpt-test', status: 'USAGE_UNKNOWN', error_code: 'LEASE_EXPIRED', input_tokens: null, output_tokens: null, estimated_cost: '0.010000', calculated_cost: null, confirmed_cost: null, reservation_id: reservation, reservation_status: 'ACTIVE', held_amount: '0.010000', needs_reconciliation: true, created_at: '2026-11-05T00:00:00Z', completed_at: null };
const renderPage = (token = 'owner') => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><AIUsage token={token}/></MemoryRouter></QueryClientProvider>);

beforeEach(async () => { await i18n.changeLanguage('vi'); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('requires sign in and shows an explicit empty state', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => empty }) as Response));
  renderPage('');
  expect(screen.getByText('Vui lòng đăng nhập Owner.')).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
  cleanup();
  renderPage();
  expect(await screen.findByText('Chưa có lượt gọi AI nào.')).toBeInTheDocument();
});

it('shows held and unknown usage and reconciles only with a confirmed decimal amount', async () => {
  const data = { ...empty, invocations: 1, by_status: { USAGE_UNKNOWN: 1 }, estimated_cost: '0.010000', held_amount: '0.010000', needs_reconciliation: 1, by_role: [{ key: 'research', invocations: 1, input_tokens: 0, output_tokens: 0, calculated_cost: '0.000000', confirmed_cost: '0.000000' }], by_model: [], items: [row], total_items: 1 };
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => ({ ok: true, status: 200, json: async () => init?.method === 'POST' ? { id: reservation } : data }) as Response));
  vi.stubGlobal('crypto', { randomUUID: () => 'reconcile-key' });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  renderPage();
  expect(await screen.findByText('USAGE_UNKNOWN · LEASE_EXPIRED')).toBeInTheDocument();
  expect(screen.getAllByText('0.010000 USD').length).toBeGreaterThan(0);
  fireEvent.change(screen.getByLabelText('Chi phí thực tế (USD)'), { target: { value: '1e3' } });
  fireEvent.change(screen.getByLabelText('Lý do / nguồn hóa đơn'), { target: { value: 'Invoice 42' } });
  fireEvent.click(screen.getByRole('button', { name: 'Xác nhận chi phí' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Nhập số tiền thực tế (USD) và lý do.');
  fireEvent.change(screen.getByLabelText('Chi phí thực tế (USD)'), { target: { value: '0.02' } });
  expect(screen.getByRole('button', { name: 'Giải phóng phần dư' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Xác nhận chi phí' }));
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true));
  const call = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST');
  expect(String(call?.[0])).toBe(`/api/v1/budgets/reservations/${reservation}/settle`);
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({ actual_amount: '0.02', reason: 'Invoice 42' });
  expect((call?.[1]?.headers as Record<string, string>)['Idempotency-Key']).toBe('reconcile-key');
});

it('reports load failures', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response));
  renderPage();
  expect(await screen.findByRole('alert')).toHaveTextContent('Không thể tải chi phí AI.');
});
